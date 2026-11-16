"""Styled multi-sheet accounting Excel (.xlsx) exporter via XlsxWriter."""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

import xlsxwriter

from .models import ZERO, AuditReport


CURRENCY_FMT = "#,##0.00"
RATE_FMT = "0.##"


def _num(value: Decimal) -> float:
    return float(value)


def _create_formats(wb: xlsxwriter.Workbook) -> Dict[str, Any]:
    base_font = {"font_name": "Calibri", "font_size": 10}
    border = 1
    border_color = "#D1D5DB"

    return {
        "title": wb.add_format({"font_name": "Calibri", "font_size": 14, "bold": True, "font_color": "#111827"}),
        "subtitle": wb.add_format({"font_name": "Calibri", "font_size": 10, "italic": True, "font_color": "#4B5563"}),
        "header": wb.add_format(
            {
                "font_name": "Calibri",
                "font_size": 11,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#1F2937",
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "border": border,
                "border_color": border_color,
            }
        ),
        "text": wb.add_format({**base_font, "align": "left", "valign": "vcenter", "border": border, "border_color": border_color}),
        "text_zebra": wb.add_format(
            {**base_font, "bg_color": "#F9FAFB", "align": "left", "valign": "vcenter", "border": border, "border_color": border_color}
        ),
        "label_bold": wb.add_format(
            {**base_font, "bold": True, "align": "left", "valign": "vcenter", "border": border, "border_color": border_color}
        ),
        "int": wb.add_format(
            {**base_font, "num_format": "0", "align": "right", "valign": "vcenter", "border": border, "border_color": border_color}
        ),
        "currency": wb.add_format(
            {**base_font, "num_format": CURRENCY_FMT, "align": "right", "valign": "vcenter", "border": border, "border_color": border_color}
        ),
        "currency_zebra": wb.add_format(
            {
                **base_font,
                "bg_color": "#F9FAFB",
                "num_format": CURRENCY_FMT,
                "align": "right",
                "valign": "vcenter",
                "border": border,
                "border_color": border_color,
            }
        ),
        "rate": wb.add_format(
            {**base_font, "num_format": RATE_FMT, "align": "right", "valign": "vcenter", "border": border, "border_color": border_color}
        ),
        "rate_zebra": wb.add_format(
            {
                **base_font,
                "bg_color": "#F9FAFB",
                "num_format": RATE_FMT,
                "align": "right",
                "valign": "vcenter",
                "border": border,
                "border_color": border_color,
            }
        ),
        "status_GECTI": wb.add_format(
            {
                **base_font,
                "bold": True,
                "font_color": "#166534",
                "bg_color": "#DCFCE7",
                "align": "center",
                "valign": "vcenter",
                "border": border,
                "border_color": border_color,
            }
        ),
        "status_UYARI": wb.add_format(
            {
                **base_font,
                "bold": True,
                "font_color": "#92400E",
                "bg_color": "#FEF3C7",
                "align": "center",
                "valign": "vcenter",
                "border": border,
                "border_color": border_color,
            }
        ),
        "status_HATA": wb.add_format(
            {
                **base_font,
                "bold": True,
                "font_color": "#991B1B",
                "bg_color": "#FEE2E2",
                "align": "center",
                "valign": "vcenter",
                "border": border,
                "border_color": border_color,
            }
        ),
    }


def _track_widths(widths: List[int], row_values: List[Any], min_w: int = 10, max_w: int = 44) -> None:
    for idx, val in enumerate(row_values):
        txt = str(val or "")
        if txt.startswith("="):
            widths[idx] = max(widths[idx], 16)
            continue
        for line in txt.splitlines():
            widths[idx] = min(max_w, max(widths[idx], min_w, len(line) + 3))


def _write_header(ws: Any, row_idx: int, headers: List[str], fmt: Any, widths: List[int]) -> None:
    ws.set_row(row_idx, 24)
    for col_idx, text in enumerate(headers):
        ws.write(row_idx, col_idx, text, fmt)
    _track_widths(widths, headers)


def _apply_widths(ws: Any, widths: List[int]) -> None:
    for col_idx, width in enumerate(widths):
        ws.set_column(col_idx, col_idx, width)


def _write_summary_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any]) -> None:
    ws = wb.add_worksheet("Ozet_Denetim")
    ws.write(0, 0, "Çevrimdışı UBL-TR Fatura Denetim ve Muhasebe Raporu", fmts["title"])
    ws.write(
        1,
        0,
        f"KVKK Notu: Tüm XML/ZIP belgeleri %100 yerel bilgisayarda işlenmiştir. Yuvarlama toleransı: {report.tolerance} TL",
        fmts["subtitle"],
    )

    last_inv_row = max(2, len(report.results) + 1)
    widths = [34, 18, 18]
    _write_header(ws, 3, ["Özet Metrik", "Değer"], fmts["header"], widths)

    metrics = [
        ("Geçerli Fatura Sayısı", f'=COUNTIF(Faturalar!A2:A{last_inv_row},"GECTI")', "int"),
        ("Uyarılı Fatura Sayısı", f'=COUNTIF(Faturalar!A2:A{last_inv_row},"UYARI")', "int"),
        ("Hatalı Fatura Sayısı", f'=COUNTIF(Faturalar!A2:A{last_inv_row},"HATA")', "int"),
        ("Okunamayan / Bozuk Dosya Sayısı", len(report.parse_errors), "int"),
        ("Toplam Mal/Hizmet Tutarı", f"=SUM(Faturalar!L2:L{last_inv_row})", "currency"),
        ("Toplam İskonto", f"=SUM(Faturalar!M2:M{last_inv_row})", "currency"),
        ("Toplam Matrah (KDV Hariç)", f"=SUM(Faturalar!N2:N{last_inv_row})", "currency"),
        ("Toplam KDV / Vergi", f"=SUM(Faturalar!O2:O{last_inv_row})", "currency"),
        ("Toplam Tevkifat", f"=SUM(Faturalar!P2:P{last_inv_row})", "currency"),
        ("Toplam Ödenecek Tutar", f"=SUM(Faturalar!R2:R{last_inv_row})", "currency"),
    ]

    for offset, (label, val, val_fmt_key) in enumerate(metrics, start=4):
        ws.write(offset, 0, label, fmts["label_bold"])
        if isinstance(val, str) and val.startswith("="):
            ws.write_formula(offset, 1, val, fmts[val_fmt_key])
        else:
            ws.write_number(offset, 1, val, fmts[val_fmt_key])

    rate_totals: Dict[Decimal, List[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for entry in report.results:
        for tb in entry.invoice.taxes:
            rate_totals[tb.percent][0] += tb.taxable_amount
            rate_totals[tb.percent][1] += tb.tax_amount

    kdv_row = len(metrics) + 6
    _write_header(ws, kdv_row, ["KDV Oranı %", "Toplam Matrah", "Toplam Vergi"], fmts["header"], widths)
    for idx, pct in enumerate(sorted(rate_totals.keys()), start=kdv_row + 1):
        matrah_sum, tax_sum = rate_totals[pct]
        ws.write_number(idx, 0, _num(pct), fmts["rate"])
        ws.write_number(idx, 1, _num(matrah_sum), fmts["currency"])
        ws.write_number(idx, 2, _num(tax_sum), fmts["currency"])

    _apply_widths(ws, widths)


def _write_invoices_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any]) -> None:
    ws = wb.add_worksheet("Faturalar")
    headers = [
        "Durum",
        "Tarih",
        "Fatura No",
        "ETTN (UUID)",
        "Profil",
        "Tip",
        "Satıcı VKN/TCKN",
        "Satıcı Ünvan",
        "Alıcı VKN/TCKN",
        "Alıcı Ünvan",
        "Para Birimi",
        "Mal/Hizmet Toplam",
        "İskonto",
        "Matrah (KDV Hariç)",
        "KDV / Vergi",
        "Tevkifat",
        "Vergiler Dahil",
        "Ödenecek Tutar",
        "Denetim Notu",
        "Kaynak Dosya",
    ]
    widths = [10] * len(headers)
    _write_header(ws, 0, headers, fmts["header"], widths)

    for row_idx, entry in enumerate(report.results, start=1):
        inv = entry.invoice
        zebra = row_idx % 2 == 1
        txt_fmt = fmts["text_zebra"] if zebra else fmts["text"]
        cur_fmt = fmts["currency_zebra"] if zebra else fmts["currency"]
        row_values = [
            entry.status,
            inv.issue_date,
            inv.invoice_id,
            inv.ettn,
            inv.profile_id,
            inv.invoice_type_code,
            inv.supplier_vkn,
            inv.supplier_name,
            inv.customer_vkn,
            inv.customer_name,
            inv.currency,
            _num(inv.line_extension_amount),
            _num(inv.allowance_total_amount),
            _num(inv.tax_exclusive_amount),
            _num(inv.tax_total_amount),
            _num(inv.withholding_total_amount),
            _num(inv.tax_inclusive_amount),
            _num(inv.payable_amount),
            entry.note_summary,
            inv.source_name,
        ]
        ws.write(row_idx, 0, entry.status, fmts.get(f"status_{entry.status}", txt_fmt))
        for col_idx, val in enumerate(row_values[1:], start=1):
            if 11 <= col_idx <= 17:
                ws.write_number(row_idx, col_idx, val, cur_fmt)
            else:
                ws.write(row_idx, col_idx, val, txt_fmt)
        _track_widths(widths, row_values)

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, len(report.results)), len(headers) - 1)
    _apply_widths(ws, widths)


def _write_lines_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any]) -> None:
    ws = wb.add_worksheet("Kalem_Detay")
    headers = [
        "Fatura No",
        "Tarih",
        "Satıcı Ünvan",
        "Satır No",
        "Ürün / Hizmet Adı",
        "Miktar",
        "Birim",
        "Birim Fiyat",
        "Satır İskonto",
        "Satır Tutarı",
        "KDV %",
        "KDV Tutarı",
    ]
    widths = [10] * len(headers)
    _write_header(ws, 0, headers, fmts["header"], widths)

    row_idx = 1
    for entry in report.results:
        inv = entry.invoice
        for item in inv.lines:
            zebra = row_idx % 2 == 1
            txt_fmt = fmts["text_zebra"] if zebra else fmts["text"]
            cur_fmt = fmts["currency_zebra"] if zebra else fmts["currency"]
            rate_fmt = fmts["rate_zebra"] if zebra else fmts["rate"]
            row_values = [
                inv.invoice_id,
                inv.issue_date,
                inv.supplier_name,
                item.line_id,
                item.item_name,
                _num(item.quantity),
                item.unit_code,
                _num(item.unit_price),
                _num(item.allowance_amount),
                _num(item.line_extension_amount),
                _num(item.tax_percent),
                _num(item.tax_amount),
            ]
            for col_idx, val in enumerate(row_values):
                if col_idx in (5, 7, 8, 9, 11):
                    ws.write_number(row_idx, col_idx, val, cur_fmt)
                elif col_idx == 10:
                    ws.write_number(row_idx, col_idx, val, rate_fmt)
                else:
                    ws.write(row_idx, col_idx, val, txt_fmt)
            _track_widths(widths, row_values)
            row_idx += 1

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, row_idx - 1), len(headers) - 1)
    _apply_widths(ws, widths)


def _write_tax_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any]) -> None:
    ws = wb.add_worksheet("KDV_Kirilim")
    headers = [
        "Fatura No",
        "Tarih",
        "Satıcı Ünvan",
        "Tür",
        "Vergi Kodu",
        "Vergi Adı",
        "Oran %",
        "Vergi Matrahı",
        "Vergi / Tevkifat Tutarı",
    ]
    widths = [10] * len(headers)
    _write_header(ws, 0, headers, fmts["header"], widths)

    row_idx = 1
    for entry in report.results:
        inv = entry.invoice
        for tb in inv.taxes + inv.withholdings:
            zebra = row_idx % 2 == 1
            txt_fmt = fmts["text_zebra"] if zebra else fmts["text"]
            cur_fmt = fmts["currency_zebra"] if zebra else fmts["currency"]
            rate_fmt = fmts["rate_zebra"] if zebra else fmts["rate"]
            row_values = [
                inv.invoice_id,
                inv.issue_date,
                inv.supplier_name,
                tb.kind,
                tb.tax_type_code,
                tb.tax_name,
                _num(tb.percent),
                _num(tb.taxable_amount),
                _num(tb.tax_amount),
            ]
            for col_idx, val in enumerate(row_values):
                if col_idx == 6:
                    ws.write_number(row_idx, col_idx, val, rate_fmt)
                elif col_idx in (7, 8):
                    ws.write_number(row_idx, col_idx, val, cur_fmt)
                else:
                    ws.write(row_idx, col_idx, val, txt_fmt)
            _track_widths(widths, row_values)
            row_idx += 1

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, row_idx - 1), len(headers) - 1)
    _apply_widths(ws, widths)


def _write_findings_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any]) -> None:
    ws = wb.add_worksheet("Uyari_ve_Mukerrer")
    headers = [
        "Önem",
        "Bulgu Kodu",
        "Fatura No",
        "ETTN (UUID)",
        "Satıcı Ünvan",
        "Açıklama",
        "Beklenen",
        "Dosyadaki Değer",
        "Kaynak Dosya",
    ]
    widths = [10] * len(headers)
    _write_header(ws, 0, headers, fmts["header"], widths)

    row_idx = 1
    for err in report.parse_errors:
        row_values = ["HATA", "DOSYA_OKUNAMADI", "-", "-", "-", err.get("error", "Bilinmeyen hata"), "-", "-", err.get("source", "")]
        ws.write(row_idx, 0, "HATA", fmts["status_HATA"])
        for col_idx, val in enumerate(row_values[1:], start=1):
            ws.write(row_idx, col_idx, val, fmts["text"])
        _track_widths(widths, row_values)
        row_idx += 1

    for finding in report.findings:
        zebra = row_idx % 2 == 1
        txt_fmt = fmts["text_zebra"] if zebra else fmts["text"]
        row_values = [
            finding.severity,
            finding.code,
            finding.invoice_id,
            finding.ettn,
            finding.supplier_name,
            finding.message,
            finding.expected_value,
            finding.actual_value,
            finding.source_name,
        ]
        ws.write(row_idx, 0, finding.severity, fmts.get(f"status_{finding.severity}", txt_fmt))
        for col_idx, val in enumerate(row_values[1:], start=1):
            ws.write(row_idx, col_idx, val, txt_fmt)
        _track_widths(widths, row_values)
        row_idx += 1

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, row_idx - 1), len(headers) - 1)
    _apply_widths(ws, widths)


def export_audit_report_xlsx(report: AuditReport, output_path: Path) -> Path:
    """Write the complete 5-sheet audit workbook to output_path."""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    wb = xlsxwriter.Workbook(str(target))
    try:
        fmts = _create_formats(wb)
        _write_summary_sheet(wb, report, fmts)
        _write_invoices_sheet(wb, report, fmts)
        _write_lines_sheet(wb, report, fmts)
        _write_tax_sheet(wb, report, fmts)
        _write_findings_sheet(wb, report, fmts)
    finally:
        wb.close()
    return target
