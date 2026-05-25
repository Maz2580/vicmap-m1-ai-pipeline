"""Read-only spatial checks against the council's ArcSDE database.

This module is **structurally read-only**. Even if the database user has write
permission, this helper will refuse to execute anything that isn't a clean
SELECT statement: it whitelists the query prefix and blocklists DML / DDL
tokens before running anything. The connection itself is opened with
``readonly=True`` and ``ApplicationIntent=ReadOnly`` as a second layer.

The four checks below directly target the dominant categories of VES
(Vicmap Editing Service) rejections we've observed in production training
data (Greater Shepparton, Oct 2024 – Oct 2025):

    47% — "M1 Road-Locality combination does not exist and not a new road"
    26% — "Original rural address would fall outside property"
    10% — "Parcel has no property link M2 required for fix"
     5% — "Provided Co-ordinates fall outside property"

Catching these in the SDE layer means the AI validator never has to guess
about facts that exist in our own database.

Connection model
----------------
Re-uses the same ``DB_SERVER`` / ``DB_USERNAME`` / ``DB_PASSWORD`` env vars
as ``InfoProdDatabaseHelper`` (the ``sdeadmin`` user already has cross-
database read access on ``vm59``). The target database is configurable via
``SDE_DATABASE`` (default ``SDE``).

Tables queried (read-only)
--------------------------
    [SDE].[SDEADMIN].[PROPERTY_MP]   Vicmap property polygons
    [SDE].[SDEADMIN].[ADDRESS]       Vicmap address layer
    [SDE].[SDEADMIN].[PARCEL_MP]     Vicmap parcel polygons

Column names follow standard Vicmap conventions. If your council's SDE uses
different names, override via the constructor kwargs.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

try:
    import pyodbc
except ImportError as _e:
    pyodbc = None  # type: ignore[assignment]
    _import_error = _e
else:
    _import_error = None


logger = logging.getLogger(__name__)


# Only queries that begin with one of these tokens (after leading whitespace
# and an optional `WITH ... AS (...)` CTE) are allowed.
_ALLOWED_PREFIXES = ("SELECT", "WITH")

# Defense-in-depth: even if a query somehow starts with SELECT, refuse it if
# any DML/DDL/exec token appears anywhere in the body.
_FORBIDDEN_TOKENS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|ALTER|DROP|TRUNCATE|EXEC|EXECUTE|"
    r"CREATE|GRANT|REVOKE|sp_|xp_)\b",
    re.IGNORECASE,
)


class ReadOnlyError(RuntimeError):
    """Raised when a query violates the read-only contract."""


class ReadOnlySDEHelper:
    """Read-only connector to the council's SDE database for Vicmap layers.

    Usage::

        sde = ReadOnlySDEHelper()                 # reads creds + DB from env
        lga = os.getenv("LGA_CODE")               # YOUR council's LGA code
        res = sde.check_road_locality_exists("MAIN STREET", "EXAMPLE LOCALITY", lga)
        if not res["exists"]:
            ...  # row would be rejected by VES
    """

    def __init__(
        self,
        *,
        server: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
        # Column-name overrides — adopters with non-standard Vicmap schemas
        # can supply their own mappings without subclassing.
        col_address: dict | None = None,
        col_property: dict | None = None,
        col_parcel: dict | None = None,
    ):
        if pyodbc is None:
            raise ImportError(
                "pyodbc is required for ReadOnlySDEHelper. "
                f"Original error: {_import_error}"
            )

        self.server = server or os.getenv("DB_SERVER", "")
        self.username = username or os.getenv("DB_USERNAME", "")
        self.password = password or os.getenv("DB_PASSWORD", "")
        self.database = database or os.getenv("SDE_DATABASE", "SDE")

        if not (self.server and self.username and self.password):
            raise ValueError(
                "ReadOnlySDEHelper requires DB_SERVER, DB_USERNAME, DB_PASSWORD "
                "to be set (or passed explicitly)."
            )

        # Column names matched to Greater Shepparton's SDE schema
        # (discovered via INFORMATION_SCHEMA.COLUMNS in 2026-05-20). The
        # Vicmap feature-class columns use ESRI's older short identifiers,
        # not the long names from the M1 V12 spec.
        self.col_address = col_address or {
            "table": "[SDE].[SDEADMIN].[ADDRESS]",
            "pfi": "PFI",
            "pr_pfi": "PR_PFI",          # FK -> PROPERTY_MP.PROP_PFI
            "ezi_address": "EZI_ADD",     # human-readable full address
            "road_name": "ROAD_NAME",
            "locality_name": "LOCALITY",  # NOT "locality_name" — SDE shorter
            "lga_code": "LGA_CODE",
            "is_primary": "IS_PRIMARY",
            # COMPLEX holds the complex-site NAME (e.g. 'KIALLA GARDENS') when
            # the address belongs to a managed complex site, else NULL. A
            # non-empty value means an LGA M1 cannot alter it — see
            # check_complex_address.
            "complex": "COMPLEX",
        }
        self.col_property = col_property or {
            "table": "[SDE].[SDEADMIN].[PROPERTY_MP]",
            "pfi": "PROP_PFI",
            "propnum": "PR_PROPNUM",     # NOT "propnum" — SDE prefixes PR_
            "lga_code": "PR_LGAC",       # NOT "prop_lga_code"
            "status": "PR_STAT",
            "shape": "Shape",            # capital S, rest lowercase
        }
        self.col_parcel = col_parcel or {
            "table": "[SDE].[SDEADMIN].[PARCEL_MP]",
            "parcel_pfi": "PARCEL_PFI",
            "parcel_spi": "PARCEL_SPI",
            "lga_code": "PC_LGAC",       # NOT "parcel_lga_code"
            "shape": "Shape",
            # NOTE: PARCEL_MP has NO direct prop_pfi FK. To check whether
            # a parcel is linked to a property we have to do a spatial
            # intersection — see check_parcel_has_property below.
        }

        self._connection: Any = None

    # ------------------------------------------------------------------ #
    # Connection / safe-execute primitives                               #
    # ------------------------------------------------------------------ #

    def _connect(self):
        if self._connection is not None:
            return self._connection
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={self.server};"
            f"DATABASE={self.database};"
            f"UID={self.username};"
            f"PWD={self.password};"
            "ApplicationIntent=ReadOnly;"
        )
        # autocommit=False + readonly=True together: any accidental DML
        # cannot commit; the driver will also refuse mutation upfront.
        self._connection = pyodbc.connect(conn_str, autocommit=False, readonly=True)
        logger.info(
            "Connected to SDE database '%s' on %s as %s (read-only).",
            self.database, self.server, self.username,
        )
        return self._connection

    def _safe_execute(self, query: str, params: tuple = ()) -> list[tuple]:
        """Execute a query after verifying it's a clean SELECT.

        Raises ReadOnlyError if the query looks like anything other than a
        plain SELECT / WITH ... SELECT.
        """
        stripped = query.lstrip()
        if not any(stripped.upper().startswith(p) for p in _ALLOWED_PREFIXES):
            raise ReadOnlyError(
                f"ReadOnlySDEHelper refuses to run non-SELECT query: "
                f"{stripped[:80]!r}…"
            )
        match = _FORBIDDEN_TOKENS.search(query)
        if match:
            raise ReadOnlyError(
                f"ReadOnlySDEHelper refuses to run query — forbidden token "
                f"{match.group(0)!r}: {stripped[:80]!r}…"
            )

        conn = self._connect()
        cursor = conn.cursor()
        try:
            cursor.execute(query, params)
            return list(cursor.fetchall())
        finally:
            cursor.close()

    def close(self) -> None:
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                self._connection = None

    # ------------------------------------------------------------------ #
    # Public checks                                                      #
    # ------------------------------------------------------------------ #

    def check_road_locality_exists(
        self,
        road_name: str,
        locality_name: str,
        lga_code: str,
        *,
        road_type: str | None = None,
        road_suffix: str | None = None,
    ) -> dict[str, Any]:
        """Does the (road_name [+ road_type [+ road_suffix]], locality_name)
        combination exist in Vicmap ADDRESS?

        Catches the #1 VES rejection class: "M1 Road-Locality combination
        does not exist and not a new road" (9 of 19 observed rejections in
        Sep–Oct 2025 training data).

        VES treats the ROAD type ('ROAD', 'STREET', 'DRIVE', 'COURT', …)
        as part of the road's identity, so 'INDUSTRIAL DRIVE' and
        'INDUSTRIAL ROAD' are *different* roads. When the M1 supplies
        a road_type that doesn't match the road's actual type in Vicmap,
        VES rejects — even though our older query (road_name + locality
        only) would have falsely matched the other variant.
        """
        if not road_name or not locality_name:
            return {"exists": False, "count": 0, "reason": "road_name or locality_name empty"}

        c = self.col_address
        clauses = [
            f"UPPER({c['road_name']}) = UPPER(?)",
            f"UPPER({c['locality_name']}) = UPPER(?)",
            f"{c['lga_code']} = ?",
        ]
        params: list = [road_name, locality_name, lga_code]
        if road_type:
            clauses.append("UPPER(ROAD_TYPE) = UPPER(?)")
            params.append(road_type)
        if road_suffix:
            clauses.append("UPPER(RD_SUF) = UPPER(?)")
            params.append(road_suffix)

        query = (
            f"SELECT COUNT(*) FROM {c['table']} "
            f"WHERE {' AND '.join(clauses)}"
        )
        rows = self._safe_execute(query, tuple(params))
        count = int(rows[0][0]) if rows else 0
        return {
            "exists": count > 0,
            "count": count,
            "reason": None,
            "filters": {
                "road_name": road_name,
                "road_type": road_type,
                "road_suffix": road_suffix,
                "locality_name": locality_name,
                "lga_code": lga_code,
            },
        }

    def lookup_propnum_in_vicmap(
        self,
        propnum: str,
        lga_code: str,
    ) -> dict[str, Any]:
        """Look up a propnum in Vicmap PROPERTY_MP, joined to ADDRESS for the
        primary human-readable address.

        Catches "Property Identifier has no matches".
        """
        if not propnum:
            return {"exists": False, "status": None, "address": None}

        p = self.col_property
        a = self.col_address
        # LEFT JOIN ADDRESS so we still return a row even if the property
        # has no primary address (rare but possible during retirement).
        query = (
            f"SELECT TOP 1 p.{p['propnum']}, p.{p['status']}, a.{a['ezi_address']} "
            f"FROM {p['table']} p "
            f"LEFT JOIN {a['table']} a "
            f"  ON a.{a['pr_pfi']} = p.{p['pfi']} AND a.{a['is_primary']} = 'Y' "
            f"WHERE p.{p['propnum']} = ? AND p.{p['lga_code']} = ?"
        )
        rows = self._safe_execute(query, (propnum, lga_code))
        if not rows:
            return {"exists": False, "status": None, "address": None}
        _, status, address = rows[0]
        return {"exists": True, "status": status, "address": address}

    def check_property_address_is_distance_based(
        self,
        propnum: str,
        lga_code: str,
    ) -> dict[str, Any]:
        """Does this property's current primary address use distance-based
        (rural) numbering?

        Used by the rule engine to flag edit_code=P rows that change the
        parcel set when the property has a rural address — VES will then
        re-compute the rural address point on the new polygon and reject
        the M1 if it falls outside ("Original rural address would fall
        outside property"). This is the dominant rejection category for
        edit_code=P rows in your training data.

        Returns:
            {'distance_based': True/False/None, 'address': '...' | None,
             'reason': str | None}
        """
        if not propnum:
            return {"distance_based": None, "address": None, "reason": "propnum empty"}

        p = self.col_property
        a = self.col_address
        query = (
            f"SELECT TOP 1 a.DIST_FLAG, a.{a['ezi_address']} "
            f"FROM {p['table']} p "
            f"JOIN {a['table']} a "
            f"  ON a.{a['pr_pfi']} = p.{p['pfi']} AND a.{a['is_primary']} = 'Y' "
            f"WHERE p.{p['propnum']} = ? AND p.{p['lga_code']} = ?"
        )
        rows = self._safe_execute(query, (propnum, lga_code))
        if not rows:
            return {
                "distance_based": None,
                "address": None,
                "reason": "no primary address on file for this property",
            }
        dist_flag, address = rows[0]
        return {
            "distance_based": str(dist_flag or "").strip().upper() == "Y",
            "address": address,
            "reason": None,
        }

    def check_parcel_has_property_by_spi(
        self,
        spi: str,
        lga_code: str,
    ) -> dict[str, Any]:
        """Same as check_parcel_has_property but identifies the parcel by
        its SPI (Standard Parcel Identifier, e.g. ``1\\LP212539``) instead
        of its PFI. Used when the M1 row uses SPI not parcel_pfi.
        """
        if not spi:
            return {"exists": False, "linked": False, "reason": "spi empty"}

        pc = self.col_parcel
        pr = self.col_property
        # Same CTE-based spatial-intersection probe, just keyed on PARCEL_SPI.
        query = (
            "WITH parcel_geom AS ("
            f"  SELECT TOP 1 {pc['parcel_spi']} AS spi, {pc['shape']} AS shape "
            f"  FROM {pc['table']} "
            f"  WHERE {pc['parcel_spi']} = ? AND {pc['lga_code']} = ?"
            ") "
            "SELECT pg.spi, "
            f"  (SELECT TOP 1 {pr['pfi']} FROM {pr['table']} "
            f"   WHERE {pr['lga_code']} = ? "
            f"   AND {pr['shape']}.STIntersects(pg.shape) = 1) AS prop_pfi "
            "FROM parcel_geom pg"
        )
        rows = self._safe_execute(query, (spi, lga_code, lga_code))
        if not rows:
            return {
                "exists": False,
                "linked": False,
                "prop_pfi": None,
                "reason": "parcel SPI not found in PARCEL_MP",
            }
        _, prop_pfi = rows[0]
        return {
            "exists": True,
            "linked": prop_pfi is not None,
            "prop_pfi": prop_pfi,
            "reason": None if prop_pfi else "parcel has no property link (M2 required)",
        }

    def check_parcel_has_property(
        self,
        parcel_pfi: str,
        lga_code: str,
    ) -> dict[str, Any]:
        """Is the parcel linked to a property in Vicmap?

        PARCEL_MP has **no** direct FK to PROPERTY_MP — the link is purely
        spatial. We resolve it by checking if any PROPERTY_MP polygon
        intersects this parcel's polygon (CTE-based, so the read-only
        guard accepts it as a SELECT/WITH statement).

        Catches "Parcel has no property link M2 required for fix".
        """
        if not parcel_pfi:
            return {"exists": False, "linked": False, "reason": "parcel_pfi empty"}

        pc = self.col_parcel
        pr = self.col_property
        # Use a CTE to grab the parcel polygon once, then probe for any
        # intersecting property. If the parcel doesn't exist the CTE is
        # empty and the final SELECT returns no rows. If it exists but no
        # property intersects, prop_pfi comes back NULL.
        query = (
            "WITH parcel_geom AS ("
            f"  SELECT TOP 1 {pc['parcel_pfi']} AS pfi, {pc['shape']} AS shape "
            f"  FROM {pc['table']} "
            f"  WHERE {pc['parcel_pfi']} = ? AND {pc['lga_code']} = ?"
            ") "
            "SELECT pg.pfi, "
            f"  (SELECT TOP 1 {pr['pfi']} FROM {pr['table']} "
            f"   WHERE {pr['lga_code']} = ? "
            f"   AND {pr['shape']}.STIntersects(pg.shape) = 1) AS prop_pfi "
            "FROM parcel_geom pg"
        )
        rows = self._safe_execute(query, (parcel_pfi, lga_code, lga_code))
        if not rows:
            return {
                "exists": False,
                "linked": False,
                "prop_pfi": None,
                "reason": "parcel not found in PARCEL_MP",
            }
        _, prop_pfi = rows[0]
        return {
            "exists": True,
            "linked": prop_pfi is not None,
            "prop_pfi": prop_pfi,
            "reason": None if prop_pfi else "parcel has no property link (M2 required)",
        }

    def point_in_property(
        self,
        easting: float,
        northing: float,
        propnum: str,
        lga_code: str,
        *,
        srid: int = 7855,  # GDA2020 MGA55 — Victoria's standard
    ) -> dict[str, Any]:
        """Does (easting, northing) fall within the property polygon for propnum?

        Catches "Original rural address would fall outside property" and
        "Provided Co-ordinates fall outside property".
        """
        if not propnum or easting is None or northing is None:
            return {"inside": None, "reason": "missing inputs"}

        c = self.col_property
        # NB: 'contains' is a SQL Server reserved word so we alias as
        # 'is_inside' instead. STContains returns BIT (0/1) — pyodbc gives
        # us an int that bool() handles.
        query = (
            f"SELECT TOP 1 {c['shape']}.STContains(geometry::Point(?, ?, ?)) AS is_inside "
            f"FROM {c['table']} "
            f"WHERE {c['propnum']} = ? AND {c['lga_code']} = ?"
        )
        rows = self._safe_execute(
            query, (float(easting), float(northing), srid, propnum, lga_code),
        )
        if not rows:
            return {"inside": None, "reason": "property not found"}
        return {"inside": bool(rows[0][0]), "reason": None}

    # ------------------------------------------------------------------ #
    # Additional spec-grounded checks (VES "common load report messages") #
    # ------------------------------------------------------------------ #

    def count_properties_for_parcel(
        self,
        parcel_pfi: str,
        lga_code: str,
        *,
        by_spi: bool = False,
    ) -> dict[str, Any]:
        """How many distinct properties does this parcel link to (spatially)?

        VES message: "Cannot Determine Property Pfi > 1 Property Found For
        Parcel Identifier". The doc rule is explicit: if one parcel is linked
        to 2+ properties you *cannot* use the parcel identifier in the M1.

        This is also the deterministic, per-row cause behind the
        parent-re-add anti-pattern: a subdivided parent's old parcel now
        spatially overlaps many child properties, so the count comes back
        high. Returns the count so the caller can decide.

        Set ``by_spi=True`` to identify the parcel by PARCEL_SPI instead of
        PARCEL_PFI (``parcel_pfi`` then carries the SPI string).
        """
        ident = parcel_pfi
        if not ident:
            return {"count": 0, "exists": False, "reason": "parcel id empty"}

        pc = self.col_parcel
        pr = self.col_property
        key_col = pc["parcel_spi"] if by_spi else pc["parcel_pfi"]
        # CTE grabs the parcel polygon, then COUNT(DISTINCT) the properties
        # whose polygon intersects it. Kept as WITH/SELECT for the read guard.
        query = (
            "WITH parcel_geom AS ("
            f"  SELECT TOP 1 {pc['shape']} AS shape "
            f"  FROM {pc['table']} "
            f"  WHERE {key_col} = ? AND {pc['lga_code']} = ?"
            ") "
            f"SELECT COUNT(DISTINCT pr.{pr['pfi']}) "
            f"FROM {pr['table']} pr, parcel_geom pg "
            f"WHERE pr.{pr['lga_code']} = ? "
            f"  AND pr.{pr['shape']}.STIntersects(pg.shape) = 1"
        )
        rows = self._safe_execute(query, (ident, lga_code, lga_code))
        count = int(rows[0][0]) if rows and rows[0][0] is not None else 0
        return {
            "count": count,
            "exists": count > 0,
            "multiple": count > 1,
            "reason": (
                "parcel links to 2+ properties — cannot use the parcel "
                "identifier in an M1" if count > 1 else None
            ),
        }

    def check_prop_pfi_exists(
        self,
        prop_pfi: str,
        lga_code: str,
    ) -> dict[str, Any]:
        """Does this property PFI exist in Vicmap PROPERTY_MP for this LGA?

        Catches VES message "Property Identifier has no matches" (e.g. the M1
        used a view_pfi or a stale prop_pfi).
        """
        if not prop_pfi:
            return {"exists": None, "reason": "property_pfi empty"}

        p = self.col_property
        query = (
            f"SELECT TOP 1 {p['pfi']} FROM {p['table']} "
            f"WHERE {p['pfi']} = ? AND {p['lga_code']} = ?"
        )
        rows = self._safe_execute(query, (prop_pfi, lga_code))
        return {"exists": bool(rows), "reason": None if rows else "prop_pfi not found"}

    def check_complex_address(
        self,
        *,
        address_pfi: str | None = None,
        propnum: str | None = None,
        lga_code: str | None = None,
    ) -> dict[str, Any]:
        """Is the target address part of a managed complex site?

        VES message: "Complex Address managed by Complex site Manager cannot
        be altered" — these (retirement villages, caravan parks, prisons,
        shopping centres, etc.) carry a non-empty ADDRESS.COMPLEX site name
        and an LGA M1 cannot change them; they must be routed to the Vicmap
        Helpdesk.

        Identify the address either directly by ``address_pfi`` (preferred,
        exact) or by ``propnum`` (joins to the property's primary address).
        Returns ``{'is_complex': bool|None, 'complex_name': str|None}``.
        """
        a = self.col_address
        complex_col = a.get("complex", "COMPLEX")

        if address_pfi:
            query = (
                f"SELECT TOP 1 {complex_col} FROM {a['table']} "
                f"WHERE {a['pfi']} = ?"
            )
            rows = self._safe_execute(query, (address_pfi,))
        elif propnum and lga_code:
            p = self.col_property
            query = (
                f"SELECT TOP 1 a.{complex_col} "
                f"FROM {p['table']} p "
                f"JOIN {a['table']} a "
                f"  ON a.{a['pr_pfi']} = p.{p['pfi']} AND a.{a['is_primary']} = 'Y' "
                f"WHERE p.{p['propnum']} = ? AND p.{p['lga_code']} = ?"
            )
            rows = self._safe_execute(query, (propnum, lga_code))
        else:
            return {
                "is_complex": None,
                "complex_name": None,
                "reason": "need address_pfi or (propnum + lga_code)",
            }

        if not rows:
            return {"is_complex": None, "complex_name": None, "reason": "address not found"}
        name = (rows[0][0] or "").strip() if rows[0][0] is not None else ""
        return {
            "is_complex": bool(name),
            "complex_name": name or None,
            "reason": None,
        }
