# Samples

This directory holds a small evaluation corpus of **public-domain** book scans
together with their reference transcriptions.

## Rules

1. **Public domain only.** Every sample must be a work whose copyright has
   expired in the United States *and* in the European Union, and it must be
   available from a source that states this explicitly (e.g. Project Gutenberg,
   Internet Archive, Gallica, BNE, Wikisource).
2. **Record the provenance.** Each sample directory contains a `SOURCE.md` with
   the title, author, year, language, source URL and the licence/public-domain
   statement of the source.
3. **No personal data.** Nothing that identifies a living person, and no
   modern copyrighted material such as dust jackets or publisher plates.
4. **Small.** At most ~20 pages per book, at a reasonable resolution, so the
   whole corpus stays under a few megabytes. Compress losslessly or with
   high-quality JPEG.
5. **Reference transcription.** Each sample ships a `reference.txt` with the
   exact text a human would expect, used to compute CER and WER.

## Expected layout

```
samples/
├── README.md
├── es_guevara_1765/
│   ├── SOURCE.md
│   ├── pages/
│   │   ├── 001.png
│   │   ├── 002.png
│   │   └── ...
│   └── reference.txt
└── en_austen_1813/
    ├── SOURCE.md
    ├── pages/
    └── reference.txt
```

## Reference transcription format

- Plain UTF-8 text, one paragraph per block, paragraphs separated by a blank
  line.
- Running heads, folios, catchwords and footnote markers are **removed**.
- Long `ſ` is normalised to `s`; ligatures are expanded.
- End-of-line hyphenation is resolved (the word appears whole).
- Modern spelling is preserved as in the original; the `--modernize` option is
  evaluated separately and never applied to the reference.

## Why not the full books?

The corpus is deliberately small so that `scan2epub eval` can run in CI in a
couple of minutes. A larger benchmark set can be generated locally with
`scan2epub samples fetch --all`; those files are cached outside the repository
and are never committed.
