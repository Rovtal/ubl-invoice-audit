"""Mathematical, KDV/withholding, tax-ID, and duplicate auditor for UBL-TR invoices."""

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

from .i18n import STATUS_LABELS, t, validate_lang
from .models import ZERO, AuditFinding, AuditReport, InvoiceAuditStatus, InvoiceRecord


def _fmt(val: Decimal) -> str:
    return f"{val:.2f}"


def _make_finding(
    invoice: InvoiceRecord,
    severity: str,
    code: str,
    message: str,
    expected_value: str = "",
    actual_value: str = "",
    lang: str = "tr",
) -> AuditFinding:
    return AuditFinding(
        severity=severity,
        code=code,
        source_name=invoice.source_name,
        invoice_id=invoice.invoice_id or t(lang, "audit_no_invoice_id"),
        ettn=invoice.ettn or t(lang, "audit_no_ettn"),
        supplier_name=invoice.supplier_name or t(lang, "audit_no_supplier"),
        message=message,
        expected_value=expected_value,
        actual_value=actual_value,
    )


def _audit_single_invoice(invoice: InvoiceRecord, tolerance: Decimal, lang: str = "tr") -> List[AuditFinding]:
    st = STATUS_LABELS[lang]
    findings: List[AuditFinding] = []

    for warn in invoice.parse_warnings:
        findings.append(_make_finding(invoice, st["warn"], "AYRISTIRMA_UYARISI", warn, lang=lang))

    if not invoice.ettn:
        findings.append(_make_finding(invoice, st["error"], "ETTN_EKSIK", t(lang, "audit_missing_ettn"), lang=lang))

    if not invoice.invoice_id:
        findings.append(_make_finding(invoice, st["error"], "FATURA_NO_EKSIK", t(lang, "audit_missing_id"), lang=lang))

    if not invoice.supplier_vkn or not invoice.supplier_vkn.isdigit():
        findings.append(
            _make_finding(
                invoice,
                st["error"],
                "SATICI_VKN_EKSIK",
                t(lang, "audit_bad_vkn"),
                expected_value=t(lang, "audit_vkn_expected"),
                actual_value=invoice.supplier_vkn or t(lang, "audit_empty"),
                lang=lang,
            )
        )
    elif len(invoice.supplier_vkn) not in (10, 11):
        findings.append(
            _make_finding(
                invoice,
                st["warn"],
                "SATICI_VKN_HANE",
                t(lang, "audit_vkn_len", length=len(invoice.supplier_vkn)),
                expected_value=t(lang, "audit_vkn_len_exp"),
                actual_value=str(len(invoice.supplier_vkn)),
                lang=lang,
            )
        )

    if invoice.lines:
        lines_sum = sum((item.line_extension_amount for item in invoice.lines), ZERO)
        if abs(lines_sum - invoice.line_extension_amount) > tolerance:
            findings.append(
                _make_finding(
                    invoice,
                    st["error"],
                    "KALEM_TOPLAM_TUTARSIZLIGI",
                    t(lang, "audit_lines_mismatch"),
                    expected_value=_fmt(lines_sum),
                    actual_value=_fmt(invoice.line_extension_amount),
                    lang=lang,
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
                st["error"],
                "MATRAH_TUTARSIZLIGI",
                t(lang, "audit_tax_excl_mismatch"),
                expected_value=_fmt(expected_tax_excl),
                actual_value=_fmt(invoice.tax_exclusive_amount),
                lang=lang,
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
                        st["error"],
                        "VERGI_HESAPLAMA_HATASI",
                        t(lang, "audit_tax_calc_err", percent=sub.percent, tax_name=sub.tax_name),
                        expected_value=_fmt(computed_tax),
                        actual_value=_fmt(sub.tax_amount),
                        lang=lang,
                    )
                )
        if abs(tax_sub_sum - invoice.tax_total_amount) > tolerance:
            findings.append(
                _make_finding(
                    invoice,
                    st["error"],
                    "VERGI_TOPLAM_TUTARSIZLIGI",
                    t(lang, "audit_tax_sub_mismatch"),
                    expected_value=_fmt(tax_sub_sum),
                    actual_value=_fmt(invoice.tax_total_amount),
                    lang=lang,
                )
            )

    expected_tax_incl = invoice.tax_exclusive_amount + invoice.tax_total_amount
    if abs(expected_tax_incl - invoice.tax_inclusive_amount) > tolerance:
        findings.append(
            _make_finding(
                invoice,
                st["error"],
                "VERGI_DAHIL_TUTARSIZLIGI",
                t(lang, "audit_tax_incl_mismatch"),
                expected_value=_fmt(expected_tax_incl),
                actual_value=_fmt(invoice.tax_inclusive_amount),
                lang=lang,
            )
        )

    expected_payable = (
        invoice.tax_inclusive_amount - invoice.withholding_total_amount + invoice.payable_rounding_amount
    )
    if abs(expected_payable - invoice.payable_amount) > tolerance:
        findings.append(
            _make_finding(
                invoice,
                st["error"],
                "ODENECEK_TUTAR_HATASI",
                t(lang, "audit_payable_mismatch"),
                expected_value=_fmt(expected_payable),
                actual_value=_fmt(invoice.payable_amount),
                lang=lang,
            )
        )

    return findings


def audit_invoices(
    invoices: List[InvoiceRecord],
    parse_errors: List[Dict[str, str]] | None = None,
    tolerance: Decimal = Decimal("0.05"),
    lang: str = "tr",
) -> AuditReport:
    """Audit all parsed UBL-TR invoices for math, tax, withholding, and duplicates."""
    active_lang = validate_lang(lang)
    st = STATUS_LABELS[active_lang]
    severity_order = {st["error"]: 0, st["warn"]: 1}
    errors_list = list(parse_errors or [])
    per_invoice_findings: Dict[int, List[AuditFinding]] = {
        idx: _audit_single_invoice(inv, tolerance, lang=active_lang) for idx, inv in enumerate(invoices)
    }

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
                        st["error"],
                        "MUKERRER_ETTN",
                        t(active_lang, "audit_dup_ettn", count=len(idxs), sources=sources),
                        expected_value=t(active_lang, "audit_dup_ettn_exp"),
                        actual_value=ettn_key,
                        lang=active_lang,
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
                            st["error"],
                            "MUKERRER_FATURA_NO",
                            t(active_lang, "audit_dup_inv_no", sup_vkn=sup_vkn, inv_id=inv_id),
                            expected_value=t(active_lang, "audit_dup_inv_no_exp"),
                            actual_value=f"{sup_vkn} / {inv_id}",
                            lang=active_lang,
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
                            st["warn"],
                            "OLASI_CIFT_KAYIT",
                            t(
                                active_lang,
                                "audit_probable_dup",
                                sup_vkn=sup_vkn,
                                issue_date=issue_date,
                                amt=_fmt(amt),
                            ),
                            expected_value=t(active_lang, "audit_probable_dup_exp"),
                            actual_value=", ".join(sorted(distinct_ids)),
                            lang=active_lang,
                        )
                    )

    results: List[InvoiceAuditStatus] = []
    all_findings: List[AuditFinding] = []
    for idx, inv in enumerate(invoices):
        item_findings = sorted(per_invoice_findings[idx], key=lambda f: severity_order.get(f.severity, 9))
        has_error = any(f.severity == st["error"] for f in item_findings)
        has_warning = any(f.severity == st["warn"] for f in item_findings)
        status = st["error"] if has_error else (st["warn"] if has_warning else st["pass"])
        results.append(InvoiceAuditStatus(invoice=inv, status=status, findings=item_findings, lang=active_lang))
        all_findings.extend(item_findings)

    all_findings.sort(key=lambda f: (severity_order.get(f.severity, 9), f.invoice_id, f.code))
    return AuditReport(
        results=results,
        findings=all_findings,
        parse_errors=errors_list,
        tolerance=tolerance,
        lang=active_lang,
    )
