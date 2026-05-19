# M1 form reference

The M1 form is the primary mechanism Victorian Local Government Authorities
(LGAs) use to update property and address information in **Vicmap** — the
State of Victoria's authoritative property/address dataset.

## Authoritative documentation

This project does not republish the M1 specification. Refer to the official
State of Victoria documentation:

- **M1 process landing page:**
  https://www.land.vic.gov.au/maps-and-spatial/data-services/vicmap-helpdesk/m1-process
- **Current version:** M1 V12 (November 2024)
- **Vicmap helpdesk (email):** `vicmap.help@transport.vic.gov.au`

The official PDF on that page covers:

- M1 field definitions (52 columns)
- Edit codes (B, C, E, P, S, Z, A, R)
- M1 Load Reports and common error messages
- VES (Vicmap Editing Service) submission workflow
- SPEAR (Streamlined Planning) integration
- Worked examples for common scenarios (subdivisions, splits, merges,
  multi-assessments, base properties, hotel-style addressing)

## Why we link rather than copy

The State of Victoria maintains the M1 spec; reproducing it here would drift
out of date when the spec is revised. Always treat `land.vic.gov.au` as the
source of truth.

## Column schema (V12, summary)

The 52 columns expected in an M1 CSV are documented in detail at the link
above. The synthetic fixture at `tests/fixtures/sample_m1.csv` follows this
exact schema with fake values.
