"""Ledger CLI command – display the immutable event ledger for a job."""

import logging

import typer

from core.errors import LmsConverterError
from core.logging_conf import setup_logging
from persistence.repositories import get_job_events

logger = logging.getLogger(__name__)


def ledger_command(
    job_id: str = typer.Argument(..., help="Job ID whose ledger to display"),
    owner: str = typer.Option("local", "--owner", help="Job owner"),
    log_level: str = typer.Option(
        "INFO", "--log-level", "-l", help="Console log level: DEBUG, INFO, WARNING, ERROR"
    ),
) -> None:
    """Show the full immutable event ledger for a job."""
    setup_logging(log_level)
    try:
        events = get_job_events(job_id, owner=owner)
    except LmsConverterError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    if not events:
        typer.echo(f"No ledger events found for job {job_id!r}.")
        return

    typer.echo(f"\nLedger for job: {job_id}")
    typer.echo(
        f"{'Event ID':8}  {'Event':<12} {'Step':<25} {'Actor':<10} {'Recorded':<20} {'Output Hash':16}"
    )
    typer.echo("-" * 97)
    for ev in events:
        typer.echo(
            f"{ev['event_id'][:8]}  "
            f"{ev['event']:<12} "
            f"{ev['step']:<25} "
            f"{ev['actor']:<10} "
            f"{ev['recorded_at']:<20} "
            f"{ev['output_hash'][:16]}"
        )
