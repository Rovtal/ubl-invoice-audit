"""Command-line interface for offline UBL-TR invoice auditing and Excel reporting."""

import argparse
import json
import logging
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .auditor import audit_invoices
from .exporter import export_audit_report_xlsx
from .i18n import DEMO_LAYOUT, SUPPORTED_LANGS, t, validate_lang
from .models import AuditReport
from .parser import collect_invoices_from_paths
from .samples import create_demo_dataset


def _detect_cli_lang(argv: Optional[List[str]]) -> str:
    args_list = sys.argv[1:] if argv is None else argv
    for idx, arg in enumerate(args_list):
        if arg == "--lang" and idx + 1 < len(args_list):
            candidate = args_list[idx + 1].strip().lower()
            return candidate if candidate in SUPPORTED_LANGS else "tr"
        if arg.startswith("--lang="):
            candidate = arg.split("=", 1)[1].strip().lower()
            return candidate if candidate in SUPPORTED_LANGS else "tr"
    return "tr"


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
        "lang": report.lang,
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


def build_parser(lang: str = "tr") -> argparse.ArgumentParser:
    """Create argument parser for ubl-audit CLI."""
    active_lang = validate_lang(lang)
    parser = argparse.ArgumentParser(
        prog="ubl-audit",
        description=t(active_lang, "cli_desc"),
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--lang",
        choices=SUPPORTED_LANGS,
        default="tr",
        help=t(active_lang, "cli_lang_help"),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help=t(active_lang, "cli_verbose_help"),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit_cmd = sub.add_parser("audit", help=t(active_lang, "cli_audit_help"))
    audit_cmd.add_argument("inputs", nargs="+", help=t(active_lang, "cli_inputs_help"))
    audit_cmd.add_argument("-o", "--output", required=True, help=t(active_lang, "cli_output_help"))
    audit_cmd.add_argument("--json", dest="json_output", help=t(active_lang, "cli_json_help"))
    audit_cmd.add_argument(
        "--tolerance",
        default=os.environ.get("UBL_AUDIT_TOLERANCE", "0.05"),
        help=t(active_lang, "cli_tolerance_help"),
    )
    audit_cmd.add_argument(
        "--fail-on-error",
        action="store_true",
        help=t(active_lang, "cli_fail_help"),
    )
    audit_cmd.add_argument(
        "--verify-tax-id",
        action="store_true",
        help=t(active_lang, "cli_verify_tax_id_help"),
    )
    audit_cmd.add_argument(
        "--lang",
        choices=SUPPORTED_LANGS,
        default=argparse.SUPPRESS,
        help=t(active_lang, "cli_lang_help"),
    )

    demo_cmd = sub.add_parser("demo", help=t(active_lang, "cli_demo_help"))
    demo_cmd.add_argument(
        "--out-dir",
        default="demo_output",
        help=t(active_lang, "cli_demo_outdir_help"),
    )
    demo_cmd.add_argument(
        "--lang",
        choices=SUPPORTED_LANGS,
        default=argparse.SUPPRESS,
        help=t(active_lang, "cli_lang_help"),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point returning POSIX exit status codes."""
    _load_dotenv_defaults(Path.cwd() / ".env")
    hinted_lang = _detect_cli_lang(argv)
    parser = build_parser(lang=hinted_lang)
    args = parser.parse_args(argv)
    active_lang = validate_lang(args.lang)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.command == "demo":
        layout = DEMO_LAYOUT[active_lang]
        out_dir = Path(args.out_dir).resolve()
        sample_dir = out_dir / layout["sample_dir"]
        create_demo_dataset(sample_dir, lang=active_lang)
        invoices, parse_errors = collect_invoices_from_paths([sample_dir], lang=active_lang)
        report = audit_invoices(invoices, parse_errors=parse_errors, tolerance=Decimal("0.05"), lang=active_lang)
        xlsx_path = out_dir / layout["xlsx_name"]
        export_audit_report_xlsx(report, xlsx_path, lang=active_lang)
        print(t(active_lang, "cli_demo_created", sample_dir=sample_dir))
        print(
            t(
                active_lang,
                "cli_demo_done",
                total=len(report.results),
                passed=report.passed_count,
                warn=report.warning_count,
                error=report.error_count,
            )
        )
        print(t(active_lang, "cli_demo_written", xlsx_path=xlsx_path))
        return 0

    try:
        tolerance = Decimal(str(args.tolerance))
        if tolerance < 0:
            raise ValueError(t(active_lang, "cli_neg_tolerance"))
    except (InvalidOperation, ValueError) as exc:
        print(t(active_lang, "cli_bad_tolerance", exc=exc), file=sys.stderr)
        return 1

    input_paths = [Path(p) for p in args.inputs]
    invoices, parse_errors = collect_invoices_from_paths(input_paths, lang=active_lang)
    if not invoices and parse_errors:
        for err in parse_errors:
            print(t(active_lang, "cli_input_error", source=err["source"], error=err["error"]), file=sys.stderr)
        return 1

    report = audit_invoices(
        invoices,
        parse_errors=parse_errors,
        tolerance=tolerance,
        lang=active_lang,
        verify_tax_id=args.verify_tax_id,
    )
    out_xlsx = export_audit_report_xlsx(report, Path(args.output), lang=active_lang)

    if args.json_output:
        json_path = Path(args.json_output)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        t(
            active_lang,
            "cli_audit_done",
            total=len(report.results),
            passed=report.passed_count,
            warn=report.warning_count,
            error=report.error_count,
            out_xlsx=out_xlsx,
        )
    )

    if args.fail_on_error and report.error_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
