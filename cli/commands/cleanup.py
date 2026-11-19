"""Retention cleanup CLI command."""

import typer

from core.retention import cleanup_expired_data


def cleanup_command(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--apply",
        help="Preview removals; pass --apply to delete expired data.",
    ),
    retention_days: int | None = typer.Option(
        None,
        "--retention-days",
        min=1,
        help="Override the configured retention period in days.",
    ),
):
    """Remove expired job records, extracted files, outputs, and uploads."""
    result = cleanup_expired_data(retention_days=retention_days, dry_run=dry_run)
    action = "Would remove" if dry_run else "Removed"
    typer.echo(
        f"{action} {result.jobs} jobs, {result.extracted_paths} extracted paths, "
        f"{result.output_paths} outputs, and {result.upload_sessions} upload sessions."
    )
    if result.skipped_paths:
        typer.echo(f"Skipped {result.skipped_paths} paths outside the managed data directories.")
    if result.failed_paths:
        typer.echo(
            f"Failed to remove {result.failed_paths} paths; they will be retried.",
            err=True,
        )
        raise typer.Exit(1)
