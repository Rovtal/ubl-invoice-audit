"""Tests for XXE-safe UBL-TR XML parsing and bounded ZIP extraction."""

import io
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from ubl_audit.parser import collect_invoices_from_paths, parse_ubl_xml_bytes
from ubl_audit.samples import build_sample_ubl_xml


class ParserTests(unittest.TestCase):
    """Verify XML/ZIP parsing security and UBL-TR field coverage."""

    def test_parse_valid_company_and_sole_proprietor_xml(self) -> None:
        company_xml = build_sample_ubl_xml(
            invoice_id="RVT20260001",
            ettn="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            issue_date="2026-11-16",
            supplier_vkn="1234567890",
            supplier_name="Anadolu A.Ş.",
            line_amount="1000.00",
            tax_amount="200.00",
            tax_inclusive="1200.00",
            payable_amount="1200.00",
        )
        inv = parse_ubl_xml_bytes(b"\xef\xbb\xbf" + company_xml, "company.xml")
        if inv is None:
            self.fail("company.xml failed to parse")
        self.assertEqual(inv.invoice_id, "RVT20260001")
        self.assertEqual(inv.supplier_scheme, "VKN")
        self.assertEqual(inv.supplier_name, "Anadolu A.Ş.")
        self.assertEqual(inv.payable_amount, Decimal("1200.00"))
        self.assertEqual(len(inv.lines), 1)

        person_xml = build_sample_ubl_xml(
            invoice_id="SHS20260002",
            ettn="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            issue_date="2026-11-16",
            supplier_vkn="10000000146",
            supplier_name="",
            supplier_person=("Deniz", "Yıldız"),
            supplier_scheme="TCKN",
            line_amount="2000.00",
            tax_amount="400.00",
            tax_inclusive="2400.00",
            withholding_amount="200.00",
            withholding_percent="50",
            payable_amount="2200.00",
        )
        inv2 = parse_ubl_xml_bytes(person_xml, "person.xml")
        if inv2 is None:
            self.fail("person.xml failed to parse")
        self.assertEqual(inv2.supplier_scheme, "TCKN")
        self.assertEqual(inv2.supplier_name, "Deniz Yıldız")
        self.assertEqual(inv2.withholding_total_amount, Decimal("200.00"))
        self.assertEqual(inv2.payable_amount, Decimal("2200.00"))

    def test_xxe_entity_is_not_resolved(self) -> None:
        xxe_payload = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///C:/Windows/win.ini">
]>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>&xxe;</cbc:ID>
    <cbc:UUID>cccccccc-cccc-4ccc-8ccc-cccccccccccc</cbc:UUID>
</Invoice>
"""
        inv = parse_ubl_xml_bytes(xxe_payload, "xxe.xml")
        if inv is None:
            self.fail("xxe.xml failed to parse")
        self.assertNotIn("extensions", inv.invoice_id.lower())
        self.assertNotIn("[fonts]", inv.invoice_id.lower())

    def test_nested_zip_and_zip_slip_rejection(self) -> None:
        good_xml = build_sample_ubl_xml(
            invoice_id="ZIP001",
            ettn="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
            issue_date="2026-11-16",
            supplier_vkn="1234567890",
            supplier_name="Zip Tedarik A.Ş.",
            line_amount="500.00",
            tax_amount="100.00",
            tax_inclusive="600.00",
            payable_amount="600.00",
        )
        inner_buf = io.BytesIO()
        with zipfile.ZipFile(inner_buf, "w") as inner_zf:
            inner_zf.writestr("nested/ZIP001.xml", good_xml)

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp_dir = Path(tmp_str)
            outer_zip = tmp_dir / "batch.zip"
            with zipfile.ZipFile(outer_zip, "w") as outer_zf:
                outer_zf.writestr("inner.zip", inner_buf.getvalue())
                outer_zf.writestr("../../evil.xml", good_xml)

            invoices, errors = collect_invoices_from_paths([tmp_dir])
            self.assertEqual(len(invoices), 1)
            self.assertEqual(invoices[0].invoice_id, "ZIP001")
            self.assertEqual(len(errors), 1)
            self.assertIn("yol geçişi", errors[0]["error"].lower())

    def test_malformed_xml_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            parse_ubl_xml_bytes(b"<Invoice><broken", "broken.xml")

    def test_english_parser_error_and_zip_traversal_messages(self) -> None:
        with self.assertRaises(ValueError) as empty_ctx:
            parse_ubl_xml_bytes(b"", "empty.xml", lang="en")
        self.assertIn("empty xml", str(empty_ctx.exception).lower())

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp_dir = Path(tmp_str)
            bad_zip = tmp_dir / "bad.zip"
            with zipfile.ZipFile(bad_zip, "w") as zf:
                zf.writestr("../evil.xml", b"<Invoice/>")
            _, errors = collect_invoices_from_paths([bad_zip], lang="en")
            self.assertEqual(len(errors), 1)
            self.assertIn("path traversal", errors[0]["error"].lower())
