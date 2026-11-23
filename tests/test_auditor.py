"""Tests for Decimal mathematical reconciliation and duplicate detection."""

import unittest
from decimal import Decimal

from ubl_audit.auditor import audit_invoices
from ubl_audit.parser import parse_ubl_xml_bytes
from ubl_audit.samples import build_sample_ubl_xml


class AuditorTests(unittest.TestCase):
    """Verify KDV/matrah math checks and duplicate invoice alerts."""

    def test_valid_multi_rate_kdv_passes(self) -> None:
        xml_bytes = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>MLT20260001</cbc:ID>
    <cbc:UUID>11111111-2222-4333-8444-555555555555</cbc:UUID>
    <cbc:IssueDate>2026-11-16</cbc:IssueDate>
    <cbc:DocumentCurrencyCode>TRY</cbc:DocumentCurrencyCode>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyIdentification><cbc:ID schemeID="VKN">1234567890</cbc:ID></cac:PartyIdentification>
            <cac:PartyName><cbc:Name>Çoklu Oran A.Ş.</cbc:Name></cac:PartyName>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="TRY">110.00</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="TRY">1000.00</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="TRY">10.00</cbc:TaxAmount>
            <cbc:Percent>1</cbc:Percent>
            <cac:TaxCategory><cac:TaxScheme><cbc:TaxTypeCode>0015</cbc:TaxTypeCode><cbc:Name>KDV</cbc:Name></cac:TaxScheme></cac:TaxCategory>
        </cac:TaxSubtotal>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="TRY">500.00</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="TRY">100.00</cbc:TaxAmount>
            <cbc:Percent>20</cbc:Percent>
            <cac:TaxCategory><cac:TaxScheme><cbc:TaxTypeCode>0015</cbc:TaxTypeCode><cbc:Name>KDV</cbc:Name></cac:TaxScheme></cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="TRY">1500.00</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="TRY">1500.00</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="TRY">1610.00</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="TRY">1610.00</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="TRY">1000.00</cbc:LineExtensionAmount>
        <cac:Item><cbc:Name>Gıda Kalemi</cbc:Name></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="TRY">1000.00</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
    <cac:InvoiceLine>
        <cbc:ID>2</cbc:ID>
        <cbc:InvoicedQuantity unitCode="C62">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="TRY">500.00</cbc:LineExtensionAmount>
        <cac:Item><cbc:Name>Hizmet Kalemi</cbc:Name></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="TRY">500.00</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
</Invoice>""".encode("utf-8")

        inv = parse_ubl_xml_bytes(xml_bytes, "multi.xml")
        if inv is None:
            self.fail("multi.xml failed to parse")
        report = audit_invoices([inv])
        self.assertEqual(report.passed_count, 1)
        self.assertEqual(report.error_count, 0)
        self.assertEqual(report.warning_count, 0)

    def test_detects_kdv_mismatch_duplicate_ettn_and_probable_duplicate(self) -> None:
        inv_bad_kdv = parse_ubl_xml_bytes(
            build_sample_ubl_xml(
                invoice_id="BAD001",
                ettn="99999999-1111-4111-8111-111111111111",
                issue_date="2026-11-16",
                supplier_vkn="1234567890",
                supplier_name="Satıcı A.Ş.",
                line_amount="1000.00",
                tax_amount="150.00",
                tax_inclusive="1150.00",
                payable_amount="1150.00",
            ),
            "bad.xml",
        )
        inv_dup_1 = parse_ubl_xml_bytes(
            build_sample_ubl_xml(
                invoice_id="DUP001",
                ettn="88888888-1111-4111-8111-111111111111",
                issue_date="2026-11-15",
                supplier_vkn="1122334455",
                supplier_name="Mükerrer A.Ş.",
                line_amount="500.00",
                tax_amount="100.00",
                tax_inclusive="600.00",
                payable_amount="600.00",
            ),
            "dup1.xml",
        )
        inv_dup_2 = parse_ubl_xml_bytes(
            build_sample_ubl_xml(
                invoice_id="DUP002",
                ettn="88888888-1111-4111-8111-111111111111",
                issue_date="2026-11-15",
                supplier_vkn="1122334455",
                supplier_name="Mükerrer A.Ş.",
                line_amount="500.00",
                tax_amount="100.00",
                tax_inclusive="600.00",
                payable_amount="600.00",
            ),
            "dup2.xml",
        )

        if inv_bad_kdv is None or inv_dup_1 is None or inv_dup_2 is None:
            self.fail("Sample audit test invoices failed to parse")
        report = audit_invoices([inv_bad_kdv, inv_dup_1, inv_dup_2], tolerance=Decimal("0.05"))
        codes = {item.code for item in report.findings}
        self.assertIn("VERGI_HESAPLAMA_HATASI", codes)
        self.assertIn("MUKERRER_ETTN", codes)
        self.assertIn("OLASI_CIFT_KAYIT", codes)
        self.assertEqual(report.error_count, 3)
        self.assertEqual(report.findings[0].severity, "HATA")

    def test_english_audit_findings_and_statuses(self) -> None:
        inv_bad = parse_ubl_xml_bytes(
            build_sample_ubl_xml(
                invoice_id="ENBAD001",
                ettn="77777777-1111-4111-8111-111111111111",
                issue_date="2026-11-23",
                supplier_vkn="1234567890",
                supplier_name="Faulty Co.",
                line_amount="1000.00",
                tax_amount="150.00",
                tax_inclusive="1150.00",
                payable_amount="1150.00",
                lang="en",
            ),
            "bad_en.xml",
            lang="en",
        )
        if inv_bad is None:
            self.fail("bad_en.xml failed to parse")
        report = audit_invoices([inv_bad], tolerance=Decimal("0.05"), lang="en")
        self.assertEqual(report.error_count, 1)
        self.assertEqual(report.results[0].status, "ERROR")
        self.assertEqual(report.findings[0].severity, "ERROR")
        self.assertIn("taxable base * rate", report.findings[0].message)
