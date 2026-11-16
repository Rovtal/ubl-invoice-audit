"""XXE-safe UBL-TR XML parser and bounded recursive ZIP collector."""

import io
import logging
import os
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as StdET

from lxml import etree

from .models import ZERO, InvoiceLineItem, InvoiceRecord, TaxBreakdown

logger = logging.getLogger("ubl_audit.parser")

DEFAULT_MAX_ZIP_DEPTH = int(os.environ.get("UBL_AUDIT_MAX_ZIP_DEPTH", "3"))
DEFAULT_MAX_ENTRY_BYTES = int(os.environ.get("UBL_AUDIT_MAX_ENTRY_MB", "25")) * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = int(os.environ.get("UBL_AUDIT_MAX_TOTAL_MB", "250")) * 1024 * 1024


def _local_name(element: etree._Element) -> str:
    tag = element.tag
    if not isinstance(tag, str):
        return ""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _find_child(parent: Optional[etree._Element], name: str) -> Optional[etree._Element]:
    if parent is None:
        return None
    for child in parent:
        if isinstance(child.tag, str) and _local_name(child) == name:
            return child
    return None


def _find_children(parent: Optional[etree._Element], name: str) -> List[etree._Element]:
    if parent is None:
        return []
    return [child for child in parent if isinstance(child.tag, str) and _local_name(child) == name]


def _find_path(parent: Optional[etree._Element], *parts: str) -> Optional[etree._Element]:
    current = parent
    for part in parts:
        current = _find_child(current, part)
        if current is None:
            return None
    return current


def _text_at(parent: Optional[etree._Element], *parts: str) -> str:
    node = _find_path(parent, *parts)
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _to_decimal(raw: str, field_label: str, warnings: List[str]) -> Decimal:
    cleaned = raw.strip()
    if not cleaned:
        return ZERO
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        warnings.append(f"Geçersiz sayısal değer ({field_label}): {cleaned}")
        return ZERO


def _sum_allowance_charges(container: Optional[etree._Element], warnings: List[str], prefix: str) -> Tuple[Decimal, Decimal]:
    allowance = ZERO
    charge = ZERO
    for block in _find_children(container, "AllowanceCharge"):
        indicator = _text_at(block, "ChargeIndicator").lower()
        amount = _to_decimal(_text_at(block, "Amount"), f"{prefix}.AllowanceCharge", warnings)
        if indicator == "true":
            charge += amount
        else:
            allowance += amount
    return allowance, charge


def _extract_party(container: Optional[etree._Element]) -> Tuple[str, str, str]:
    party = _find_child(container, "Party")
    if party is None:
        return "", "", ""

    chosen_id = ""
    chosen_scheme = ""
    for ident in _find_children(party, "PartyIdentification"):
        id_el = _find_child(ident, "ID")
        if id_el is None or not id_el.text:
            continue
        val = id_el.text.strip()
        scheme = str(id_el.get("schemeID") or "").strip().upper()
        if scheme in ("VKN", "TCKN"):
            chosen_id = val
            chosen_scheme = scheme
            break
        if not chosen_id:
            chosen_id = val
            chosen_scheme = scheme

    if chosen_id and not chosen_scheme:
        if len(chosen_id) == 10 and chosen_id.isdigit():
            chosen_scheme = "VKN"
        elif len(chosen_id) == 11 and chosen_id.isdigit():
            chosen_scheme = "TCKN"

    name = _text_at(party, "PartyName", "Name")
    if not name:
        first_name = _text_at(party, "Person", "FirstName")
        family_name = _text_at(party, "Person", "FamilyName")
        name = " ".join(part for part in (first_name, family_name) if part).strip()

    return chosen_id, chosen_scheme, name


def _extract_tax_totals(
    container: Optional[etree._Element],
    tag_name: str,
    kind: str,
    warnings: List[str],
) -> Tuple[Decimal, List[TaxBreakdown]]:
    total = ZERO
    breakdowns: List[TaxBreakdown] = []
    for tax_block in _find_children(container, tag_name):
        total += _to_decimal(_text_at(tax_block, "TaxAmount"), f"{tag_name}.TaxAmount", warnings)
        for sub in _find_children(tax_block, "TaxSubtotal"):
            taxable = _to_decimal(_text_at(sub, "TaxableAmount"), f"{tag_name}.TaxableAmount", warnings)
            tax_amt = _to_decimal(_text_at(sub, "TaxAmount"), f"{tag_name}.SubtotalTaxAmount", warnings)
            pct = _to_decimal(_text_at(sub, "Percent"), f"{tag_name}.Percent", warnings)
            scheme_el = _find_path(sub, "TaxCategory", "TaxScheme")
            type_code = _text_at(scheme_el, "TaxTypeCode") or _text_at(scheme_el, "ID")
            tax_name = _text_at(scheme_el, "Name") or kind
            breakdowns.append(
                TaxBreakdown(
                    kind=kind,
                    tax_type_code=type_code,
                    tax_name=tax_name,
                    taxable_amount=taxable,
                    tax_amount=tax_amt,
                    percent=pct,
                )
            )
    return total, breakdowns


def parse_ubl_xml_bytes(raw_bytes: bytes, source_name: str = "<memory>") -> Optional[InvoiceRecord]:
    """Parse UBL-TR Invoice XML bytes securely without resolving external entities."""
    if not raw_bytes or not raw_bytes.strip():
        raise ValueError("Boş XML içeriği.")

    cleaned_bytes = raw_bytes.lstrip(b"\xef\xbb\xbf \t\r\n")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
        huge_tree=False,
    )
    try:
        root = etree.fromstring(cleaned_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"XML sözdizimi hatası: {exc}") from exc

    if _local_name(root) != "Invoice":
        return None

    warnings: List[str] = []
    supplier_vkn, supplier_scheme, supplier_name = _extract_party(_find_child(root, "AccountingSupplierParty"))
    customer_vkn, customer_scheme, customer_name = _extract_party(_find_child(root, "AccountingCustomerParty"))

    monetary = _find_child(root, "LegalMonetaryTotal")
    header_allowance, header_charge = _sum_allowance_charges(root, warnings, "Header")

    line_ext = _to_decimal(_text_at(monetary, "LineExtensionAmount"), "LineExtensionAmount", warnings)
    allowance_total = _text_at(monetary, "AllowanceTotalAmount")
    charge_total = _text_at(monetary, "ChargeTotalAmount")
    allowance_val = (
        _to_decimal(allowance_total, "AllowanceTotalAmount", warnings)
        if allowance_total
        else header_allowance
    )
    charge_val = (
        _to_decimal(charge_total, "ChargeTotalAmount", warnings)
        if charge_total
        else header_charge
    )
    tax_excl = _to_decimal(_text_at(monetary, "TaxExclusiveAmount"), "TaxExclusiveAmount", warnings)
    tax_incl = _to_decimal(_text_at(monetary, "TaxInclusiveAmount"), "TaxInclusiveAmount", warnings)
    rounding_amt = _to_decimal(_text_at(monetary, "PayableRoundingAmount"), "PayableRoundingAmount", warnings)
    payable_amt = _to_decimal(_text_at(monetary, "PayableAmount"), "PayableAmount", warnings)

    tax_total_amt, taxes = _extract_tax_totals(root, "TaxTotal", "VERGI", warnings)
    withholding_total_amt, withholdings = _extract_tax_totals(root, "WithholdingTaxTotal", "TEVKIFAT", warnings)

    lines: List[InvoiceLineItem] = []
    for line_el in _find_children(root, "InvoiceLine"):
        line_id = _text_at(line_el, "ID")
        item_name = _text_at(line_el, "Item", "Name") or _text_at(line_el, "Item", "Description")
        qty_el = _find_child(line_el, "InvoicedQuantity")
        qty_text = qty_el.text.strip() if qty_el is not None and qty_el.text else ""
        unit_code = str(qty_el.get("unitCode") or "").strip() if qty_el is not None else ""
        qty = _to_decimal(qty_text, f"Line[{line_id}].InvoicedQuantity", warnings)
        price_amt = _to_decimal(_text_at(line_el, "Price", "PriceAmount"), f"Line[{line_id}].Price", warnings)
        line_allow, _ = _sum_allowance_charges(line_el, warnings, f"Line[{line_id}]")
        line_total = _to_decimal(_text_at(line_el, "LineExtensionAmount"), f"Line[{line_id}].LineExtensionAmount", warnings)
        line_tax_amt, line_subtotals = _extract_tax_totals(line_el, "TaxTotal", "VERGI", warnings)
        line_pct = line_subtotals[0].percent if line_subtotals else ZERO

        lines.append(
            InvoiceLineItem(
                line_id=line_id,
                item_name=item_name,
                quantity=qty,
                unit_code=unit_code,
                unit_price=price_amt,
                allowance_amount=line_allow,
                line_extension_amount=line_total,
                tax_percent=line_pct,
                tax_amount=line_tax_amt,
            )
        )

    currency = _text_at(root, "DocumentCurrencyCode") or "TRY"
    if not tax_excl and line_ext:
        tax_excl = line_ext - allowance_val + charge_val

    return InvoiceRecord(
        source_name=source_name,
        ettn=_text_at(root, "UUID"),
        invoice_id=_text_at(root, "ID"),
        issue_date=_text_at(root, "IssueDate"),
        profile_id=_text_at(root, "ProfileID"),
        invoice_type_code=_text_at(root, "InvoiceTypeCode"),
        currency=currency,
        supplier_vkn=supplier_vkn,
        supplier_scheme=supplier_scheme,
        supplier_name=supplier_name,
        customer_vkn=customer_vkn,
        customer_scheme=customer_scheme,
        customer_name=customer_name,
        line_extension_amount=line_ext,
        allowance_total_amount=allowance_val,
        charge_total_amount=charge_val,
        tax_exclusive_amount=tax_excl,
        tax_inclusive_amount=tax_incl,
        payable_rounding_amount=rounding_amt,
        payable_amount=payable_amt,
        tax_total_amount=tax_total_amt,
        withholding_total_amount=withholding_total_amt,
        taxes=taxes,
        withholdings=withholdings,
        lines=lines,
        parse_warnings=warnings,
    )


def _is_unsafe_zip_member(member_name: str) -> bool:
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
        return True
    parts = [part for part in normalized.split("/") if part]
    return ".." in parts


def _read_zip_member_bounded(zf: zipfile.ZipFile, info: zipfile.ZipInfo, budget_state: Dict[str, int]) -> bytes:
    if info.file_size > DEFAULT_MAX_ENTRY_BYTES:
        raise ValueError(f"ZIP girdisi boyut sınırını aşıyor ({info.filename}).")

    chunks: List[bytes] = []
    entry_read = 0
    with zf.open(info, "r") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            entry_read += len(chunk)
            budget_state["total_bytes"] += len(chunk)
            if entry_read > DEFAULT_MAX_ENTRY_BYTES or budget_state["total_bytes"] > DEFAULT_MAX_TOTAL_BYTES:
                raise ValueError(f"ZIP toplam açılmış veri sınırı aşıldı ({info.filename}).")
            chunks.append(chunk)
    return b"".join(chunks)


def _collect_from_zip_bytes(
    raw_zip: bytes,
    archive_label: str,
    depth: int,
    invoices: List[InvoiceRecord],
    parse_errors: List[Dict[str, str]],
    budget_state: Dict[str, int],
) -> None:
    if depth > DEFAULT_MAX_ZIP_DEPTH:
        parse_errors.append({"source": archive_label, "error": "İç içe ZIP derinlik sınırı aşıldı."})
        return

    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip), "r") as zf:
            for info in sorted(zf.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                if _is_unsafe_zip_member(info.filename):
                    parse_errors.append(
                        {"source": f"{archive_label}!/{info.filename}", "error": "Güvensiz ZIP yol geçişi engellendi."}
                    )
                    continue
                lower_name = info.filename.lower()
                if not (lower_name.endswith(".xml") or lower_name.endswith(".zip")):
                    continue

                nested_label = f"{archive_label}!/{info.filename}"
                try:
                    member_bytes = _read_zip_member_bounded(zf, info, budget_state)
                except (ValueError, zipfile.BadZipFile, RuntimeError) as exc:
                    parse_errors.append({"source": nested_label, "error": str(exc)})
                    continue

                if lower_name.endswith(".zip"):
                    _collect_from_zip_bytes(member_bytes, nested_label, depth + 1, invoices, parse_errors, budget_state)
                else:
                    try:
                        parsed = parse_ubl_xml_bytes(member_bytes, nested_label)
                        if parsed is not None:
                            invoices.append(parsed)
                    except ValueError as exc:
                        parse_errors.append({"source": nested_label, "error": str(exc)})
    except (zipfile.BadZipFile, StdET.ParseError, OSError) as exc:
        parse_errors.append({"source": archive_label, "error": f"ZIP arşivi okunamadı: {exc}"})


def collect_invoices_from_paths(input_paths: List[Path]) -> Tuple[List[InvoiceRecord], List[Dict[str, str]]]:
    """Collect UBL-TR invoices from .xml files, .zip archives, and directories."""
    invoices: List[InvoiceRecord] = []
    parse_errors: List[Dict[str, str]] = []
    budget_state = {"total_bytes": 0}
    candidate_files: List[Path] = []

    for raw_path in input_paths:
        resolved = Path(raw_path).resolve()
        if not resolved.exists():
            parse_errors.append({"source": str(raw_path), "error": "Girdi yolu bulunamadı."})
            continue
        if resolved.is_dir():
            for file_path in sorted(resolved.rglob("*")):
                if file_path.is_file() and file_path.suffix.lower() in (".xml", ".zip"):
                    candidate_files.append(file_path)
        elif resolved.is_file():
            candidate_files.append(resolved)

    for file_path in candidate_files:
        suffix = file_path.suffix.lower()
        try:
            file_bytes = file_path.read_bytes()
        except OSError as exc:
            parse_errors.append({"source": str(file_path), "error": f"Dosya okunamadı: {exc}"})
            continue

        if suffix == ".zip":
            _collect_from_zip_bytes(file_bytes, str(file_path), 1, invoices, parse_errors, budget_state)
        elif suffix == ".xml":
            try:
                parsed = parse_ubl_xml_bytes(file_bytes, str(file_path))
                if parsed is not None:
                    invoices.append(parsed)
                else:
                    parse_errors.append({"source": str(file_path), "error": "XML dosyası bir UBL-TR Invoice belgesi değil."})
            except ValueError as exc:
                parse_errors.append({"source": str(file_path), "error": str(exc)})
        else:
            parse_errors.append({"source": str(file_path), "error": f"Desteklenmeyen dosya uzantısı: {suffix}"})

    logger.info("%d fatura ayrıştırıldı, %d dosya/okuma hatası.", len(invoices), len(parse_errors))
    return invoices, parse_errors
