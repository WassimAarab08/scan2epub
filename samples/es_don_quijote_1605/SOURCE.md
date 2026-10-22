# Don Quijote

| | |
| --- | --- |
| Author | Miguel de Cervantes Saavedra |
| Year | 1605 |
| Language | es |
| Source | [Project Gutenberg, eBook 2000](https://www.gutenberg.org/ebooks/2000) |
| Licence | Public domain in the United States; the original work is in the public domain in the European Union. |
| OCR language | `spa` |

## What these pages are

The **text** is the real, public-domain text of the work, taken from Project
Gutenberg. The **pages** are rendered by
[`scripts/fetch_samples.py`](../scripts/fetch_samples.py) as they would have
been printed: the long s, the ligatures, the running head, the folio and a
footnote.

They are not photographs of a book. They are synthetic pages that reproduce
the *typographical* problems of an old book, so that the corpus can be
versioned in the repository and the evaluation can run everywhere, without
scanning anything.

## The reference transcription

`reference.txt` holds the text as it should be read: the long s normalised,
the ligatures expanded, the running head and the folio removed, and the
footnote kept. It is what the deterministic cleaner must produce, so the
evaluation measures the whole chain and not only the recognition.
