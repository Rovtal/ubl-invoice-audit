# Security Policy

## Threat Model

`ubl-invoice-audit` processes untrusted `.xml` invoices and nested `.zip` archives locally:

- **Offline-Only Execution:** Zero external network calls or third-party telemetry.
- **XXE & Entity Expansion Guard:** `lxml.etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)`.
- **Archive Safety Limits:** Blocks zip-slip path traversal (`../`, drive letters, absolute entries) and enforces nested ZIP depth (`UBL_AUDIT_MAX_ZIP_DEPTH`), per-entry (`UBL_AUDIT_MAX_ENTRY_MB`), and total uncompressed (`UBL_AUDIT_MAX_TOTAL_MB`) byte caps.
- **Excel Formula Injection (CWE-1236):** Neutralizes leading `=`, `+`, `-`, `@`, `\t`, and `\r` characters in untrusted text fields and disables automatic string-to-formula/URL conversion in `XlsxWriter`.

## Reporting a Vulnerability

Open a private security advisory on GitHub or report reproducible security issues without including confidential client invoices.
