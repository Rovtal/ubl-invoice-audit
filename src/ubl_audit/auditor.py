"""Mathematical, KDV/withholding, tax-ID, and duplicate auditor for UBL-TR invoices."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

from .models import ZERO, AuditFinding, AuditReport, InvoiceAuditStatus, InvoiceRecord


SEVERITY_ORDER = {"HATA": 0, "UYARI": 1}


def _fmt(val: Decimal) -> str:
    return f"{val:.2f}"


def _make_finding(
    invoice: InvoiceRecord,
    severity: str,
    code: str,
    message: str,
    expected_value: str = "",
    actual_value: str = "",
) -> AuditFinding:
    return AuditFinding(
        severity=severity,
        code=code,
        source_name=invoice.source_name,
        invoice_id=invoice.invoice_id or "(Fatura No Yok)",
        ettn=invoice.ettn or "(ETTN Yok)",
        supplier_name=invoice.supplier_name or "(Satıcı Bilinmiyor)",
        message=message,
        expected_value=expected_value,
        actual_value=actual_value,
    )


def _audit_single_invoice(invoice: InvoiceRecord, tolerance: Decimal) -> List[AuditFinding]:
    findings: List[AuditFinding] = []

    for warn in invoice.parse_warnings:
        findings.append(_make_finding(invoice, "UYARI", "AYRISTIRMA_UYARISI", warn))

    if not invoice.ettn:
        findings.append(_make_finding(invoice, "HATA", "ETTN_EKSIK", "Fatura ETTN (UUID) alanı boş."))

    if not invoice.invoice_id:
        findings.append(_make_finding(invoice, "HATA", "FATURA_NO_EKSIK", "Fatura numarası (cbc:ID) boş."))

    if not invoice.supplier_vkn or not invoice.supplier_vkn.isdigit():
        findings.append(
            _make_finding(
                invoice,
                "HATA",
                "SATICI_VKN_EKSIK",
                "Satıcı VKN/TCKN bilgisi eksik veya geçersiz karakter içeriyor.",
                expected_value="10 veya 11 hane rakam",
                actual_value=invoice.supplier_vkn or "(boş)",
            )
        )
    elif len(invoice.supplier_vkn) not in (10, 11):
        findings.append(
            _make_finding(
                invoice,
                "UYARI",
                "SATICI_VKN_HANE",
                f"Satıcı VKN/TCKN uzunluğu beklenen 10/11 haneden farklı ({len(invoice.supplier_vkn)} hane).",
                expected_value="10 veya 11",
                actual_value=str(len(invoice.supplier_vkn)),
            )
        )

    if invoice.lines:
        lines_sum = sum((item.line_extension_amount for item in invoice.lines), ZERO)
        if abs(lines_sum - invoice.line_extension_amount) > tolerance:
            findings.append(
                _make_finding(
                    invoice,
                    "HATA",
                    "KALEM_TOPLAM_TUTARSIZLIGI",
                    "Fatura satır tutarları toplamı ile başlık LineExtensionAmount eşleşmiyor.",
                    expected_value=_fmt(lines_sum),
                    actual_value=_fmt(invoice.line_extension_amount),
                )
            )

    expected_tax_excl = (
        invoice.line_extension_amount - invoice.allowance_total_amount + invoice.charge_total_amount
    )
    if (invoice.line_extension_amount > ZERO or invoice.tax_exclusive_amount > ZERO) and abs(
        expected_tax_excl - invoice.tax_exclusive_amount
    ) > tolerance:
        findings.append(
            _make_finding(
                invoice,
                "HATA",
                "MATRAH_TUTARSIZLIGI",
                "Mal/Hizmet toplamı - İskonto + Artırım ile TaxExclusiveAmount eşleşmiyor.",
                expected_value=_fmt(expected_tax_excl),
                actual_value=_fmt(invoice.tax_exclusive_amount),
            )
        )

    if invoice.taxes:
        tax_sub_sum = ZERO
        for sub in invoice.taxes:
            tax_sub_sum += sub.tax_amount
            computed_tax = (sub.taxable_amount * sub.percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if abs(computed_tax - sub.tax_amount) > tolerance:
                findings.append(
                    _make_finding(
                        invoice,
                        "HATA",
                        "VERGI_HESAPLAMA_HATASI",
                        f"%{sub.percent} oranlı {sub.tax_name} vergisi matrah * oran ile uyuşmuyor.",
                        expected_value=_fmt(computed_tax),
                        actual_value=_fmt(sub.tax_amount),
                    )
                )
        if abs(tax_sub_sum - invoice.tax_total_amount) > tolerance:
            findings.append(
                _make_finding(
                    invoice,
                    "HATA",
                    "VERGI_TOPLAM_TUTARSIZLIGI",
                    "Vergi alt satırları toplamı ile başlık TaxTotal tutarı eşleşmiyor.",
                    expected_value=_fmt(tax_sub_sum),
                    actual_value=_fmt(invoice.tax_total_amount),
                )
            )

    expected_tax_incl = invoice.tax_exclusive_amount + invoice.tax_total_amount
    if abs(expected_tax_incl - invoice.tax_inclusive_amount) > tolerance:
        findings.append(
            _make_finding(
                invoice,
                "HATA",
                "VERGI_DAHIL_TUTARSIZLIGI",
                "Matrah + Toplam Vergi ile TaxInclusiveAmount uyuşmuyor.",
                expected_value=_fmt(expected_tax_incl),
                actual_value=_fmt(invoice.tax_inclusive_amount),
            )
        )

    expected_payable = (
        invoice.tax_inclusive_amount - invoice.withholding_total_amount + invoice.payable_rounding_amount
    )
    if abs(expected_payable - invoice.payable_amount) > tolerance:
        findings.append(
            _make_finding(
                invoice,
                "HATA",
                "ODENECEK_TUTAR_HATASI",
                "Vergiler Dahil - Tevkifat (+ Yuvarlama) ile PayableAmount eşleşmiyor.",
                expected_value=_fmt(expected_payable),
                actual_value=_fmt(invoice.payable_amount),
            )
        )

    return findings


def audit_invoices(
    invoices: List[InvoiceRecord],
    parse_errors: List[Dict[str, str]] | None = None,
    tolerance: Decimal = Decimal("0.05"),
) -> AuditReport:
    """Audit all parsed UBL-TR invoices for math, tax, withholding, and duplicates."""
    errors_list = list(parse_errors or [])
    per_invoice_findings: Dict[int, List[AuditFinding]] = {idx: _audit_single_invoice(inv, tolerance) for idx, inv in enumerate(invoices)}

    ettn_groups: Dict[str, List[int]] = defaultdict(list)
    inv_no_groups: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    probable_dup_groups: Dict[Tuple[str, str, Decimal], List[int]] = defaultdict(list)

    for idx, inv in enumerate(invoices):
        ettn_key = inv.ettn.strip().lower()
        if ettn_key:
            ettn_groups[ettn_key].append(idx)

        id_key = (inv.supplier_vkn.strip(), inv.invoice_id.strip().upper())
        if id_key[0] and id_key[1]:
            inv_no_groups[id_key].append(idx)

        prob_key = (inv.supplier_vkn.strip(), inv.issue_date.strip(), inv.payable_amount)
        if prob_key[0] and prob_key[1] and inv.payable_amount > ZERO:
            probable_dup_groups[prob_key].append(idx)

    for ettn_key, idxs in ettn_groups.items():
        if len(idxs) > 1:
            sources = ", ".join(invoices[i].invoice_id or invoices[i].source_name for i in idxs)
            for idx in idxs:
                per_invoice_findings[idx].append(
                    _make_finding(
                        invoices[idx],
                        "HATA",
                        "MUKERRER_ETTN",
                        f"Aynı ETTN (UUID) {len(idxs)} farklı dosyada tespit edildi ({sources}).",
                        expected_value="Tekil ETTN",
                        actual_value=ettn_key,
                    )
                )

    for (sup_vkn, inv_id), idxs in inv_no_groups.items():
        if len(idxs) > 1:
            distinct_ettns = {invoices[i].ettn.strip().lower() for i in idxs if invoices[i].ettn.strip()}
            if len(distinct_ettns) > 1:
                for idx in idxs:
                    per_invoice_findings[idx].append(
                        _make_finding(
                            invoices[idx],
                            "HATA",
                            "MUKERRER_FATURA_NO",
                            f"Aynı satıcı ({sup_vkn}) için aynı Fatura No ({inv_id}) farklı ETTN ile tekrarlanmış.",
                            expected_value="Tekil Fatura No",
                            actual_value=f"{sup_vkn} / {inv_id}",
                        )
                    )

    for (sup_vkn, issue_date, amt), idxs in probable_dup_groups.items():
        if len(idxs) > 1:
            distinct_ids = {invoices[i].invoice_id.strip().upper() for i in idxs if invoices[i].invoice_id.strip()}
            if len(distinct_ids) > 1:
                for idx in idxs:
                    per_invoice_findings[idx].append(
                        _make_finding(
                            invoices[idx],
                            "UYARI",
                            "OLASI_CIFT_KAYIT",
                            f"Aynı satıcı ({sup_vkn}), tarih ({issue_date}) ve ödenecek tutarda ({_fmt(amt)}) farklı fatura numaraları var.",
                            expected_value="Tekil işlem kontrolü",
                            actual_value=", ".join(sorted(distinct_ids)),
                        )
                    )

    results: List[InvoiceAuditStatus] = []
    all_findings: List[AuditFinding] = []
    for idx, inv in enumerate(invoices):
        item_findings = sorted(per_invoice_findings[idx], key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
        has_error = any(f.severity == "HATA" for f in item_findings)
        has_warning = any(f.severity == "UYARI" for f in item_findings)
        status = "HATA" if has_error else ("UYARI" if has_warning else "GECTI")
        results.append(InvoiceAuditStatus(invoice=inv, status=status, findings=item_findings))
        all_findings.extend(item_findings)

    all_findings.sort(key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.invoice_id, f.code))
    return AuditReport(results=results, findings=all_findings, parse_errors=errors_list, tolerance=tolerance)
