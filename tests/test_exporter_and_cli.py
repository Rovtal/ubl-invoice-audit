"""End-to-end tests for styled 5-sheet Excel export and CLI commands."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from lxml import etree

from ubl_audit.cli import main
from ubl_audit.samples import build_sample_ubl_xml


NS_SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


class ExporterAndCliTests(unittest.TestCase):
    """Verify Excel workbook structure, formulas, and CLI exit behavior."""

    def test_cli_demo_creates_valid_five_sheet_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            demo_dir = Path(tmp_str) / "demo_run"
            rc = main(["demo", "--out-dir", str(demo_dir)])
            self.assertEqual(rc, 0)

            xlsx_path = demo_dir / "ornek_denetim_raporu.xlsx"
            self.assertTrue(xlsx_path.is_file())

            with zipfile.ZipFile(xlsx_path, "r") as zf:
                wb_xml = etree.fromstring(zf.read("xl/workbook.xml"))
                sheets = [el.get("name") for el in wb_xml.findall(f".//{{{NS_SS}}}sheet")]
                self.assertEqual(
                    sheets,
                    [
                        "Ozet_Denetim",
                        "Faturalar",
                        "Kalem_Detay",
                        "KDV_Kirilim",
                        "Uyari_ve_Mukerrer",
                    ],
                )

                summary_xml = etree.fromstring(zf.read("xl/worksheets/sheet1.xml"))
                formulas = [el.text for el in summary_xml.findall(f".//{{{NS_SS}}}f") if el.text]
                self.assertTrue(any(f.startswith("COUNTIF(Faturalar!") for f in formulas))
                self.assertTrue(any(f.startswith("SUM(Faturalar!") for f in formulas))

                inv_xml = etree.fromstring(zf.read("xl/worksheets/sheet2.xml"))
                inv_rows = inv_xml.findall(f".//{{{NS_SS}}}sheetData/{{{NS_SS}}}row")
                self.assertEqual(len(inv_rows), 7)

                shared_xml = etree.fromstring(zf.read("xl/sharedStrings.xml"))
                shared_texts = ["".join(si.itertext()) for si in shared_xml.findall(f".//{{{NS_SS}}}si")]
                self.assertIn("GECTI", shared_texts)
                self.assertIn("UYARI", shared_texts)
                self.assertIn("HATA", shared_texts)

                findings_xml = etree.fromstring(zf.read("xl/worksheets/sheet5.xml"))
                findings_rows = findings_xml.findall(f".//{{{NS_SS}}}sheetData/{{{NS_SS}}}row")
                self.assertGreaterEqual(len(findings_rows), 4)

    def test_cli_audit_with_json_and_fail_on_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp_dir = Path(tmp_str)
            demo_dir = tmp_dir / "src_demo"
            self.assertEqual(main(["demo", "--out-dir", str(demo_dir)]), 0)

            sample_dir = demo_dir / "ornek_faturalar"
            out_xlsx = tmp_dir / "cikti.xlsx"
            out_json = tmp_dir / "ozet.json"

            rc_fail = main(
                [
                    "audit",
                    str(sample_dir),
                    "-o",
                    str(out_xlsx),
                    "--json",
                    str(out_json),
                    "--fail-on-error",
                ]
            )
            self.assertEqual(rc_fail, 2)
            self.assertTrue(out_xlsx.is_file())
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["parsed_invoices"], 6)
            self.assertEqual(payload["summary"]["passed"], 1)
            self.assertGreaterEqual(payload["summary"]["errors"], 1)

    def test_english_demo_audit_and_cwe1236_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp_dir = Path(tmp_str)
            demo_dir = tmp_dir / "demo_en"
            rc = main(["demo", "--lang", "en", "--out-dir", str(demo_dir)])
            self.assertEqual(rc, 0)

            xlsx_path = demo_dir / "sample_audit_report.xlsx"
            self.assertTrue(xlsx_path.is_file())
            self.assertTrue((demo_dir / "sample_invoices").is_dir())

            with zipfile.ZipFile(xlsx_path, "r") as zf:
                wb_xml = etree.fromstring(zf.read("xl/workbook.xml"))
                sheets = [el.get("name") for el in wb_xml.findall(f".//{{{NS_SS}}}sheet")]
                self.assertEqual(
                    sheets,
                    [
                        "Audit_Summary",
                        "Invoices",
                        "Line_Details",
                        "VAT_Breakdown",
                        "Alerts_and_Duplicates",
                    ],
                )

                summary_xml = etree.fromstring(zf.read("xl/worksheets/sheet1.xml"))
                formulas = [el.text for el in summary_xml.findall(f".//{{{NS_SS}}}f") if el.text]
                self.assertTrue(any('COUNTIF(Invoices!A2:A7,"PASSED")' in f for f in formulas))
                self.assertTrue(any(f.startswith("SUM(Invoices!") for f in formulas))

                shared_xml = etree.fromstring(zf.read("xl/sharedStrings.xml"))
                shared_texts = ["".join(si.itertext()) for si in shared_xml.findall(f".//{{{NS_SS}}}si")]
                self.assertIn("PASSED", shared_texts)
                self.assertIn("WARNING", shared_texts)
                self.assertIn("ERROR", shared_texts)

            # Verify --lang before subcommand and CWE-1236 formula injection protection
            inj_xml = build_sample_ubl_xml(
                invoice_id="INJ001",
                ettn="66666666-6666-4666-8666-666666666666",
                issue_date="2026-11-23",
                supplier_vkn="1234567890",
                supplier_name="=CMD|' /C calc'!A0 Corp",
                line_amount="100.00",
                tax_amount="20.00",
                tax_inclusive="120.00",
                payable_amount="120.00",
                lang="en",
            )
            inj_dir = tmp_dir / "inj_src"
            inj_dir.mkdir()
            (inj_dir / "inj.xml").write_bytes(inj_xml)
            inj_out = tmp_dir / "inj_report.xlsx"
            inj_json = tmp_dir / "inj_summary.json"
            self.assertEqual(
                main(["--lang", "en", "audit", str(inj_dir), "-o", str(inj_out), "--json", str(inj_json)]),
                0,
            )
            inj_payload = json.loads(inj_json.read_text(encoding="utf-8"))
            self.assertEqual(inj_payload["lang"], "en")
            self.assertEqual(inj_payload["summary"]["passed"], 1)

            with zipfile.ZipFile(inj_out, "r") as zf:
                inv_xml = etree.fromstring(zf.read("xl/worksheets/sheet2.xml"))
                self.assertEqual(len(inv_xml.findall(f".//{{{NS_SS}}}f")), 0)
                shared_xml = etree.fromstring(zf.read("xl/sharedStrings.xml"))
                shared_texts = ["".join(si.itertext()) for si in shared_xml.findall(f".//{{{NS_SS}}}si")]
                self.assertTrue(any(txt.startswith("'=") and "CMD|" in txt for txt in shared_texts))

            with self.assertRaises(SystemExit) as bad_lang_ctx:
                main(["demo", "--lang", "de"])
            self.assertEqual(bad_lang_ctx.exception.code, 2)

    def test_cli_version_and_verify_tax_id_flag(self) -> None:
        with self.assertRaises(SystemExit) as ver_ctx:
            main(["--version"])
        self.assertEqual(ver_ctx.exception.code, 0)

        with tempfile.TemporaryDirectory() as tmp_str:
            tmp_dir = Path(tmp_str)
            demo_dir = tmp_dir / "tax_demo"
            self.assertEqual(main(["demo", "--lang", "en", "--out-dir", str(demo_dir)]), 0)

            out_xlsx = tmp_dir / "strict_tax.xlsx"
            out_json = tmp_dir / "strict_tax.json"
            rc = main(
                [
                    "audit",
                    str(demo_dir / "sample_invoices" / "RVT2026000000000.xml"),
                    "-o",
                    str(out_xlsx),
                    "--json",
                    str(out_json),
                    "--lang",
                    "en",
                    "--verify-tax-id",
                ]
            )
            self.assertEqual(rc, 0)
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["warnings"], 1)
            self.assertEqual(payload["findings"][0]["code"], "SATICI_VKN_SAGLAMA")
