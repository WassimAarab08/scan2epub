# Usage

## `scan2epub convert`

Convert a scanned PDF into a reflowable EPUB 3 file.

```bash
scan2epub convert libro.pdf -o libro.epub
```

| Option | Default | Description |
| --- | --- | --- |
| `-o`, `--output` | `<input>.epub` | The destination file. |
| `--ocr` | `tesseract` | The OCR engine. |
| `--lang` | from the configuration | The language of the OCR engine. |
| `--dpi` | `300` | The resolution of the rendered pages. |
| `--title` | the name of the file | The title of the book. |
| `--author` | empty | The author of the book. |
| `--year` | empty | The year of publication. |
| `--output-language` | derived from `--lang` | The language of the EPUB. |
| `--work-dir` | `<input>.scan2epub` | Where the intermediate files are written. |
| `--cache-dir` | `<work-dir>/cache` | Where the artefacts are cached. |
| `--no-cache` | off | Disable the cache. |
| `--no-validate` | off | Skip the EPUBCheck validation. |
| `--strict` | off | Fail when the generated EPUB does not pass EPUBCheck. |
| `--config` | the user configuration | The `config.toml` file. |
| `--json` | off | Print the summary as JSON. |

The global options come **before** the command:

```bash
scan2epub --verbose convert libro.pdf -o libro.epub
```

### Recipes

```bash
# A Spanish book printed before 1900: the legacy language data matters.
scan2epub convert libro.pdf -o libro.epub --lang "spa+spa_old"

# A poor scan: raise the resolution and keep the adaptive binarisation.
scan2epub convert libro.pdf -o libro.epub --dpi 400

# A book whose title page is not the first page.
scan2epub convert libro.pdf -o libro.epub \
    --title "Historia de la imprenta en España" \
    --author "Anónimo" --year 1765

# Reuse the cache of a previous run: the pages are not recognised twice.
scan2epub convert libro.pdf -o libro.epub --cache-dir ~/.cache/scan2epub/libro

# A machine readable summary, for a script.
scan2epub convert libro.pdf -o libro.epub --json | jq .removed_running_heads
```

## `scan2epub doctor`

Report what the installation supports: the version, the available OCR engines,
the Tesseract language data, the configuration file, the presence of EPUBCheck
and the presence of the API keys (**never their value**).

```bash
scan2epub doctor
scan2epub doctor --json
```

```
scan2epub 0.1.0
  Python      3.12.10
  Platform    Windows-11-10.0.26200-SP0
  Config      not found (using defaults)

OCR engines
Engine     Status     Details
tesseract  available  version 5.5.3.20260724, languages: eng, osd, spa, spa_old

Dependencies
  pypdfium2    5.14.0
  opencv       5.0.0.93
  numpy        2.3.5
  pillow       13.0.0
```

## The output

The command prints a summary of what it did:

```
EPUB written: libro.epub
  size        412.3 KiB
  pages       218
  chapters    14
  duration    96.4 s
  removed running heads: HISTORIA DE LA IMPRENTA EN ESPAÑA
  removed folios        218
  rejoined hyphenations  1342
  merged paragraphs      2871
  footnotes detected     96
  EPUBCheck passed (0 warnings, version 5.4.0)
```

Each line maps to one of the rules of the cleaner, described in
[`architecture.md`](architecture.md#what-the-cleaner-does).

## The exit codes

| Code | Meaning |
| --- | --- |
| `0` | The conversion succeeded. |
| `1` | The conversion failed; the reason is printed. |
| `2` | The command line was wrong. |
| `130` | The user interrupted the run. |

## Reading the result

The generated EPUB is a plain EPUB 3 file. It opens in Calibre, KOReader,
Apple Books, Thorium, Foliate and any other reader. The font, the size, the
line height, the margins and the theme are controlled by the reader: the
stylesheet of the book never forces them.

To check the file by hand:

```bash
unzip -l libro.epub
```

```
Archive:  libro.epub
  Length      Date    Time    Name
---------  ---------- -----   ----
        20  2026-10-21 09:00   mimetype
       377  2026-10-21 09:00   META-INF/container.xml
      2412  2026-10-21 09:00   EPUB/package.opf
      3180  2026-10-21 09:00   EPUB/nav.xhtml
       612  2026-10-21 09:00   EPUB/styles/main.css
     48210  2026-10-21 09:00   EPUB/text/chapter-001.xhtml
```

## Using the library

```python
from pathlib import Path

from scan2epub.application.pipeline import Pipeline
from scan2epub.config import Config, GeneralConfig
from scan2epub.domain.models import BookMetadata
from scan2epub.infrastructure.imaging.opencv_preprocessor import OpenCvPreprocessor
from scan2epub.infrastructure.ocr.tesseract import TesseractOcrEngine
from scan2epub.infrastructure.pdf.pdfium_source import PdfiumPageSource

config = Config(general=GeneralConfig(language="spa", dpi=300))
pipeline = Pipeline(
    source=PdfiumPageSource(Path("libro.pdf"), dpi=config.general.dpi),
    preprocessor=OpenCvPreprocessor(config.preprocess),
    ocr=TesseractOcrEngine(lang="spa"),
    config=config,
    work_dir=Path("trabajo"),
)
result = pipeline.run(BookMetadata(title="Mi libro"), Path("libro.epub"))
print(result.validation.passed, result.page_count)
```

## `scan2epub config`

Write or inspect the configuration file.

```bash
scan2epub config --init          # write a documented template
scan2epub config --show          # print the configuration in use
scan2epub config                 # say where the file is
```

The template that `--init` writes is a fully commented `config.toml`; every
section of it is described in [`configuration.md`](configuration.md).

## `scan2epub serve`

Start the REST API, which exposes the same pipeline over HTTP.

```bash
scan2epub serve --host 127.0.0.1 --port 8000
```

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `127.0.0.1` | The address the service listens on. |
| `--port` | `8000` | The port. |
| `--reload` | off | Reload the code on every change. |
| `--data-dir` | `.scan2epub` | Where the uploads and the results are written. |

The service listens on the loopback address by default: put it behind a
reverse proxy with TLS and authentication before exposing it.

| Route | Method | Description |
| --- | --- | --- |
| `/` | `GET` | A small web page that converts a book. |
| `/health` | `GET` | The version and the available engines. |
| `/api/engines` | `GET` | The description of every engine. |
| `/api/convert` | `POST` | Upload a PDF, get the summary and the download link. |
| `/api/download/{job}/{name}` | `GET` | Download a generated EPUB. |
| `/docs` | `GET` | The interactive documentation of the API. |
| `/openapi.json` | `GET` | The OpenAPI schema. |

```bash
curl -F "file=@libro.pdf" -F "title=El libro" http://127.0.0.1:8000/api/convert
```

```json
{
  "title": "El libro",
  "pages": 218,
  "chapters": 14,
  "size": 422145,
  "duration_seconds": 96.4,
  "removed_running_heads": ["HISTORIA DE LA IMPRENTA EN ESPAÑA"],
  "removed_page_numbers": 218,
  "joined_hyphens": 1342,
  "merged_paragraphs": 2871,
  "footnotes": 96,
  "epub_valid": true,
  "epub_warnings": [],
  "download": "/api/download/scan2epub-abc123/libro.epub"
}
```

> **Status: preview.** The queue of jobs, the worker process and the progress
> by SSE arrive in Phase 4. For now the conversion runs in the process that
> receives the request.

## The commands of the later phases

| Command | Phase |
| --- | --- |
| `scan2epub estimate` | 3 — the cost of a run with a paid provider |
| `scan2epub eval` | 2 — the CER and WER of every engine |
| `scan2epub worker` | 4 — the job worker of the queue |
| `scan2epub samples fetch` | 2 — the public-domain evaluation corpus |