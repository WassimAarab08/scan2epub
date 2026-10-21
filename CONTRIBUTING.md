# Contributing to scan2epub

Thanks for taking the time to contribute! This document explains how to set up a
development environment, the conventions we follow, and the rules that keep the
project safe (permissive licenses only).

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Table of contents

- [Licensing rules (read this first)](#licensing-rules-read-this-first)
- [Development setup](#development-setup)
- [Quality gates](#quality-gates)
- [Commit conventions](#commit-conventions)
- [Pull request process](#pull-request-process)
- [Adding an OCR engine or text corrector](#adding-an-ocr-engine-or-text-corrector)
- [Adding a dependency](#adding-a-dependency)
- [Code style](#code-style)
- [Reporting bugs](#reporting-bugs)

## Licensing rules (read this first)

`scan2epub` is licensed under **Apache-2.0**. To keep it usable inside
libraries, universities and commercial products, **every** dependency must be
permissive.

**Forbidden:** GPL, AGPL, LGPL-only, SSPL, BUSL, Commons Clause, and any
non-commercial or source-available license — including transitive dependencies
of the packages you add.

Known offenders that must never be added (they are explicitly rejected):

| Package | License |
| --- | --- |
| PyMuPDF / `fitz` | AGPL-3.0 |
| EbookLib | AGPL-3.0 |
| `marker`, `surya` | GPL-3.0 |
| MinerU (non-Pro / community editions) | AGPL-3.0 / non-commercial |

**Before opening a PR that adds a dependency:**

1. Check the license of the package *and* of its runtime dependencies.
2. Add a row to [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
3. Run `uv run python scripts/check_licenses.py` — CI will fail otherwise.
4. Prefer an extra (`[project.optional-dependencies]`) over a hard dependency
   whenever the feature is not needed by every user.

Model weights are **never** vendored into the repository. Reference them by
Hugging Face repository id and document their license in
`THIRD_PARTY_LICENSES.md`.

## Development setup

Requirements: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Git.
Optionally: the `tesseract` binary for the default OCR engine, Node 20+ and
Docker for the web UI and container builds.

```bash
git clone https://github.com/WassimAarab08/scan2epub.git
cd scan2epub

uv sync --all-extras        # install everything, including dev tools
uv run scan2epub --help     # verify the CLI works

# Optional engines
uv sync --extra vlm         # TeleOCR / PaddleOCR-VL (torch + transformers)
uv sync --extra llm         # LiteLLM remote OCR + correction
```

Run the web UI:

```bash
cd web
npm install
npm start                   # http://localhost:4200, proxies to the API
```

## Quality gates

Everything below must pass before a pull request can be merged. The same
commands run in CI.

```bash
uv run ruff format --check .      # formatting
uv run ruff check .               # lint
uv run pyright                    # strict type checking
uv run pytest --cov=src/scan2epub --cov-report=term-missing
```

Type annotations are required and `pyright` runs in **strict** mode. Public
functions and methods need docstrings in the imperative mood ("Return the
...", not "Returns the ...").

Coverage must stay at or above **80 %** for `src/scan2epub/domain` and
`src/scan2epub/application`. New code without tests will fail CI.

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <imperative summary>

<optional body>

<optional footer>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
`build`, `ci`, `chore`, `revert`.

Scopes: `cli`, `api`, `web`, `core`, `ocr`, `correct`, `epub`, `cache`, `eval`,
`docs`, `deps`.

Examples:

```
feat(correct): add normalized edit-distance guardrail
fix(epub): write mimetype as the first uncompressed ZIP entry
docs(readme): add the before/after comparison
test(clean): cover hyphen re-joining across page boundaries
```

Keep commits small and atomic. A commit should build and pass the gates on its
own.

## Pull request process

1. Fork the repository and create a branch from `main`:
   `git checkout -b feat/my-feature`.
2. Make your change, with tests.
3. Run the quality gates locally.
4. Push and open a pull request using the template.
5. A maintainer reviews within a few days. Expect questions — that's normal.
6. Once approved, the maintainer squashes-merge with a Conventional Commit
   title, or asks you to rebase.

Never force-push to a branch that has a review in progress; use
`git push --force-with-lease` only on your own branch.

## Adding an OCR engine or text corrector

Engines and correctors are **ports** (protocols) with pluggable adapters. The
whole guide fits in under 50 lines; see
[`docs/adding-an-engine.md`](docs/adding-an-engine.md).

In short:

```python
from scan2epub.domain.ports import OcrEngine
from scan2epub.domain.models import Page, TextBlock


class MyEngine:
    name = "my-engine"

    def recognize(self, page: Page) -> list[TextBlock]:
        ...
        return [TextBlock(text="...", bbox=(0, 0, 1, 1), confidence=0.9)]
```

Register it in `config.toml`:

```toml
[ocr.my-engine]
adapter = "scan2epub.infrastructure.ocr.my_engine:MyEngine"
```

## Adding a dependency

```bash
uv add <package>            # runtime
uv add --optional <pkg>    # extra
uv sync && uv run python scripts/check_licenses.py
```

Then update `THIRD_PARTY_LICENSES.md` in the same commit.

## Code style

- **English** for code, comments, docstrings, commit messages and
  documentation. User-facing CLI help may be English; translations live in the
  docs.
- Four-space indentation, 100-column lines (configured in `pyproject.toml`).
- `ruff format` is the single source of truth for formatting. Do not hand-tune.
- Prefer explicit types over `Any`. `pyright` strict mode forbids implicit
  `Any` leaks.
- Public API changes need a `CHANGELOG.md` entry under `## [Unreleased]`.

## Reporting bugs

Open an issue using the **Bug report** template. A good report includes:

- The exact command you ran and the full output.
- `scan2epub doctor` output (it prints versions, available engines and config).
- The input: page count, whether the PDF is text-based or scanned, and — if
  possible — a few sample pages.
- The expected vs. actual result.

If the issue involves copyrighted material, **do not attach it**. Use a
public-domain sample from [`samples/`](samples/) or a self-made synthetic page.

## Code of Conduct

Instances of unacceptable behaviour should be reported to the maintainers at
`conduct@scan2epub.org` (or the address in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)).
All reports will be reviewed and handled promptly and discreetly.
