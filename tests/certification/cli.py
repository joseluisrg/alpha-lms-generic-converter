"""Command-line entry point for LMS certification runs."""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from tests.certification.factory import build_target
from tests.certification.models import ReportStatus
from tests.certification.plan import CertificationPlan, PlanError, build_plan
from tests.certification.runner import run_certification, write_report
from tests.certification.targets import CertificationUnavailable, TargetFactory

DEFAULT_OUTPUT = Path("data/reports/certification-results.json")
DEFAULT_WORKSPACE = Path("data/certification")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("all", "moodle", "openedx"),
        default="all",
        help="Limit the run to one target (default: all).",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Limit the run to one golden case id; may be repeated.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Report path (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Artifact workspace; defaults to a temporary directory.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Persist artifacts under data/certification when --workspace is omitted.",
    )
    parser.add_argument("--run-id", help="Override the generated run identifier.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the plan without provisioning an LMS.",
    )
    return parser


def _selected_plan(args: argparse.Namespace) -> CertificationPlan:
    plan = build_plan()
    targets = None if args.target == "all" else {args.target}
    case_ids = set(args.case_ids) if args.case_ids else None
    if case_ids is not None:
        unknown = case_ids - plan.case_ids
        if unknown:
            raise PlanError(f"Unknown case id(s): {', '.join(sorted(unknown))}")
    return plan.select(targets=targets, case_ids=case_ids)


def _print_plan(plan: CertificationPlan, stream: TextIO) -> None:
    import_label = "import" if len(plan.imports) == 1 else "imports"
    feature_label = "feature" if plan.feature_count == 1 else "features"
    print(
        f"Certification plan: {len(plan.imports)} {import_label}, "
        f"{plan.feature_count} {feature_label}, matrix v{plan.matrix_version}",
        file=stream,
    )
    for planned in plan.imports:
        environment = planned.environment
        print(
            f"- {planned.case_id} -> {planned.target} "
            f"({environment.release} {environment.patch}, "
            f"{planned.feature_count} features)",
            file=stream,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    target_factory: TargetFactory | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        plan = _selected_plan(args)
    except PlanError as exc:
        print(f"Invalid certification plan: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        _print_plan(plan, sys.stdout)
        return 0

    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    workspace = args.workspace
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if workspace is None:
        if args.keep_artifacts:
            workspace = DEFAULT_WORKSPACE / run_id
        else:
            temporary = tempfile.TemporaryDirectory(prefix="lms-certification-")
            workspace = Path(temporary.name)

    try:
        factory = target_factory or (lambda name: build_target(name, run_id=run_id))
        report = run_certification(
            plan,
            workspace,
            factory,
            run_id=run_id,
        )
    except CertificationUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            temporary.cleanup()

    write_report(report, args.output)
    print(
        f"Certification {report.status.value}: "
        f"{report.summary.cases_passed}/{report.summary.cases_total} imports passed, "
        f"{report.summary.features_verified}/{report.summary.features_total} features verified"
    )
    return 0 if report.status == ReportStatus.PASSED else 1
