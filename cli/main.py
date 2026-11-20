"""
LMS Converter CLI - Migrate courses between Open edX and Moodle.

Commands:
- inspect:  Inspect a course and show structure, warnings, and migration readiness
- migrate:  Migrate a course from source LMS to target LMS
- report:   Generate a detailed report for a previous job
- cleanup:  Remove expired jobs and artifacts
- ledger:   Show the immutable provenance ledger for a job
- rollback: Restore a job to a previous artifact version

Usage:
    lms-converter inspect path/to/course.tar.gz --source openedx
    lms-converter migrate path/to/course.mbz --target openedx --output export.tar.gz
    lms-converter cleanup --dry-run
    lms-converter ledger <job_id>
    lms-converter rollback <job_id> [--version N]
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

import typer

from cli.commands import (
    cleanup_command,
    inspect_command,
    ledger_command,
    migrate_command,
    report_command,
    rollback_command,
)
from core.errors import SchemaVersionError
from persistence.repositories import init_db

# Create Typer application with help text
app = typer.Typer(help="LMS Converter - Migrate courses between Open edX and Moodle")


def _version_callback(value: bool) -> None:
    if not value:
        return
    try:
        current = package_version("lms-converter")
    except PackageNotFoundError:
        current = "0.1.0"
    typer.echo(current)
    raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    """
    LMS Converter - Migrate courses between Open edX and Moodle.

    Use 'inspect' to analyze a course and check migration readiness.
    Use 'migrate' to convert a course from one LMS to another.
    """
    try:
        init_db()
    except SchemaVersionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc


# Register commands
app.command("inspect")(inspect_command)
app.command("migrate")(migrate_command)
app.command("report")(report_command)
app.command("cleanup")(cleanup_command)
app.command("ledger")(ledger_command)
app.command("rollback")(rollback_command)

if __name__ == "__main__":
    app()
