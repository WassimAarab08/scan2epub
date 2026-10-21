"""The ``scan2epub`` command line interface."""

from __future__ import annotations

import sys

import typer

from scan2epub import __version__
from scan2epub.errors import Scan2EpubError
from scan2epub.logging import configure_logging

__all__ = ["app", "main"]

app = typer.Typer(
    name="scan2epub",
    help=(
        "Convert scanned public-domain books into clean, reflowable EPUB 3 files.\n\n"
        "Everything runs locally by default: no API key and no network access are "
        "needed unless you explicitly ask for a remote engine."
    ),
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="Show the version and exit.", is_eager=True
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
    json_logs: bool = typer.Option(False, "--json-logs", help="Emit machine-readable JSON logs."),
) -> None:
    """Set the global options shared by every command."""
    if version:
        typer.echo(f"scan2epub {__version__}")
        raise typer.Exit
    configure_logging(verbose=verbose, json_logs=json_logs)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit


def main() -> None:
    """Entry point of the console script."""
    try:
        app()
    except Scan2EpubError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:  # pragma: no cover - interactive
        typer.secho("Interrupted.", fg=typer.colors.YELLOW, err=True)
        raise SystemExit(130) from None


def _register_commands() -> None:
    """Import and register every command module."""
    from scan2epub.cli.commands import convert, doctor, serve  # noqa: PLC0415

    app.command(name="convert")(convert.convert)
    app.command(name="doctor")(doctor.doctor)
    app.command(name="serve")(serve.serve)


_register_commands()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
