"""Data models for UBL-TR invoice records and audit results."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List


ZERO = Decimal("0.00")


@dataclass
class TaxBreakdown:
    """Represents a single tax or withholding subtotal block from UBL-TR XML."""

    kind: str
    tax_type_code: str
    tax_name: str
    taxable_amount: Decimal
    tax_amount: Decimal
    percent: Decimal


@dataclass
class InvoiceLineItem:
    """Represents a single invoice line from cac:InvoiceLine."""

    line_id: str
    item_name: str
    quantity: Decimal
    unit_code: str
    unit_price: Decimal
    allowance_amount: Decimal
    line_extension_amount: Decimal
    tax_percent: Decimal
    tax_amount: Decimal


@dataclass
class InvoiceRecord:
    """Normalized UBL-TR invoice header, totals, taxes, and line items."""

    source_name: str
    ettn: str
    invoice_id: str
    issue_date: str
    profile_id: str
    invoice_type_code: str
    currency: str
    supplier_vkn: str
    supplier_scheme: str
    supplier_name: str
    customer_vkn: str
    customer_scheme: str
    customer_name: str
    line_extension_amount: Decimal
    allowance_total_amount: Decimal
    charge_total_amount: Decimal
    tax_exclusive_amount: Decimal
    tax_inclusive_amount: Decimal
    payable_rounding_amount: Decimal
    payable_amount: Decimal
    tax_total_amount: Decimal
    withholding_total_amount: Decimal
    taxes: List[TaxBreakdown] = field(default_factory=list)
    withholdings: List[TaxBreakdown] = field(default_factory=list)
    lines: List[InvoiceLineItem] = field(default_factory=list)
    parse_warnings: List[str] = field(default_factory=list)


@dataclass
class AuditFinding:
    """Audit discrepancy or duplicate alert produced for an invoice."""

    severity: str
    code: str
    source_name: str
    invoice_id: str
    ettn: str
    supplier_name: str
    message: str
    expected_value: str = ""
    actual_value: str = ""


@dataclass
class InvoiceAuditStatus:
    """Per-invoice summary outcome combining status badge and joined notes."""

    invoice: InvoiceRecord
    status: str
    findings: List[AuditFinding] = field(default_factory=list)

    @property
    def note_summary(self) -> str:
        if not self.findings:
            return "Tüm matematiksel ve tekillik kontrolleri geçti."
        return " | ".join(f"[{item.severity}] {item.message}" for item in self.findings)


@dataclass
class AuditReport:
    """Complete batch audit summary across parsed and failed inputs."""

    results: List[InvoiceAuditStatus]
    findings: List[AuditFinding]
    parse_errors: List[Dict[str, str]]
    tolerance: Decimal

    @property
    def total_files(self) -> int:
        return len(self.results) + len(self.parse_errors)

    @property
    def passed_count(self) -> int:
        return sum(1 for item in self.results if item.status == "GECTI")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.results if item.status == "UYARI")

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.results if item.status == "HATA") + len(self.parse_errors)
