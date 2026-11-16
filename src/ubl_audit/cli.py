"""Command-line interface for offline UBL-TR invoice auditing and Excel reporting."""

import argparse
import json
import logging
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

from .auditor import audit_invoices
from .exporter import export_audit_report_xlsx
from .models import AuditReport
from .parser import collect_invoices_from_paths
from .samples import create_demo_dataset


def _load_dotenv_defaults(env_path: Path) -> None:
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, val = stripped.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = val.strip().strip('"').strip("'")
    except OSError:
        pass


def _report_to_dict(report: AuditReport) -> Dict[str, Any]:
    return {
        "summary": {
            "total_files": report.total_files,
            "parsed_invoices": len(report.results),
            "passed": report.passed_count,
            "warnings": report.warning_count,
            "errors": report.error_count,
            "tolerance": str(report.tolerance),
        },
        "parse_errors": report.parse_errors,
        "findings": [
            {
                "severity": item.severity,
                "code": item.code,
                "invoice_id": item.invoice_id,
                "ettn": item.ettn,
                "supplier_name": item.supplier_name,
                "message": item.message,
                "expected_value": item.expected_value,
                "actual_value": item.actual_value,
                "source_name": item.source_name,
            }
            for item in report.findings
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    """Create argument parser for ubl-audit CLI."""
    parser = argparse.ArgumentParser(
        prog="ubl-audit",
        description="Çevrimdışı UBL-TR e-Fatura / e-Arşiv XML ve ZIP denetçisi ve Excel raporlayıcı.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Ayrıntılı günlük çıktısını etkinleştirir.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit_cmd = sub.add_parser("audit", help="Verilen XML, ZIP veya klasörleri denetleyip Excel raporu üretir.")
    audit_cmd.add_argument("inputs", nargs="+", help="XML dosyaları, ZIP arşivleri veya klasör yolları.")
    audit_cmd.add_argument("-o", "--output", required=True, help="Üretilecek .xlsx rapor dosya yolu.")
    audit_cmd.add_argument("--json", dest="json_output", help="İsteğe bağlı JSON denetim özeti çıkış yolu.")
    audit_cmd.add_argument(
        "--tolerance",
        default=os.environ.get("UBL_AUDIT_TOLERANCE", "0.05"),
        help="Kuruş yuvarlama toleransı (varsayılan: 0.05).",
    )
    audit_cmd.add_argument(
        "--fail-on-error",
        action="store_true",
        help="HATA bulgusu veya okuma hatası varsa çıkış kodunu 2 yapar.",
    )

    demo_cmd = sub.add_parser("demo", help="Örnek UBL-TR XML ve iç içe ZIP seti üretip örnek denetim raporu oluşturur.")
    demo_cmd.add_argument(
        "--out-dir",
        default="demo_output",
        help="Örnek faturalar ve raporun kaydedileceği klasör (varsayılan: demo_output).",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point returning POSIX exit status codes."""
    _load_dotenv_defaults(Path.cwd() / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "demo":
        out_dir = Path(args.out_dir).resolve()
        sample_dir = out_dir / "ornek_faturalar"
        create_demo_dataset(sample_dir)
        invoices, parse_errors = collect_invoices_from_paths([sample_dir])
        report = audit_invoices(invoices, parse_errors=parse_errors, tolerance=Decimal("0.05"))
        xlsx_path = out_dir / "ornek_denetim_raporu.xlsx"
        export_audit_report_xlsx(report, xlsx_path)
        print(f"Örnek faturalar oluşturuldu: {sample_dir}")
        print(
            f"Denetim tamamlandı: Toplam={len(report.results)}, "
            f"Geçti={report.passed_count}, Uyarı={report.warning_count}, Hata={report.error_count}"
        )
        print(f"Excel raporu yazıldı: {xlsx_path}")
        return 0

    try:
        tolerance = Decimal(str(args.tolerance))
        if tolerance < 0:
            raise ValueError("Tolerans negatif olamaz.")
    except (InvalidOperation, ValueError) as exc:
        print(f"Geçersiz tolerans değeri: {exc}", file=sys.stderr)
        return 1

    input_paths = [Path(p) for p in args.inputs]
    invoices, parse_errors = collect_invoices_from_paths(input_paths)
    if not invoices and parse_errors:
        for err in parse_errors:
            print(f"Girdi hatası ({err['source']}): {err['error']}", file=sys.stderr)
        return 1

    report = audit_invoices(invoices, parse_errors=parse_errors, tolerance=tolerance)
    out_xlsx = export_audit_report_xlsx(report, Path(args.output))

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Denetim tamamlandı: Toplam={len(report.results)}, "
        f"Geçti={report.passed_count}, Uyarı={report.warning_count}, "
        f"Hata={report.error_count}, Rapor={out_xlsx}"
    )

    if args.fail_on_error and report.error_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
