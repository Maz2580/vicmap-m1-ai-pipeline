"""Deterministic pre-LLM rule engine for M1 row validation.

The engine runs cheap-to-expensive checks against a single M1 row. Each
check can short-circuit with a terminal verdict (KEEP / REJECT), or leave
the verdict as AMBIGUOUS — in which case the caller should fall through to
the LLM.

Why bother with rules first?
----------------------------
Looking at the production VES-rejection training data, ~89% of real
rejections fall into 4 categories that can be checked **deterministically**
against your SDE database:

  - Road-locality combo missing in Vicmap ADDRESS (and new_road != Y)
  - Provided coordinates / rural address fall outside property polygon
  - Parcel has no property link (M2 required, not M1)
  - Mandatory fields missing for the row's edit_code

Running these in code instead of via the LLM:

  - Eliminates LLM cost on rejections we can prove without it.
  - Cuts latency to ~10-30ms per check vs. ~1-3s per LLM call.
  - Gives deterministic, reproducible answers — same input -> same verdict.

Rows that no rule could classify are returned with verdict='AMBIGUOUS' and
the caller (smart_openai_validator) decides whether to invoke the LLM with
the existing rule findings already attached.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------#
# Result types                                                               #
# ---------------------------------------------------------------------------#

Verdict = Literal["KEEP", "REJECT", "AMBIGUOUS"]
Severity = Literal["info", "warning", "error"]


@dataclass
class Issue:
    field: str
    severity: Severity
    message: str
    suggested_fix: str | None = None
    rule: str | None = None  # which rule produced this issue


@dataclass
class RuleResult:
    verdict: Verdict = "AMBIGUOUS"
    confidence: float = 0.0
    issues: list[Issue] = field(default_factory=list)
    rules_fired: list[str] = field(default_factory=list)

    @property
    def is_terminal(self) -> bool:
        return self.verdict in ("KEEP", "REJECT")

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


# ---------------------------------------------------------------------------#
# Per-edit-code mandatory fields (Vicmap M1 V12 spec)                        #
# ---------------------------------------------------------------------------#

# Codes:
#   B - Remove primary property from base / retire base
#   C - Update parcel-based Council Reference number (Crefno)
#   E - Update both property and address details
#   P - Update property details only
#   S - Update address details only
#   Z - Remove secondary address / downgrade distance-based to urban
#   A - Add property to multi-assessment
#   R - Remove property from multi-assessment
MANDATORY_FIELDS_BY_EDIT_CODE: dict[str, list[str]] = {
    "P": ["propnum"],
    "E": ["propnum", "road_name", "locality_name"],
    "S": ["road_name", "locality_name"],
    "A": ["propnum"],
    "R": ["propnum"],
    "B": ["propnum"],
    # 'C' needs crefno but null is permitted — handled below
    # 'Z' has lighter requirements
}

VALID_EDIT_CODES = set("BCEPSZAR")


# ---------------------------------------------------------------------------#
# Helpers                                                                    #
# ---------------------------------------------------------------------------#

def _get(row: dict[str, Any], key: str, default: str = "") -> str:
    """Robustly fetch a string field from a CSV row (handles None / nan)."""
    val = row.get(key, default)
    if val is None:
        return default
    s = str(val).strip()
    if s.lower() == "nan":
        return default
    # Pozi sometimes appends '.0' to numeric IDs
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def _get_float(row: dict[str, Any], key: str) -> float | None:
    raw = _get(row, key)
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------#
# RuleEngine                                                                 #
# ---------------------------------------------------------------------------#

class RuleEngine:
    """Evaluate one M1 row against a sequence of deterministic rules.

    Construction
    ------------
    The engine needs an SDE helper (ReadOnlySDEHelper) and the council's
    LGA code. The SDE helper can be ``None`` — in that case, only the
    schema rules run (no DB-hitting rules), and DB-dependent rejections
    fall through to AMBIGUOUS so the LLM still has a chance.
    """

    def __init__(self, sde, lga_code: str, *, fail_fast: bool = True):
        self.sde = sde
        self.lga_code = str(lga_code)
        self.fail_fast = fail_fast

    def evaluate(self, row: dict[str, Any]) -> RuleResult:
        """Run rules on a single row and return a verdict."""
        result = RuleResult()

        # Schema rules — always run, cheap, no DB hit.
        self._rule_edit_code_valid(row, result)
        self._rule_mandatory_fields_for_edit_code(row, result)

        # If schema rules already rejected and fail_fast, stop here.
        if self.fail_fast and result.has_errors:
            result.verdict = "REJECT"
            result.confidence = 1.0
            return result

        # DB-hitting rules — only run if we have an SDE helper.
        if self.sde is not None:
            self._rule_road_locality_exists(row, result)
            if self.fail_fast and result.has_errors:
                result.verdict = "REJECT"
                result.confidence = 0.95
                return result

            self._rule_parcel_has_property(row, result)
            if self.fail_fast and result.has_errors:
                result.verdict = "REJECT"
                result.confidence = 0.95
                return result

            self._rule_parcel_by_spi_has_property(row, result)
            if self.fail_fast and result.has_errors:
                result.verdict = "REJECT"
                result.confidence = 0.95
                return result

            self._rule_point_in_property(row, result)
            if self.fail_fast and result.has_errors:
                result.verdict = "REJECT"
                result.confidence = 0.9
                return result

            # WARNING-level rule — doesn't reject, just flags AMBIGUOUS so
            # the LLM judges with the rural-address context.
            self._rule_p_edit_with_distance_based_address(row, result)

        # Comment-pattern rules — independent of SDE. Run always.
        self._rule_pozi_sync_drift_multi_assessment(row, result)

        # No rule fired definitively. If we collected no issues, we can
        # confidently KEEP — there's nothing wrong with the row that we
        # know how to detect. Otherwise stay AMBIGUOUS for the LLM.
        if not result.issues:
            result.verdict = "KEEP"
            # Slightly under 1.0 — we only know "nothing wrong that we can
            # check"; the LLM might still spot a comment-field warning.
            result.confidence = 0.75
        return result

    # ----------------------------------------------------------------- #
    # Schema rules                                                       #
    # ----------------------------------------------------------------- #

    def _rule_edit_code_valid(self, row, result: RuleResult) -> None:
        ec = _get(row, "edit_code").upper()
        if not ec:
            result.issues.append(Issue(
                field="edit_code",
                severity="error",
                message="edit_code is required on every M1 row.",
                suggested_fix="Set edit_code to one of B, C, E, P, S, Z, A, R.",
                rule="edit_code_valid",
            ))
        elif ec not in VALID_EDIT_CODES:
            result.issues.append(Issue(
                field="edit_code",
                severity="error",
                message=f"edit_code={ec!r} is not a valid Vicmap M1 V12 code.",
                suggested_fix="Use one of B, C, E, P, S, Z, A, R.",
                rule="edit_code_valid",
            ))
        result.rules_fired.append("edit_code_valid")

    def _rule_mandatory_fields_for_edit_code(self, row, result: RuleResult) -> None:
        ec = _get(row, "edit_code").upper()
        if ec not in MANDATORY_FIELDS_BY_EDIT_CODE:
            return
        required = MANDATORY_FIELDS_BY_EDIT_CODE[ec]
        missing = [f for f in required if not _get(row, f)]
        for f in missing:
            result.issues.append(Issue(
                field=f,
                severity="error",
                message=(
                    f"{f} is mandatory for edit_code={ec} but is empty. "
                    f"VES will reject this row."
                ),
                suggested_fix=f"Populate the {f} column before submission.",
                rule="mandatory_fields_for_edit_code",
            ))
        result.rules_fired.append("mandatory_fields_for_edit_code")

    # ----------------------------------------------------------------- #
    # DB-hitting rules                                                   #
    # ----------------------------------------------------------------- #

    def _rule_road_locality_exists(self, row, result: RuleResult) -> None:
        """Catches the #1 VES rejection (47% of real-world rejections).

        Matches on the FULL road identity (name + type + suffix) so we
        distinguish 'INDUSTRIAL ROAD' from 'INDUSTRIAL DRIVE' — VES treats
        these as different roads, and our earlier name-only check was
        false-negative on every type-mismatch case.
        """
        road = _get(row, "road_name")
        road_type = _get(row, "road_type") or None
        road_suffix = _get(row, "road_suffix") or None
        locality = _get(row, "locality_name")
        new_road = _get(row, "new_road").upper()

        if not (road and locality):
            return
        if new_road == "Y":
            return

        try:
            res = self.sde.check_road_locality_exists(
                road, locality, self.lga_code,
                road_type=road_type, road_suffix=road_suffix,
            )
        except Exception as exc:
            logger.warning("SDE check_road_locality_exists failed: %s", exc)
            return

        if not res.get("exists"):
            full_road = " ".join(
                p for p in (road, road_type, road_suffix) if p
            )
            result.issues.append(Issue(
                field="road_name+road_type+locality_name",
                severity="error",
                message=(
                    f"Road-locality combination '{full_road}, {locality}' "
                    f"is not present in Vicmap ADDRESS for LGA "
                    f"{self.lga_code}, and new_road is not 'Y'. VES will "
                    f"reject this with 'M1 Road-Locality combination does "
                    f"not exist and not a new road'."
                ),
                suggested_fix=(
                    "Either set new_road='Y' if this really is a new road, "
                    "or verify road_name AND road_type spelling — VES "
                    "treats 'INDUSTRIAL DRIVE' and 'INDUSTRIAL ROAD' as "
                    "different roads."
                ),
                rule="road_locality_exists",
            ))
        result.rules_fired.append("road_locality_exists")

    def _rule_parcel_has_property(self, row, result: RuleResult) -> None:
        """Catches 'Parcel has no property link M2 required for fix'."""
        parcel_pfi = _get(row, "parcel_pfi")
        if not parcel_pfi:
            return

        try:
            res = self.sde.check_parcel_has_property(parcel_pfi, self.lga_code)
        except Exception as exc:
            logger.warning("SDE check_parcel_has_property failed: %s", exc)
            return

        if res.get("exists") and not res.get("linked"):
            result.issues.append(Issue(
                field="parcel_pfi",
                severity="error",
                message=(
                    f"Parcel {parcel_pfi} exists in PARCEL_MP but has no "
                    f"linked property. VES will reject with 'Parcel has no "
                    f"property link M2 required for fix' — an M1 cannot "
                    f"create the link, you need to submit an M2 first."
                ),
                suggested_fix="Submit an M2 to create the parcel-property link, then resubmit this row.",
                rule="parcel_has_property",
            ))
        result.rules_fired.append("parcel_has_property")

    def _rule_parcel_by_spi_has_property(self, row, result: RuleResult) -> None:
        """Like _rule_parcel_has_property but identifies the parcel by SPI.

        VES rejects with 'Parcel has no property link M2 required for fix'
        regardless of how the parcel was identified in the M1. We only run
        this when parcel_pfi is *empty* (so we don't double-check the same
        parcel from both directions).
        """
        if _get(row, "parcel_pfi"):
            return  # _rule_parcel_has_property already checked by PFI
        spi = _get(row, "spi")
        if not spi:
            return

        try:
            res = self.sde.check_parcel_has_property_by_spi(spi, self.lga_code)
        except Exception as exc:
            logger.warning("SDE check_parcel_has_property_by_spi failed: %s", exc)
            return

        if res.get("exists") and not res.get("linked"):
            result.issues.append(Issue(
                field="spi",
                severity="error",
                message=(
                    f"Parcel SPI {spi} exists in PARCEL_MP but has no linked "
                    f"property. VES will reject with 'Parcel has no property "
                    f"link M2 required for fix' — an M1 cannot create the "
                    f"link, you need to submit an M2 first."
                ),
                suggested_fix="Submit an M2 to create the parcel-property link, then resubmit this row.",
                rule="parcel_by_spi_has_property",
            ))
        result.rules_fired.append("parcel_by_spi_has_property")

    def _rule_p_edit_with_distance_based_address(self, row, result: RuleResult) -> None:
        """For edit_code=P + SPI populated + property has rural address:
        WARN that VES may reject with 'Original rural address would fall
        outside property'. Sets verdict to AMBIGUOUS (not REJECT) — the
        LLM gets to judge, since the staleness of training data means
        some of these may have been fixed.
        """
        edit_code = _get(row, "edit_code").upper()
        propnum = _get(row, "propnum")
        spi = _get(row, "spi")
        # Only relevant when P (property-only edit) AND the parcel set is
        # changing (SPI populated) AND we have a propnum to look up.
        if edit_code != "P" or not spi or not propnum:
            return

        try:
            info = self.sde.check_property_address_is_distance_based(
                propnum, self.lga_code,
            )
        except Exception as exc:
            logger.warning(
                "SDE check_property_address_is_distance_based failed: %s", exc,
            )
            return

        if info.get("distance_based"):
            result.issues.append(Issue(
                field="spi",
                severity="warning",
                message=(
                    f"Property {propnum} has a distance-based (rural) "
                    f"primary address ({info.get('address')!r}). Changing "
                    f"the parcel set via SPI {spi} may shift the calculated "
                    f"rural-address point outside the new polygon — VES "
                    f"historically rejects this with 'Original rural "
                    f"address would fall outside property'. Verify the "
                    f"resulting address position, or accompany this with an "
                    f"S edit to relocate the address."
                ),
                suggested_fix=(
                    "Either submit an accompanying S edit to set explicit "
                    "coordinates for the address, or confirm the new parcel "
                    "polygon still contains the calculated rural-address "
                    "point."
                ),
                rule="p_edit_with_distance_based_address",
            ))
        result.rules_fired.append("p_edit_with_distance_based_address")

    def _rule_pozi_sync_drift_multi_assessment(self, row, result: RuleResult) -> None:
        """Flag a Pozi-generated multi-assessment where the new propnum and
        the existing property have different road names.

        Data flow context
        -----------------
        Pathway (council ERP) is the upstream source of property/address
        changes. Pozi compares Pathway against SDE (which lags Vicmap until
        the previous M1 round-trips) and writes M1 rows to push Pathway's
        new propnums into Vicmap via VES. To attach a new propnum to an
        existing property, Pozi does a *spatial intersection* of the new
        parcel against existing SDE property polygons. When the
        intersected property's address has a different road name than the
        new propnum's Pathway-supplied address, Pozi flags
        ``**WARNING**: properties have different road names`` in the
        comments field.

        Why this matters
        ----------------
        Two plausible causes:
          (a) Legitimate — the new lot really does front a different road
              than the parent property (corner lots, rear lots, etc.).
          (b) Mistake — Pozi's spatial join picked up an unrelated
              neighbouring property, OR Pathway hasn't been told the
              parent was retired, OR there's a propnum collision.

        Auto-accepting (b) corrupts Vicmap. Auto-rejecting (a) blocks
        legitimate edits. The only safe action is human review.

        Behaviour
        ---------
        Mark the row AMBIGUOUS with a high-priority warning so:
          1. The LLM call gets the exact comment context and can reason
             about it instead of guessing.
          2. The rule engine doesn't silently rubber-stamp the row as KEEP
             (which is what happens today for these 140+ rows per Pozi run).

        Signal in your training data: 168-row Pozi file had 140 rows
        matching ``**WARNING** + different road``. Not all wrong, but
        every one needs human eyes.
        """
        edit_code = _get(row, "edit_code").upper()
        if edit_code != "A":
            return
        comments = (row.get("comments") or "").strip()
        if not comments:
            return
        cl = comments.lower()
        # Both markers must be present — '**WARNING**' alone happens in
        # other comment contexts, and 'different road' alone could be a
        # genuine multi-road address.
        if ("**warning**" in cl) and ("different road" in cl):
            result.issues.append(Issue(
                field="comments",
                severity="warning",
                message=(
                    "Pozi flagged a multi-assessment add where the new "
                    "propnum (from Pathway) and the target property (from "
                    "SDE) have different road names. This is often legitimate "
                    "(corner/rear lots) but is also the signature of Pozi "
                    "spatially mis-matching the new parcel to a neighbouring "
                    "property, or of Pathway holding an unretired parent. "
                    "Cannot auto-decide — needs human review."
                ),
                suggested_fix=(
                    "Look at both addresses in Vicmap before submitting: "
                    "confirm the new propnum's address really sits on the "
                    "existing property's parcels, and that Pathway still "
                    "shows the parent as active. If the parent should have "
                    "been retired or the parcel really is unrelated, DROP "
                    "this row from the M1 — do not submit."
                ),
                rule="pozi_sync_drift_multi_assessment",
            ))
        result.rules_fired.append("pozi_sync_drift_multi_assessment")

    def _rule_point_in_property(self, row, result: RuleResult) -> None:
        """Catches 'Provided Co-ordinates fall outside property' / 'rural address would fall outside property'."""
        easting = _get_float(row, "easting")
        northing = _get_float(row, "northing")
        propnum = _get(row, "propnum")

        if easting is None or northing is None or not propnum:
            return

        try:
            res = self.sde.point_in_property(
                easting, northing, propnum, self.lga_code,
            )
        except Exception as exc:
            logger.warning("SDE point_in_property failed: %s", exc)
            return

        if res.get("inside") is False:
            result.issues.append(Issue(
                field="easting+northing",
                severity="error",
                message=(
                    f"Coordinates ({easting}, {northing}) fall outside the "
                    f"polygon of property {propnum}. VES will reject this row."
                ),
                suggested_fix=(
                    "Re-check the address location, or use a different "
                    "propnum that actually contains this point."
                ),
                rule="point_in_property",
            ))
        result.rules_fired.append("point_in_property")
