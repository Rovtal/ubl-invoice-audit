# ubl-invoice-audit

Language: **English** | [Türkçe](README.tr.md)

A **100% offline** Python CLI tool that parses UBL-TR (`e-Invoice` / `e-Archive`) XML documents and nested ZIP archives, validates line/tax/withholding math using exact `Decimal` arithmetic, isolates duplicate invoices, and exports a styled 5-sheet Excel (`.xlsx`) audit workbook.

> Built for strict local privacy: XML invoices and ZIP batches never leave your machine or touch third-party APIs.

## Key Capabilities

- **Nested ZIP & XXE Protection:** Safely expands nested `.zip` archives in memory with external entity (`XXE`) resolution disabled, zip-slip (`../`) path blocking, depth limits, and decompressed size caps.
- **Exact `Decimal` Reconciliation:** Validates line extensions, allowances/charges, multi-rate VAT subtotals, `TaxTotal`, `WithholdingTaxTotal`, `TaxInclusiveAmount`, and `PayableAmount` without floating-point rounding drift.
- **Duplicate & Anomaly Detection:** Isolates duplicate `ETTN (UUID)` entries, repeated supplier invoice numbers across different ETTNs, and probable duplicate pairs (same supplier, date, and payable total).
- **Corporate & Sole-Proprietor Support:** Handles both `PartyName` (`VKN`) and `Person` (`TCKN`) supplier/customer blocks.
- **CWE-1236 Formula Protection:** Neutralizes leading spreadsheet formula characters (`=`, `+`, `-`, `@`) in untrusted XML text fields during `.xlsx` export.

## Installation & Usage

Requires Python `>=3.10` (`lxml`, `XlsxWriter`):

```powershell
cd ubl-invoice-audit
pip install -e .[dev]
```

Run directly from source without installing (`PowerShell` / `Bash`):

```powershell
$env:PYTHONPATH="src"; python -m ubl_audit.cli demo --lang en --out-dir demo_output
```

```bash
PYTHONPATH=src python -m ubl_audit.cli demo --lang en --out-dir demo_output
```

### 1. Run Sample Demo

```powershell
ubl-audit demo --lang en --out-dir demo_output
```

### 2. Audit Folders, XML Files, or ZIP Archives

Use `--lang en` for English output or omit `--lang` (`tr` default for backward compatibility). Add `--fail-on-error` to return exit code `2` when errors or parse failures are detected:

```powershell
ubl-audit audit .\invoices_dir .\batch.zip -o .\audit_report.xlsx --json .\summary.json --lang en --fail-on-error
```

## 5-Sheet Workbook Output (`--lang en`)

| Sheet Name | Contents |
| --- | --- |
| `Audit_Summary` | Dynamic `COUNTIF` / `SUM` formulas, error counters, and VAT rate totals |
| `Invoices` | Full invoice ledger with status badge, tax IDs, totals, and audit notes |
| `Line_Details` | Line-level quantities, unit prices, allowances, and VAT breakdowns |
| `VAT_Breakdown` | Tax and withholding subtotal ledger per invoice |
| `Alerts_and_Duplicates` | Unreadable files, math discrepancies, duplicate ETTNs, and warnings |

## Tests

```powershell
python -m pytest -v
```

## License

[MIT](LICENSE) — Rovtal
