"""EPUB validation with EPUBCheck.

EPUBCheck is a Java tool (BSD-3-Clause). It is never bundled with the Python
package: the validator is looked up in the environment and, when it is not
available, the stage reports that the validation was skipped instead of
failing the run.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ValidationReport", "find_epubcheck", "validate_epub"]

#: Environment variable pointing at the ``epubcheck.jar`` file.
ENV_JAR = "SCAN2EPUB_EPUBCHECK_JAR"

_ERROR_RE = re.compile(r"^(?:ERROR|FATAL)(?:\([A-Z0-9-]+\))?:\s*(.+)$", re.IGNORECASE)
_WARNING_RE = re.compile(r"^(?:WARNING|WARN)(?:\([A-Z0-9-]+\))?:\s*(.+)$", re.IGNORECASE)
_VERSION_RE = re.compile(r"EPUBCheck\s+v?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The outcome of an EPUB validation run."""

    ran: bool = False
    passed: bool = True
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    version: str | None = None
    reason: str | None = None

    @property
    def error_count(self) -> int:
        """Number of reported errors."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Number of reported warnings."""
        return len(self.warnings)


def find_epubcheck() -> Path | None:
    """Locate the EPUBCheck jar or launcher in the environment."""
    configured = os.environ.get(ENV_JAR)
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate
    launcher = shutil.which("epubcheck")
    if launcher:
        return Path(launcher)
    for candidate in (
        Path("/opt/epubcheck/epubcheck.jar"),
        Path("/usr/local/lib/epubcheck/epubcheck.jar"),
        Path.home() / ".cache" / "scan2epub" / "epubcheck.jar",
    ):
        if candidate.is_file():
            return candidate
    return None


def validate_epub(path: Path, *, tool: Path | None = None, timeout: int = 300) -> ValidationReport:
    """Validate an EPUB file.

    Args:
        path: The ``.epub`` file to validate.
        tool: The EPUBCheck jar or launcher. When omitted, it is looked up in
            the environment.
        timeout: Maximum number of seconds allowed for the validation.

    Returns:
        The validation report. ``ran`` is ``False`` when EPUBCheck could not
        be found, in which case the report carries the reason.
    """
    epubcheck = tool or find_epubcheck()
    if epubcheck is None:
        return ValidationReport(
            ran=False,
            passed=True,
            reason=(
                "EPUBCheck was not found. Install it and set "
                f"{ENV_JAR} to validate the generated file."
            ),
        )

    command = _build_command(epubcheck, path)
    # Force the C locale so that the messages are always in English and can
    # be parsed reliably.
    environment = dict(os.environ)
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    try:
        completed = subprocess.run(  # noqa: S603 - the command is built from fixed arguments
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ValidationReport(ran=False, passed=True, reason=f"Could not run EPUBCheck: {exc}")

    output = f"{completed.stdout}\n{completed.stderr}"
    errors: list[str] = []
    warnings: list[str] = []
    messages: list[str] = []
    version: str | None = _tool_version(epubcheck)

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        error_match = _ERROR_RE.match(stripped)
        if error_match:
            errors.append(error_match.group(1))
            continue
        warning_match = _WARNING_RE.match(stripped)
        if warning_match:
            warnings.append(warning_match.group(1))
            continue
        messages.append(stripped)

    return ValidationReport(
        ran=True,
        passed=not errors and completed.returncode == 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
        messages=tuple(messages),
        version=version,
    )


def _build_command(epubcheck: Path, path: Path) -> list[str]:
    """Build the command line used to run EPUBCheck."""
    if epubcheck.suffix == ".jar":
        # The JVM flags force the English locale so that the messages can be
        # parsed reliably, whatever the language of the host.
        return [
            "java",
            "-Duser.language=en",
            "-Duser.country=US",
            "-jar",
            str(epubcheck),
            str(path),
        ]
    return [str(epubcheck), str(path)]


def _tool_version(epubcheck: Path, timeout: int = 60) -> str | None:
    """Return the version of the EPUBCheck installation, if it can be read."""
    if epubcheck.suffix == ".jar":
        command = [
            "java",
            "-Duser.language=en",
            "-Duser.country=US",
            "-jar",
            str(epubcheck),
            "--version",
        ]
    else:
        command = [str(epubcheck), "--version"]
    try:
        completed = subprocess.run(  # noqa: S603 - the command is built from fixed arguments
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - environment
        return None
    match = _VERSION_RE.search(f"{completed.stdout}\n{completed.stderr}")
    return match.group(1) if match else None
