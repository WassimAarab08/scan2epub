# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | ✅ |
| < 0.1 | ❌ |

`scan2epub` is pre-1.0. Security fixes land on `main` and are backported to the
latest `0.1.x` release.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately via GitHub's private reporting form:

> <https://github.com/WassimAarab08/scan2epub/security/advisories/new>

Or email `security@scan2epub.org`. Encrypting your message with our PGP key is
preferred but not required.

Please include:

- Type of issue (path traversal, SSRF, command injection, credential leak, …).
- Affected component and version.
- Steps to reproduce, ideally with a minimal proof of concept.
- Impact: what an attacker gains.

We aim to acknowledge reports within **72 hours** and to ship a fix or
mitigation within **14 days** of confirmation. We will keep you updated and
credit you in the advisory unless you prefer otherwise.

## Threat model

`scan2epub` processes untrusted input (user-uploaded PDFs) and can call out to
third-party APIs. The security properties we actively maintain:

| Area | Guarantee |
| --- | --- |
| **Secrets** | API keys are read only from environment variables. They are never written to logs, never persisted in the cache or the job database, and never included in error messages. A redaction filter runs over all log records. |
| **File paths** | All cache keys and output paths are derived from sanitised, hashed identifiers. User-supplied filenames never reach the filesystem unchecked; path traversal is rejected. |
| **PDF parsing** | PDFs are parsed with `pypdfium2` (PDFium, sandboxed process) and images are decoded with a size limit to prevent decompression bombs. |
| **Subprocesses** | `tesseract` and `epubcheck` are invoked with argument arrays (never a shell string), with explicit timeouts and a sanitised `PATH`. |
| **Remote calls** | Only HTTPS URLs from a user-configured allow-list of providers are contacted. Redirects are followed only to the same host. Responses are size-limited. |
| **EPUB output** | Generated XHTML is escaped and validated; no user content is ever interpreted as markup. |
| **Job queue** | The SQLite queue uses WAL mode and atomic job claiming, so two workers cannot process the same job. |

## Out of scope

- Vulnerabilities in upstream dependencies that have no reachable code path in
  `scan2epub` (please report those upstream).
- Denial of service caused by deliberately enormous inputs (a 10 000-page PDF
  will use a lot of RAM); we apply size limits but cannot make the tool
  unbounded.
- Weaknesses in the OCR models themselves (they are upstream artefacts).
- Social engineering of project maintainers.

## Security-relevant defaults

- The web API binds to `127.0.0.1` by default. Put it behind a reverse proxy
  with TLS and authentication before exposing it.
- Remote OCR and LLM correction are **opt-in**. A job that uses a paid provider
  requires an explicit budget limit.
- The default OCR engine (Tesseract) runs fully locally and never makes a
  network request.
