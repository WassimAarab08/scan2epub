# The anatomy of the generated EPUB

`scan2epub` writes the EPUB by hand. This document describes the file it
produces and why each part is the way it is.

```mermaid
erDiagram
    ZIP {
        string mimetype
        string META-INF_container.xml
        string EPUB_package.opf
        string EPUB_nav.xhtml
        string EPUB_styles_main.css
        string EPUB_text_chapter-001_xhtml
        string EPUB_images_figure-001_png
    }
```

## The container

The file is a ZIP with a very precise layout, as the EPUB 3 specification
requires:

```python
with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    info = zipfile.ZipInfo("mimetype", date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    archive.writestr(info, "application/epub+zip")
    ...
```

| Rule | Reason |
| --- | --- |
| `mimetype` is the **first** entry | A reader that sniffs the file must find it at offset 30. |
| `mimetype` is **stored**, not deflated | The specification requires it. |
| The timestamps are fixed | Two runs of the same book produce the same bytes. |

## `META-INF/container.xml`

The entry point of the package.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
```

## `EPUB/package.opf`

The package document. It carries the metadata and the manifest.

```xml
<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0"
         unique-identifier="pub-id" xml:lang="es">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:9b1c...</dc:identifier>
    <dc:title>Historia de la imprenta en España</dc:title>
    <dc:language>es</dc:language>
    <dc:creator id="creator">
      Anónimo
    </dc:creator>
    <meta refines="#creator" property="role" scheme="marc:relators">aut</meta>
    <dc:date>1765</dc:date>
    <meta property="dcterms:modified">2026-10-21T09:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="styles/main.css" media-type="text/css"/>
    <item id="chapter-1" href="text/chapter-001.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter-1"/>
  </spine>
</package>
```

| Element | Required by EPUB 3 | Written by `scan2epub` |
| --- | --- | --- |
| `dc:identifier` | yes | A UUIDv5 derived from the title and the author, so it is stable. |
| `dc:title` | yes | The `--title` option, or the name of the file. |
| `dc:language` | yes | A BCP-47 tag derived from the OCR language. |
| `dcterms:modified` | yes | The moment of the conversion, in UTC. |
| `dc:creator` | no | The `--author` option, with the `aut` role. |
| `dc:date` | no | The `--year` option. |
| `properties="nav"` | yes, one per package | The navigation document. |

`dc:language` matters: Tesseract uses three-letter codes (`spa`, `eng`) while
EPUB needs the two-letter BCP-47 form (`es`, `en`). The mapping lives in
`scan2epub.config.output_language_for`.

## `EPUB/nav.xhtml`

The navigation document, with the table of contents and the landmarks.

```xml
<nav epub:type="toc" id="toc">
  <h1>Índice</h1>
  <ol>
    <li><a href="text/chapter-001.xhtml">CAPITULO PRIMERO</a>
      <ol>
        <li><a href="text/chapter-001.xhtml#chapter-1-h1">De la antigüedad</a></li>
      </ol>
    </li>
  </ol>
</nav>
```

The labels of the navigation document follow the language of the book:
`Índice` in Spanish, `Table of contents` in English, and so on.

## `EPUB/styles/main.css`

The stylesheet is deliberately minimal. **It never declares a font family, a
font size, a line height or the body margin**, so the reading preferences of
the e-reader always win.

```css
p { text-indent: 1em; }
p.first { text-indent: 0; }
h1, h2, h3, h4 { text-align: center; page-break-after: avoid; }
h1 { page-break-before: always; }
blockquote { margin-left: 2em; margin-right: 2em; }
img { max-width: 100%; height: auto; }
hr { width: 30%; margin: 1em auto; border: 0; border-top: 1px solid currentColor; }
aside { page-break-inside: avoid; }
```

This is not a matter of taste: a browser test measures the computed style of
the generated document and checks that the font, the size and the leading come
from the reader.

## `EPUB/text/chapter-XXX.xhtml`

One content document per chapter.

```xml
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      lang="es" xml:lang="es">
  <head>
    <title>CAPITULO PRIMERO</title>
    <link rel="stylesheet" type="text/css" href="../styles/main.css"/>
  </head>
  <body>
    <section epub:type="chapter" id="chapter-1">
      <h1>CAPITULO PRIMERO</h1>
      <p class="first">El hombre que escribe con la letra larga, llamada por los
      impresores letra sigma, no sabe que la s final de la palabra se escribia
      de otra manera que la inicial.</p>
      <p>Y por esta razon los lectores modernos encuentran estas paginas
      (_mucho_) mas {_dificiles_} de lo que son.</p>
      <hr/>
      <aside epub:type="footnote" id="chapter-1-fn-1">
        <p>Nota del autor sobre la imprenta y sus costes.</p>
      </aside>
    </section>
  </body>
</html>
```

| Detail | Reason |
| --- | --- |
| The `xmlns:epub` declaration | `epub:type` lives in the EPUB namespace. |
| `lang` and `xml:lang` | A screen reader needs the language of the text. |
| `<p class="first">` | The first paragraph of a chapter is not indented. |
| The `hr` before the notes | The notes are set apart from the text. |
| Every text run is escaped | No OCR output is ever interpreted as markup. |

## The footnotes

A footnote whose number appears in the body becomes a real EPUB note: the
number in the text is a `noteref` and the note itself is an `aside` with
`epub:type="footnote"`.

```xml
<p>El texto principal <sup><a epub:type="noteref" href="#chapter-1-fn-1">1</a></sup>
y su continuacion.</p>
...
<aside epub:type="footnote" id="chapter-1-fn-1">
  <p>Nota del autor.</p>
</aside>
```

When the number cannot be found in the body text, the note is kept as a plain
paragraph instead: an orphan note is better than a broken link.

## The figures

The illustrations are stored in `EPUB/images/` and declared in the manifest:

```xml
<item id="figure-1" href="images/figure-1.png" media-type="image/png"/>
```

and referenced from the text:

```xml
<figure id="figure-1">
  <img src="../images/figure-1.png" alt=""/>
  <figcaption>Una figura</figcaption>
</figure>
```

## The validation

The file is validated with [EPUBCheck](https://www.w3.org/Tools/epubcheck/),
the reference implementation of the specification, released under the
BSD-3-Clause licence.

```bash
java -jar epubcheck.jar libro.epub
```

```
Validating using EPUB version 3.4 rules.
No errors or warnings detected.
Messages: 0 fatals / 0 errors / 0 warnings / 0 infos
```

The validation runs automatically at the end of a conversion, and again in the
continuous integration on the file produced by the test suite.
