"""Offline UBL-TR invoice parser, mathematical auditor, and Excel exporter."""

from .auditor import audit_invoices
from .exporter import export_audit_report_xlsx
from .models import (
    AuditFinding,
    AuditReport,
    InvoiceLineItem,
    InvoiceRecord,
    TaxBreakdown,
)
from .parser import collect_invoices_from_paths, parse_ubl_xml_bytes

__all__ = [
    "AuditFinding",
    "AuditReport",
    "InvoiceLineItem",
    "InvoiceRecord",
    "TaxBreakdown",
    "audit_invoices",
    "collect_invoices_from_paths",
    "export_audit_report_xlsx",
    "parse_ubl_xml_bytes",
]

__version__ = "0.1.0"
