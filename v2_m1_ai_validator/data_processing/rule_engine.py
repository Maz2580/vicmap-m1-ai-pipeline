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
import re
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

# Plan-number prefixes that legitimately carry NO lot number (M1 spec,
# "Vicmap LAT Link": Plan of Consolidation, Consolidated Plan, land in
# Title Plan). Any other plan (PS = Plan of Subdivision, etc.) requires a lot.
PLAN_PREFIXES_WITHOUT_LOT = {"PC", "CP", "TP"}

# Acceptable datum/projection tokens (M1 V12 spec FAQ "What datum/projections
# can I use?"). Compared case-insensitively with internal spaces collapsed.
VALID_DATUM_PROJ = {
    "EPSG:7855", "EPSG:7854", "EPSG:28355", "EPSG:28354", "EPSG:3111",
    "EPSG:7899", "GDA2020 MGA55", "GDA2020 MGA54", "GDA94 MGA55",
    "GDA94 MGA54", "VG94", "VICGRID94", "VG2020", "VICGRID2020",
}

# A single new propnum legitimately joins ONE multi-assessment (occasionally a
# small same-address set, e.g. units "2/39" + "3/39"). When the SAME new
# propnum is added (edit_code=A) to this many or more DISTINCT existing target
# properties, it is the "parent re-add" anti-pattern: a subdivided parent being
# stamped back onto every child lot of its plan. Flag for human review.
FANOUT_THRESHOLD = 3

# Pull "... to property <propnum>" out of a Pozi multi-assessment comment.
_FANOUT_TARGET_RE = re.compile(r"to property (\d+)", re.IGNORECASE)


def analyze_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute file-level context that single-row rules can't see.

    Currently builds the multi-assessment fan-out map: for every new propnum
    added via edit_code=A, the set of DISTINCT existing target properties it
    is being attached to (parsed from the Pozi comment "... to property N").

    Returns ``{"fanout": {propnum: {"targets": [...], "count": int}}}``.
    Pass the result into ``RuleEngine.evaluate(row, batch_context=...)``.
    """
    fanout: dict[str, set[str]] = {}
    for row in rows:
        if _get(row, "edit_code").upper() != "A":
            continue
        propnum = _get(row, "propnum")
        if not propnum:
            continue
        comment = str(row.get("comments") or "")
        targets = fanout.setdefault(propnum, set())
        for m in _FANOUT_TARGET_RE.finditer(comment):
            targets.add(m.group(1))
    return {
        "fanout": {
            pn: {"targets": sorted(t), "count": len(t)}
            for pn, t in fanout.items()
        }
    }


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

    def evaluate(
        self,
        row: dict[str, Any],
        batch_context: dict[str, Any] | None = None,
    ) -> RuleResult:
        """Run rules on a single row and return a verdict.

        ``batch_context`` carries file-level facts that can't be derived from
        a single row — currently the multi-assessment fan-out map produced by
        ``analyze_batch``. It is optional; without it the cross-row rules are
        simply skipped.
        """
        result = RuleResult()
        new_sub = _get(row, "new_sub").upper() == "Y"

        # Schema rules — always run, cheap, no DB hit. These check spec
        # conformance that VES enforces deterministically (the "Some common
        # load report messages" section of the M1 V12 doc), so a violation
        # is a certain rejection, not a judgement call.
        self._rule_edit_code_valid(row, result)
        self._rule_mandatory_fields_for_edit_code(row, result)
        self._rule_plan_lot_pairing(row, result)
        self._rule_coordinates_required(row, result)
        self._rule_datum_when_coordinates(row, result)
        self._rule_hsa_consistency(row, result)

        # Schema errors are format errors — terminal even for new subdivisions.
        if self.fail_fast and result.has_errors:
            result.verdict = "REJECT"
            result.confidence = 1.0
            return result

        # DB-hitting rules — only run if we have an SDE helper.
        if self.sde is not None:
            sde_start = len(result.issues)

            # Existing error-severity checks (proven in production).
            self._rule_road_locality_exists(row, result)
            self._rule_parcel_has_property(row, result)
            self._rule_parcel_by_spi_has_property(row, result)
            self._rule_point_in_property(row, result)

            # New warning-severity checks — highlight for human review, never
            # auto-REJECT (see VES "common load report messages").
            self._rule_parcel_links_to_multiple_properties(row, result)
            self._rule_prop_pfi_exists(row, result)
            self._rule_complex_address(row, result)
            self._rule_p_edit_with_distance_based_address(row, result)

            if new_sub:
                # A brand-new subdivision lot legitimately isn't in SDE yet:
                # SDE lags Pathway by one M1 round-trip. Don't hard-REJECT on
                # SDE-absence — downgrade those errors to warnings so the row
                # routes to human/LLM review instead of being blocked.
                for issue in result.issues[sde_start:]:
                    if issue.severity == "error":
                        issue.severity = "warning"
                        issue.message += (
                            " [new_sub=Y: SDE may simply lag this new "
                            "subdivision, so this is flagged for review, not "
                            "rejected.]"
                        )
            elif self.fail_fast and result.has_errors:
                result.verdict = "REJECT"
                result.confidence = 0.95
                return result

        # Comment-pattern + cross-row rules — independent of SDE. Run always.
        self._rule_pozi_sync_drift_multi_assessment(row, result)
        self._rule_parent_readd_fanout(row, result, batch_context)

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

    def _rule_plan_lot_pairing(self, row, result: RuleResult) -> None:
        """plan_number and lot_number must travel together.

        M1 spec (Vicmap LAT Link): where plan_number is populated, lot_number
        must also be populated *unless* the plan has no lot — Plan of
        Consolidation (PC), Consolidated Plan (CP), or land in Title Plan
        (TP). Where lot_number is populated, plan_number must also be present.
        """
        plan = _get(row, "plan_number")
        lot = _get(row, "lot_number")

        if lot and not plan:
            result.issues.append(Issue(
                field="plan_number",
                severity="error",
                message=(
                    f"lot_number={lot!r} is populated but plan_number is "
                    f"empty. M1 requires both together."
                ),
                suggested_fix="Populate plan_number to match the lot_number.",
                rule="plan_lot_pairing",
            ))
        elif plan and not lot:
            prefix = "".join(c for c in plan[:2] if c.isalpha()).upper()
            if prefix not in PLAN_PREFIXES_WITHOUT_LOT:
                result.issues.append(Issue(
                    field="lot_number",
                    severity="error",
                    message=(
                        f"plan_number={plan!r} is populated but lot_number is "
                        f"empty. A lot number is required unless the plan is a "
                        f"PC/CP/TP (which {plan!r} is not)."
                    ),
                    suggested_fix=(
                        "Populate lot_number, or confirm the plan is a "
                        "Plan of Consolidation / Consolidated Plan / Title Plan."
                    ),
                    rule="plan_lot_pairing",
                ))
        result.rules_fired.append("plan_lot_pairing")

    def _rule_coordinates_required(self, row, result: RuleResult) -> None:
        """easting+northing are mandatory when the address is positioned away
        from the default urban location.

        M1 spec (Address - Location): easting/northing are mandatory where
        ``distance_related_flag = 'Y'`` OR ``is_primary = 'N'`` (a secondary
        address). Without coordinates VES cannot place the point and rejects.
        """
        dist_flag = _get(row, "distance_related_flag").upper()
        is_primary = _get(row, "is_primary").upper()
        needs_coords = dist_flag == "Y" or is_primary == "N"
        if not needs_coords:
            return

        easting = _get_float(row, "easting")
        northing = _get_float(row, "northing")
        if easting is None or northing is None:
            trigger = (
                "distance_related_flag='Y'" if dist_flag == "Y"
                else "is_primary='N' (secondary address)"
            )
            result.issues.append(Issue(
                field="easting+northing",
                severity="error",
                message=(
                    f"Coordinates are mandatory because {trigger}, but "
                    f"easting/northing are not both populated. VES cannot "
                    f"position the address and will reject the row."
                ),
                suggested_fix=(
                    "Supply both easting and northing (from LASSI), or, if "
                    "this should be a default urban address, clear "
                    "distance_related_flag / set is_primary='Y'."
                ),
                rule="coordinates_required",
            ))
        result.rules_fired.append("coordinates_required")

    def _rule_datum_when_coordinates(self, row, result: RuleResult) -> None:
        """datum_proj must be populated (and recognised) when coordinates are.

        M1 spec: "The Map Projection and Coordinate System must be populated
        when the Easting and Northing attributes have been populated."
        """
        easting = _get_float(row, "easting")
        northing = _get_float(row, "northing")
        if easting is None and northing is None:
            return

        datum = _get(row, "datum_proj")
        if not datum:
            result.issues.append(Issue(
                field="datum_proj",
                severity="error",
                message=(
                    "easting/northing are populated but datum_proj is empty. "
                    "The datum and projection must be supplied with "
                    "coordinates (e.g. EPSG:7855 for GDA2020 MGA55)."
                ),
                suggested_fix="Populate datum_proj, e.g. 'EPSG:7855'.",
                rule="datum_when_coordinates",
            ))
        else:
            norm = " ".join(datum.upper().split())
            if norm not in VALID_DATUM_PROJ:
                # Unrecognised token: warn (AMBIGUOUS), don't hard-reject —
                # the council may use a valid alias we haven't enumerated.
                result.issues.append(Issue(
                    field="datum_proj",
                    severity="warning",
                    message=(
                        f"datum_proj={datum!r} is not one of the recognised "
                        f"M1 datum/projection tokens. Verify it is a valid "
                        f"GDA94/GDA2020 MGA or Vicgrid value (or an EPSG code "
                        f"such as 7855/28355/3111)."
                    ),
                    suggested_fix=(
                        "Use a documented value: EPSG:7855/7854/28355/28354/"
                        "3111/7899 or the equivalent named projection."
                    ),
                    rule="datum_when_coordinates",
                ))
        result.rules_fired.append("datum_when_coordinates")

    def _rule_hsa_consistency(self, row, result: RuleResult) -> None:
        """Hotel Style Address consistency.

        M1 spec: if ``hsa_flag = 'Y'`` then hsa_unit_id is mandatory AND none
        of the Address-Floor fields may be populated (the full unit detail
        lives in hsa_unit_id instead).
        """
        if _get(row, "hsa_flag").upper() != "Y":
            return

        if not _get(row, "hsa_unit_id"):
            result.issues.append(Issue(
                field="hsa_unit_id",
                severity="error",
                message=(
                    "hsa_flag='Y' but hsa_unit_id is empty. A Hotel Style "
                    "Address requires the standardized hsa_unit_id."
                ),
                suggested_fix=(
                    "Populate hsa_unit_id per AS/NZS4819 format, or clear "
                    "hsa_flag if this is not a hotel-style address."
                ),
                rule="hsa_consistency",
            ))

        floor_fields = [
            "floor_type", "floor_prefix_1", "floor_no_1", "floor_suffix_1",
            "floor_prefix_2", "floor_no_2", "floor_suffix_2",
        ]
        populated_floor = [f for f in floor_fields if _get(row, f)]
        if populated_floor:
            result.issues.append(Issue(
                field="floor_*",
                severity="error",
                message=(
                    f"hsa_flag='Y' but floor field(s) "
                    f"{', '.join(populated_floor)} are populated. For a "
                    f"Hotel Style Address the floor fields must be empty — "
                    f"the detail belongs in hsa_unit_id."
                ),
                suggested_fix=(
                    "Move the floor/level detail into hsa_unit_id and clear "
                    "the floor_* columns."
                ),
                rule="hsa_consistency",
            ))
        result.rules_fired.append("hsa_consistency")

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

    def _rule_parcel_links_to_multiple_properties(self, row, result: RuleResult) -> None:
        """VES: "Cannot Determine Property Pfi > 1 Property Found For Parcel
        Identifier". If the parcel used in the M1 links to 2+ properties, the
        parcel identifier cannot be used. This is also the per-row SDE cause
        of the parent-re-add fan-out. Warning -> highlight for human review.

        Gate: only relevant when the parcel/SPI is the SOLE locator. If the
        row also carries a propnum or property_pfi, VES uses that to pinpoint
        the property and the parcel multiplicity is harmless — so we skip,
        avoiding a false flag on the (very common) propnum+SPI rows.
        """
        if _get(row, "propnum") or _get(row, "property_pfi"):
            return

        parcel_pfi = _get(row, "parcel_pfi")
        spi = _get(row, "spi")
        if parcel_pfi:
            ident, by_spi, label = parcel_pfi, False, f"parcel_pfi {parcel_pfi}"
        elif spi:
            ident, by_spi, label = spi, True, f"parcel SPI {spi}"
        else:
            return

        try:
            res = self.sde.count_properties_for_parcel(
                ident, self.lga_code, by_spi=by_spi,
            )
        except Exception as exc:
            logger.warning("SDE count_properties_for_parcel failed: %s", exc)
            return

        if res.get("multiple"):
            result.issues.append(Issue(
                field="parcel_pfi" if not by_spi else "spi",
                severity="warning",
                message=(
                    f"{label} links to {res.get('count')} distinct properties "
                    f"in Vicmap. VES rejects this with 'Cannot Determine "
                    f"Property Pfi > 1 Property Found For Parcel Identifier' — "
                    f"a parcel identifier can only be used when it maps to a "
                    f"single property. This is also the signature of a "
                    f"subdivided parent being re-added to its child lots."
                ),
                suggested_fix=(
                    "Identify the specific property with prop_pfi/propnum "
                    "instead of the parcel identifier, or confirm this is not "
                    "a retired parent being re-added. Needs human review."
                ),
                rule="parcel_links_to_multiple_properties",
            ))
        result.rules_fired.append("parcel_links_to_multiple_properties")

    def _rule_prop_pfi_exists(self, row, result: RuleResult) -> None:
        """VES: "Property Identifier has no matches". If the row supplies a
        property_pfi that isn't in Vicmap PROPERTY_MP, flag it. Warning (not
        REJECT) because a brand-new property may simply lag in SDE.
        """
        prop_pfi = _get(row, "property_pfi")
        if not prop_pfi:
            return

        try:
            res = self.sde.check_prop_pfi_exists(prop_pfi, self.lga_code)
        except Exception as exc:
            logger.warning("SDE check_prop_pfi_exists failed: %s", exc)
            return

        if res.get("exists") is False:
            result.issues.append(Issue(
                field="property_pfi",
                severity="warning",
                message=(
                    f"property_pfi {prop_pfi} has no match in Vicmap "
                    f"PROPERTY_MP for LGA {self.lga_code}. VES rejects with "
                    f"'Property Identifier has no matches'. It may be a "
                    f"view_pfi, a stale pfi, or a not-yet-loaded new property."
                ),
                suggested_fix=(
                    "Verify the prop_pfi against current Vicmap (LASSI), or "
                    "use propnum + lga_code instead."
                ),
                rule="prop_pfi_exists",
            ))
        result.rules_fired.append("prop_pfi_exists")

    def _rule_complex_address(self, row, result: RuleResult) -> None:
        """VES: "Complex Address managed by Complex site Manager cannot be
        altered". If the target address belongs to a managed complex site
        (ADDRESS.COMPLEX populated), an LGA M1 cannot change it — it must be
        routed to the Vicmap Helpdesk. Warning -> highlight for human review.
        """
        address_pfi = _get(row, "address_pfi")
        propnum = _get(row, "propnum")
        if not address_pfi and not propnum:
            return

        try:
            res = self.sde.check_complex_address(
                address_pfi=address_pfi or None,
                propnum=propnum or None,
                lga_code=self.lga_code,
            )
        except Exception as exc:
            logger.warning("SDE check_complex_address failed: %s", exc)
            return

        if res.get("is_complex"):
            name = res.get("complex_name") or "a managed complex site"
            result.issues.append(Issue(
                field="address_pfi" if address_pfi else "propnum",
                severity="warning",
                message=(
                    f"This address belongs to complex site '{name}'. "
                    f"Complex-flagged addresses cannot be altered by a normal "
                    f"LGA M1 — VES rejects with 'Complex Address managed by "
                    f"Complex site Manager cannot be altered'."
                ),
                suggested_fix=(
                    "Do not submit this row in the normal M1. Prepare it "
                    "separately and email the Vicmap Helpdesk "
                    "(Vicmap.help@transport.vic.gov.au) to load it."
                ),
                rule="complex_address",
            ))
        result.rules_fired.append("complex_address")

    def _rule_parent_readd_fanout(
        self, row, result: RuleResult, batch_context: dict[str, Any] | None,
    ) -> None:
        """Cross-row rule: flag a multi-assessment add where the same new
        propnum is being attached to many distinct existing properties — the
        "parent re-add" anti-pattern (a subdivided parent stamped back onto
        every child lot of its plan).

        Needs the fan-out map from ``analyze_batch`` (passed via
        ``batch_context``); without it this rule is a no-op. Warning ->
        highlight for human review, never auto-REJECT.
        """
        if not batch_context:
            return
        if _get(row, "edit_code").upper() != "A":
            return
        propnum = _get(row, "propnum")
        if not propnum:
            return

        info = (batch_context.get("fanout") or {}).get(propnum)
        if not info:
            return
        count = info.get("count", 0)
        if count >= FANOUT_THRESHOLD:
            targets = info.get("targets", [])
            sample = ", ".join(targets[:8]) + ("…" if len(targets) > 8 else "")
            result.issues.append(Issue(
                field="propnum",
                severity="warning",
                message=(
                    f"New propnum {propnum} is being added (edit_code=A) as a "
                    f"multi-assessment to {count} DISTINCT existing properties "
                    f"({sample}). A genuine multi-assessment add attaches to "
                    f"one property; adding the same new propnum to many is the "
                    f"signature of a subdivided parent being re-stamped onto "
                    f"its child lots. Almost certainly should NOT be submitted."
                ),
                suggested_fix=(
                    "Review in Vicmap: confirm whether propnum {0} is a "
                    "retired parent of these properties' plan. If so, DROP all "
                    "{1} of these rows from the M1 — do not submit.".format(
                        propnum, count,
                    )
                ),
                rule="parent_readd_fanout",
            ))
        result.rules_fired.append("parent_readd_fanout")
