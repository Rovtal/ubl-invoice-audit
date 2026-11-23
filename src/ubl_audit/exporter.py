"""Styled multi-sheet accounting Excel (.xlsx) exporter via XlsxWriter."""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import xlsxwriter

from .i18n import EXPORT_COPY, SHEET_NAMES, STATUS_LABELS, validate_lang
from .models import ZERO, AuditReport


CURRENCY_FMT = "#,##0.00"
RATE_FMT = "0.##"
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _num(value: Decimal) -> float:
    return float(value)


def _safe_text(value: Any) -> str:
    txt = str(value or "")
    if txt and txt != "-" and txt[0] in FORMULA_PREFIXES:
        return "'" + txt
    return txt


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
        "status_pass": wb.add_format(
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
        "status_warn": wb.add_format(
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
        "status_error": wb.add_format(
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
        ws.write_string(row_idx, col_idx, text, fmt)
    _track_widths(widths, headers)


def _apply_widths(ws: Any, widths: List[int]) -> None:
    for col_idx, width in enumerate(widths):
        ws.set_column(col_idx, col_idx, width)


def _write_summary_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any], lang: str) -> None:
    sheets = SHEET_NAMES[lang]
    st = STATUS_LABELS[lang]
    copy = EXPORT_COPY[lang]
    inv_sheet = sheets["invoices"]

    ws = wb.add_worksheet(sheets["summary"])
    ws.write_string(0, 0, copy["summary_title"], fmts["title"])
    ws.write_string(1, 0, copy["summary_subtitle"].format(tolerance=report.tolerance), fmts["subtitle"])

    last_inv_row = max(2, len(report.results) + 1)
    widths = [34, 18, 18]
    _write_header(ws, 3, copy["summary_headers"], fmts["header"], widths)

    formula_map: Dict[str, tuple[Any, str]] = {
        "pass_count": (f'=COUNTIF({inv_sheet}!A2:A{last_inv_row},"{st["pass"]}")', "int"),
        "warn_count": (f'=COUNTIF({inv_sheet}!A2:A{last_inv_row},"{st["warn"]}")', "int"),
        "error_count": (f'=COUNTIF({inv_sheet}!A2:A{last_inv_row},"{st["error"]}")', "int"),
        "parse_errors": (len(report.parse_errors), "int"),
        "line_ext": (f"=SUM({inv_sheet}!L2:L{last_inv_row})", "currency"),
        "allowance": (f"=SUM({inv_sheet}!M2:M{last_inv_row})", "currency"),
        "tax_excl": (f"=SUM({inv_sheet}!N2:N{last_inv_row})", "currency"),
        "tax_total": (f"=SUM({inv_sheet}!O2:O{last_inv_row})", "currency"),
        "withholding": (f"=SUM({inv_sheet}!P2:P{last_inv_row})", "currency"),
        "payable": (f"=SUM({inv_sheet}!R2:R{last_inv_row})", "currency"),
    }

    metric_specs = copy["summary_metrics"]
    for offset, (key, label) in enumerate(metric_specs, start=4):
        val, val_fmt_key = formula_map[key]
        ws.write_string(offset, 0, label, fmts["label_bold"])
        if isinstance(val, str) and val.startswith("="):
            ws.write_formula(offset, 1, val, fmts[val_fmt_key])
        else:
            ws.write_number(offset, 1, val, fmts[val_fmt_key])

    rate_totals: Dict[Decimal, List[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for entry in report.results:
        for tb in entry.invoice.taxes:
            rate_totals[tb.percent][0] += tb.taxable_amount
            rate_totals[tb.percent][1] += tb.tax_amount

    kdv_row = len(metric_specs) + 6
    _write_header(ws, kdv_row, copy["kdv_headers"], fmts["header"], widths)
    for idx, pct in enumerate(sorted(rate_totals.keys()), start=kdv_row + 1):
        matrah_sum, tax_sum = rate_totals[pct]
        ws.write_number(idx, 0, _num(pct), fmts["rate"])
        ws.write_number(idx, 1, _num(matrah_sum), fmts["currency"])
        ws.write_number(idx, 2, _num(tax_sum), fmts["currency"])

    _apply_widths(ws, widths)


def _write_invoices_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any], lang: str) -> None:
    sheets = SHEET_NAMES[lang]
    st = STATUS_LABELS[lang]
    copy = EXPORT_COPY[lang]
    status_fmt_map = {
        st["pass"]: fmts["status_pass"],
        st["warn"]: fmts["status_warn"],
        st["error"]: fmts["status_error"],
    }

    ws = wb.add_worksheet(sheets["invoices"])
    headers = copy["invoice_headers"]
    widths = [10] * len(headers)
    _write_header(ws, 0, headers, fmts["header"], widths)

    for row_idx, entry in enumerate(report.results, start=1):
        inv = entry.invoice
        zebra = row_idx % 2 == 1
        txt_fmt = fmts["text_zebra"] if zebra else fmts["text"]
        cur_fmt = fmts["currency_zebra"] if zebra else fmts["currency"]
        row_values = [
            entry.status,
            _safe_text(inv.issue_date),
            _safe_text(inv.invoice_id),
            _safe_text(inv.ettn),
            _safe_text(inv.profile_id),
            _safe_text(inv.invoice_type_code),
            _safe_text(inv.supplier_vkn),
            _safe_text(inv.supplier_name),
            _safe_text(inv.customer_vkn),
            _safe_text(inv.customer_name),
            _safe_text(inv.currency),
            _num(inv.line_extension_amount),
            _num(inv.allowance_total_amount),
            _num(inv.tax_exclusive_amount),
            _num(inv.tax_total_amount),
            _num(inv.withholding_total_amount),
            _num(inv.tax_inclusive_amount),
            _num(inv.payable_amount),
            _safe_text(entry.note_summary),
            _safe_text(inv.source_name),
        ]
        ws.write_string(row_idx, 0, entry.status, status_fmt_map.get(entry.status, txt_fmt))
        for col_idx, val in enumerate(row_values[1:], start=1):
            if 11 <= col_idx <= 17:
                ws.write_number(row_idx, col_idx, val, cur_fmt)
            else:
                ws.write_string(row_idx, col_idx, val, txt_fmt)
        _track_widths(widths, row_values)

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, len(report.results)), len(headers) - 1)
    _apply_widths(ws, widths)


def _write_lines_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any], lang: str) -> None:
    sheets = SHEET_NAMES[lang]
    copy = EXPORT_COPY[lang]

    ws = wb.add_worksheet(sheets["lines"])
    headers = copy["line_headers"]
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
                _safe_text(inv.invoice_id),
                _safe_text(inv.issue_date),
                _safe_text(inv.supplier_name),
                _safe_text(item.line_id),
                _safe_text(item.item_name),
                _num(item.quantity),
                _safe_text(item.unit_code),
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
                    ws.write_string(row_idx, col_idx, val, txt_fmt)
            _track_widths(widths, row_values)
            row_idx += 1

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, row_idx - 1), len(headers) - 1)
    _apply_widths(ws, widths)


def _write_tax_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any], lang: str) -> None:
    sheets = SHEET_NAMES[lang]
    copy = EXPORT_COPY[lang]

    ws = wb.add_worksheet(sheets["tax"])
    headers = copy["tax_headers"]
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
                _safe_text(inv.invoice_id),
                _safe_text(inv.issue_date),
                _safe_text(inv.supplier_name),
                _safe_text(tb.kind),
                _safe_text(tb.tax_type_code),
                _safe_text(tb.tax_name),
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
                    ws.write_string(row_idx, col_idx, val, txt_fmt)
            _track_widths(widths, row_values)
            row_idx += 1

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, row_idx - 1), len(headers) - 1)
    _apply_widths(ws, widths)


def _write_findings_sheet(wb: xlsxwriter.Workbook, report: AuditReport, fmts: Dict[str, Any], lang: str) -> None:
    sheets = SHEET_NAMES[lang]
    st = STATUS_LABELS[lang]
    copy = EXPORT_COPY[lang]
    status_fmt_map = {
        st["pass"]: fmts["status_pass"],
        st["warn"]: fmts["status_warn"],
        st["error"]: fmts["status_error"],
    }

    ws = wb.add_worksheet(sheets["findings"])
    headers = copy["finding_headers"]
    widths = [10] * len(headers)
    _write_header(ws, 0, headers, fmts["header"], widths)

    row_idx = 1
    for err in report.parse_errors:
        err_msg = _safe_text(err.get("error", copy["unknown_error"]))
        err_src = _safe_text(err.get("source", ""))
        row_values = [st["error"], "DOSYA_OKUNAMADI", "-", "-", "-", err_msg, "-", "-", err_src]
        ws.write_string(row_idx, 0, st["error"], fmts["status_error"])
        for col_idx, val in enumerate(row_values[1:], start=1):
            ws.write_string(row_idx, col_idx, val, fmts["text"])
        _track_widths(widths, row_values)
        row_idx += 1

    for finding in report.findings:
        zebra = row_idx % 2 == 1
        txt_fmt = fmts["text_zebra"] if zebra else fmts["text"]
        row_values = [
            finding.severity,
            _safe_text(finding.code),
            _safe_text(finding.invoice_id),
            _safe_text(finding.ettn),
            _safe_text(finding.supplier_name),
            _safe_text(finding.message),
            _safe_text(finding.expected_value),
            _safe_text(finding.actual_value),
            _safe_text(finding.source_name),
        ]
        ws.write_string(row_idx, 0, finding.severity, status_fmt_map.get(finding.severity, txt_fmt))
        for col_idx, val in enumerate(row_values[1:], start=1):
            ws.write_string(row_idx, col_idx, val, txt_fmt)
        _track_widths(widths, row_values)
        row_idx += 1

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(0, row_idx - 1), len(headers) - 1)
    _apply_widths(ws, widths)


def export_audit_report_xlsx(
    report: AuditReport,
    output_path: Path,
    lang: Optional[str] = None,
) -> Path:
    """Write the complete 5-sheet audit workbook to output_path."""
    active_lang = validate_lang(lang or report.lang)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    wb = xlsxwriter.Workbook(
        str(target),
        {"strings_to_formulas": False, "strings_to_urls": False},
    )
    try:
        fmts = _create_formats(wb)
        _write_summary_sheet(wb, report, fmts, active_lang)
        _write_invoices_sheet(wb, report, fmts, active_lang)
        _write_lines_sheet(wb, report, fmts, active_lang)
        _write_tax_sheet(wb, report, fmts, active_lang)
        _write_findings_sheet(wb, report, fmts, active_lang)
    finally:
        wb.close()
    return target
