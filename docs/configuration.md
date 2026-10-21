# Configuration

The configuration is layered. From the lowest priority to the highest:

1. the defaults defined in `src/scan2epub/config.py`;
2. the `config.toml` file;
3. the environment variables prefixed with `SCAN2EPUB_`;
4. the command line options.

## The configuration file

By default it is read from:

| Platform | Path |
| --- | --- |
| Linux | `~/.config/scan2epub/config.toml` |
| macOS | `~/.config/scan2epub/config.toml` |
| Windows | `%APPDATA%\scan2epub\config.toml` |

The `SCAN2EPUB_CONFIG` environment variable overrides the location, and
`--config` overrides everything.

```toml
[general]
# The resolution of the rendered pages.
dpi = 300
# The default language of the OCR engine and of the generated book.
language = "spa"
# The OCR engine to use by default.
ocr_engine = "tesseract"
# The text corrector to use by default. Leave it out to stay offline.
# text_corrector = "litellm/ollama/qwen3"
# Modernise the spelling of the text. Off by default: the original spelling
# of the book is preserved.
modernize = false
# The metadata of the book. Every field can be overridden on the command line.
title = "Historia de la imprenta en España"
author = "Anónimo"
year = "1765"
# Validate the generated EPUB with EPUBCheck.
validate_epub = true

[preprocess]
deskew = true
max_skew_degrees = 5.0
binarize = true
denoise = true
crop_borders = true
crop_margin = 16
binary_block_size = 31
binary_c = 12

[clean]
# The height of the header and of the footer zones, as a fraction of the page.
header_zone = 0.12
footer_zone = 0.12
# The zone where the footnotes live.
footnote_zone = 0.82
# How many pages a block must repeat on to be considered a running head.
min_running_head_repeats = 3
max_running_head_chars = 90
join_hyphens = true
normalize_characters = true
join_paragraphs = true
detect_footnotes = true

[ocr.tesseract]
lang = "spa+eng"
oem = 1
psm = 3
# The directory that holds the `*.traineddata` files. When it is not set,
# `TESSDATA_PREFIX` is used.
# tessdata_dir = "/opt/tessdata"

[ocr.paddleocr-vl]
adapter = "scan2epub.infrastructure.ocr.paddleocr_vl:PaddleOcrVlEngine"
model = "PaddlePaddle/PaddleOCR-VL"

[ocr.paddleocr-vl.options]
device = "auto"
max_new_tokens = 4096

[correct.litellm]
adapter = "scan2epub.infrastructure.correction.litellm_corrector:LiteLlmCorrector"
model = "ollama/qwen3"

[correct.litellm.options]
# The maximum normalised edit distance a correction may reach.
max_distance = 0.12
# The maximum relative change of the length of a block.
max_length_change = 0.25
```

## The language data of Tesseract

The OCR of a book in Spanish from before 1900 needs the *legacy* Spanish
language data, `spa_old`, next to the modern one:

```bash
# The modern and the legacy Spanish, plus English.
scan2epub convert libro.pdf -o libro.epub --lang "spa+spa_old+eng"
```

The `*.traineddata` files live in the `tessdata` directory. Point
`TESSDATA_PREFIX` at it, or set `tessdata_dir` in the configuration file.

| Language | Code |
| --- | --- |
| Spanish (modern) | `spa` |
| Spanish (before 1900) | `spa_old` |
| English | `eng` |
| French | `fra` |
| German | `deu` |
| Italian | `ita` |
| Portuguese | `por` |
| Latin | `lat` |

## The environment variables

| Variable | Effect |
| --- | --- |
| `SCAN2EPUB_CONFIG` | The path of the `config.toml` file. |
| `SCAN2EPUB_GENERAL_DPI` | Overrides `[general] dpi`. |
| `SCAN2EPUB_GENERAL_LANGUAGE` | Overrides `[general] language`. |
| `SCAN2EPUB_GENERAL_OCR_ENGINE` | Overrides `[general] ocr_engine`. |
| `SCAN2EPUB_GENERAL_MODERNIZE` | Overrides `[general] modernize`. |
| `SCAN2EPUB_PREPROCESS_BINARIZE` | Overrides `[preprocess] binarize`. |
| `SCAN2EPUB_CLEAN_MIN_RUNNING_HEAD_REPEATS` | Overrides the repetition threshold. |
| `SCAN2EPUB_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`. |
| `SCAN2EPUB_EPUBCHECK_JAR` | The path of `epubcheck.jar`. |
| `TESSDATA_PREFIX` | The directory of the Tesseract language data. |
| `HF_HOME` | The cache of the Hugging Face models. |
| `OLLAMA_HOST` | The address of a local Ollama server. |

## The API keys

**The keys are only read from the environment.** They are never written to
the configuration file, never stored in the cache and never logged.

| Provider | Variable |
| --- | --- |
| OpenAI | `OPENAI_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |
| Google Gemini | `GEMINI_API_KEY` |
| Mistral | `MISTRAL_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |

A local Ollama, llama.cpp or vLLM server needs no key at all.

The logger redacts the keys automatically: any value that looks like a
credential is replaced by `***REDACTED***` before it reaches the output. The
`doctor` command reports only whether a key is present, never its value.

## The cache and the working directory

| Path | Content |
| --- | --- |
| `~/.cache/scan2epub` | The default cache of the artefacts. |
| `<source>.scan2epub` | The default working directory of a conversion. |

The working directory holds the rendered pages, the processed images and the
cache of the run. Delete it to start from scratch; the cache is keyed by the
hash of the inputs, so an interrupted run can safely be resumed.

## A complete example

```bash
# A local conversion, with the legacy Spanish and no network access.
scan2epub convert \
    "Cartas marruecas.pdf" \
    -o "cartas.epub" \
    --lang "spa+spa_old" \
    --title "Cartas marruecas" \
    --author "José María de Laverde" \
    --year 1737 \
    --dpi 300
```

```bash
# The same book with a local vision model and a local LLM.
OLLAMA_HOST=http://localhost:11434 scan2epub convert \
    "Cartas marruecas.pdf" \
    -o "cartas.epub" \
    --ocr paddleocr-vl \
    --llm ollama/qwen3
```
