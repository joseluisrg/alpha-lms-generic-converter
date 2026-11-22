"""Rollback CLI command – restore a job to a previous artifact version."""

import logging
from typing import Optional

import typer

from core.errors import LmsConverterError
from core.logging_conf import setup_logging
from persistence.repositories import rollback_job

logger = logging.getLogger(__name__)


def rollback_command(
    job_id: str = typer.Argument(..., help="Job ID to roll back"),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        "-v",
        help="Manifest version to restore (default: latest available)",
    ),
    owner: str = typer.Option("local", "--owner", help="Job owner"),
    log_level: str = typer.Option(
        "INFO", "--log-level", "-l", help="Console log level: DEBUG, INFO, WARNING, ERROR"
    ),
) -> None:
    """Roll back a job to a previous artifact version."""
    setup_logging(log_level)
    try:
        restored = rollback_job(job_id, version=version, owner=owner)
    except LmsConverterError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Rolled back job {job_id!r}")
    typer.echo(f"  Status:        {restored['status']}")
    typer.echo(f"  Manifest path: {restored.get('manifest_path') or 'N/A'}")
