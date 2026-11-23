# Changelog

## 0.2.0 - 2026-11-23

- Added offline Turkish 10-digit `VKN` and 11-digit `TCKN` algorithmic checksum verification via `validate_turkish_tax_id()` and `--verify-tax-id` CLI flag (`SATICI_VKN_SAGLAMA` warning).
- Added `-V` / `--version` CLI flag.
- Added GitHub Actions CI matrix (`Python 3.10–3.12`) running `ruff` strict rules, `pytest`, and EN demo CLI smoke checks.
- Added `SECURITY.md` documenting offline XXE, zip-slip, and CWE-1236 controls.

## 0.1.0 - 2026-11-23

- Initial bilingual (`--lang en` / `--lang tr`) offline UBL-TR invoice parser, `Decimal` math/duplicate auditor, CWE-1236 protected 5-sheet `.xlsx` exporter, and MIT license.
