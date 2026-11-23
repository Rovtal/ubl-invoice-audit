"""Realistic synthetic UBL-TR invoice and ZIP archive generator for demos and tests."""

import io
import zipfile
from pathlib import Path
from typing import Dict, List
from xml.sax.saxutils import escape

from .i18n import DEMO_LAYOUT, validate_lang


_SAMPLE_LABELS: dict[str, dict[str, str]] = {
    "tr": {
        "customer_name": "Örnek Alıcı İşletme A.Ş.",
        "item_name": "Danışmanlık ve Veri Otomasyon Hizmeti",
        "withholding_name": "KDV Tevkifatı",
        "sup_0": "Marmara Teknoloji Danışmanlık A.Ş.",
        "sup_1": "Anadolu Tedarik Ticaret A.Ş.",
        "sup_3": "Bozuk Hesap Lojistik Ltd. Şti.",
    },
    "en": {
        "customer_name": "Example Buyer Corp.",
        "item_name": "Consulting and Data Automation Service",
        "withholding_name": "VAT Withholding",
        "sup_0": "Marmara Tech Advisory Inc.",
        "sup_1": "Anatolia Supply Trade Inc.",
        "sup_3": "Faulty Tax Logistics Ltd.",
    },
}


def build_sample_ubl_xml(
    invoice_id: str,
    ettn: str,
    issue_date: str,
    supplier_vkn: str,
    supplier_name: str,
    line_amount: str,
    tax_amount: str,
    tax_inclusive: str,
    payable_amount: str,
    withholding_amount: str = "0.00",
    withholding_percent: str = "0",
    supplier_person: tuple = (),
    supplier_scheme: str = "VKN",
    tax_percent: str = "20",
    extra_tax_subtotal: str = "",
    lang: str = "tr",
) -> bytes:
    """Build a valid or intentionally flawed UBL-TR 1.2 XML document."""
    active_lang = validate_lang(lang)
    labels = _SAMPLE_LABELS[active_lang]
    if supplier_person:
        first_name, family_name = supplier_person
        party_name_xml = (
            f"<cac:Person><cbc:FirstName>{escape(first_name)}</cbc:FirstName>"
            f"<cbc:FamilyName>{escape(family_name)}</cbc:FamilyName></cac:Person>"
        )
    else:
        party_name_xml = f"<cac:PartyName><cbc:Name>{escape(supplier_name)}</cbc:Name></cac:PartyName>"

    withholding_xml = ""
    if withholding_amount != "0.00":
        withholding_xml = f"""
    <cac:WithholdingTaxTotal>
        <cbc:TaxAmount currencyID="TRY">{escape(withholding_amount)}</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="TRY">{escape(tax_amount)}</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="TRY">{escape(withholding_amount)}</cbc:TaxAmount>
            <cbc:Percent>{escape(withholding_percent)}</cbc:Percent>
            <cac:TaxCategory>
                <cac:TaxScheme>
                    <cbc:ID>9015</cbc:ID>
                    <cbc:Name>{escape(labels["withholding_name"])}</cbc:Name>
                    <cbc:TaxTypeCode>9015</cbc:TaxTypeCode>
                </cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:WithholdingTaxTotal>"""

    xml_str = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
    <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
    <cbc:ProfileID>TICARIFATURA</cbc:ProfileID>
    <cbc:ID>{escape(invoice_id)}</cbc:ID>
    <cbc:UUID>{escape(ettn)}</cbc:UUID>
    <cbc:IssueDate>{escape(issue_date)}</cbc:IssueDate>
    <cbc:InvoiceTypeCode>SATIS</cbc:InvoiceTypeCode>
    <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyIdentification>
                <cbc:ID schemeID="{escape(supplier_scheme)}">{escape(supplier_vkn)}</cbc:ID>
            </cac:PartyIdentification>
            {party_name_xml}
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cac:Party>
            <cac:PartyIdentification>
                <cbc:ID schemeID="VKN">9999999999</cbc:ID>
            </cac:PartyIdentification>
            <cac:PartyName>
                <cbc:Name>{escape(labels["customer_name"])}</cbc:Name>
            </cac:PartyName>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="TRY">{escape(tax_amount)}</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="TRY">{escape(line_amount)}</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="TRY">{escape(tax_amount)}</cbc:TaxAmount>
            <cbc:Percent>{escape(tax_percent)}</cbc:Percent>
            <cac:TaxCategory>
                <cac:TaxScheme>
                    <cbc:ID>0015</cbc:ID>
                    <cbc:Name>KDV</cbc:Name>
                    <cbc:TaxTypeCode>0015</cbc:TaxTypeCode>
                </cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>{extra_tax_subtotal}
    </cac:TaxTotal>{withholding_xml}
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="TRY">{escape(line_amount)}</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="TRY">{escape(line_amount)}</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="TRY">{escape(tax_inclusive)}</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="TRY">{escape(payable_amount)}</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="TRY">{escape(line_amount)}</cbc:LineExtensionAmount>
        <cac:Item>
            <cbc:Name>{escape(labels["item_name"])}</cbc:Name>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="TRY">{escape(line_amount)}</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
</Invoice>
"""
    return xml_str.encode("utf-8")


def create_demo_dataset(target_dir: Path, lang: str = "tr") -> List[Path]:
    """Generate deterministic XML and nested ZIP demo fixtures in target_dir."""
    active_lang = validate_lang(lang)
    labels = _SAMPLE_LABELS[active_lang]
    layout = DEMO_LAYOUT[active_lang]
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    f0_clean = build_sample_ubl_xml(
        invoice_id="RVT2026000000000",
        ettn="00000000-0000-4000-8000-000000000000",
        issue_date="2026-11-09",
        supplier_vkn="5566778899",
        supplier_name=labels["sup_0"],
        line_amount="1500.00",
        tax_amount="300.00",
        tax_inclusive="1800.00",
        payable_amount="1800.00",
        lang=active_lang,
    )
    f1 = build_sample_ubl_xml(
        invoice_id="RVT2026000000001",
        ettn="11111111-1111-4111-8111-111111111111",
        issue_date="2026-11-10",
        supplier_vkn="1234567890",
        supplier_name=labels["sup_1"],
        line_amount="1000.00",
        tax_amount="200.00",
        tax_inclusive="1200.00",
        payable_amount="1200.00",
        lang=active_lang,
    )
    f2 = build_sample_ubl_xml(
        invoice_id="SHS2026000000002",
        ettn="22222222-2222-4222-8222-222222222222",
        issue_date="2026-11-11",
        supplier_vkn="10000000146",
        supplier_name="",
        supplier_person=("Deniz", "Demir"),
        supplier_scheme="TCKN",
        line_amount="2000.00",
        tax_amount="400.00",
        tax_inclusive="2400.00",
        withholding_amount="200.00",
        withholding_percent="50",
        payable_amount="2200.00",
        lang=active_lang,
    )
    f3_bad_kdv = build_sample_ubl_xml(
        invoice_id="ERR2026000000003",
        ettn="33333333-3333-4333-8333-333333333333",
        issue_date="2026-11-12",
        supplier_vkn="2233445566",
        supplier_name=labels["sup_3"],
        line_amount="1000.00",
        tax_amount="150.00",
        tax_inclusive="1150.00",
        payable_amount="1150.00",
        lang=active_lang,
    )
    f4_dup_ettn = build_sample_ubl_xml(
        invoice_id="RVT2026000000004",
        ettn="11111111-1111-4111-8111-111111111111",
        issue_date="2026-11-13",
        supplier_vkn="1234567890",
        supplier_name=labels["sup_1"],
        line_amount="500.00",
        tax_amount="100.00",
        tax_inclusive="600.00",
        payable_amount="600.00",
        lang=active_lang,
    )
    f5_probable_dup = build_sample_ubl_xml(
        invoice_id="SHS2026000000009",
        ettn="55555555-5555-4555-8555-555555555555",
        issue_date="2026-11-11",
        supplier_vkn="10000000146",
        supplier_name="",
        supplier_person=("Deniz", "Demir"),
        supplier_scheme="TCKN",
        line_amount="2000.00",
        tax_amount="400.00",
        tax_inclusive="2400.00",
        withholding_amount="200.00",
        withholding_percent="50",
        payable_amount="2200.00",
        lang=active_lang,
    )

    created_paths: List[Path] = []
    direct_files: Dict[str, bytes] = {
        "RVT2026000000000.xml": f0_clean,
        "RVT2026000000001.xml": f1,
        "SHS2026000000002.xml": f2,
    }
    for name, payload in direct_files.items():
        path = target_dir / name
        path.write_bytes(payload)
        created_paths.append(path)

    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w", compression=zipfile.ZIP_DEFLATED) as inner_zf:
        inner_zf.writestr(f"{layout['nested_dir']}/ERR2026000000003.xml", f3_bad_kdv)
        inner_zf.writestr(f"{layout['nested_dir']}/RVT2026000000004.xml", f4_dup_ettn)

    outer_zip_path = target_dir / layout["outer_zip"]
    with zipfile.ZipFile(outer_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as outer_zf:
        outer_zf.writestr(layout["inner_zip"], inner_buf.getvalue())
        outer_zf.writestr("SHS2026000000009.xml", f5_probable_dup)

    created_paths.append(outer_zip_path)
    return created_paths
