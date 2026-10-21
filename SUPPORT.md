# Support

## How to get help

| You want to… | Do this |
| --- | --- |
| Report a bug | Open an issue with the **Bug report** template. |
| Ask a question | Open an issue with the **Question** template, or start a discussion. |
| Propose a feature | Open an issue with the **Feature request** template. |
| Contribute an OCR engine | Read [`docs/adding-an-engine.md`](docs/adding-an-engine.md) and open a pull request. |
| Report a security problem | **Do not** open an issue. See [`SECURITY.md`](SECURITY.md). |

Please **search the existing issues first**: the answer is often already
there, and a duplicate makes the queue longer for everybody.

## What to include in a bug report

The three things that save the most time:

1. The **exact command** you ran, and its full output.
2. The output of `scan2epub doctor`.
3. A **sample** of the input: the page count, whether the PDF is scanned or
   has a text layer, and the language and the era of the book.

```bash
scan2epub doctor
scan2epub convert libro.pdf -o libro.epub --verbose
```

> **Never attach a book that is still in copyright.** Use a public-domain
> sample from `samples/`, or a page that you made yourself. See the
> [`samples/README.md`](samples/README.md) for the rules.

## Asking a good question

Include:

- What you were trying to do.
- What you expected to happen.
- What happened instead, with the output.
- Your operating system, your Python version and the version of `scan2epub`.

## Helping others

- Answer the questions that nobody has answered yet.
- Label an issue that you can reproduce, and say how.
- Review a pull request, even if you are not a maintainer. A second pair of
  eyes is always useful, and it is the fastest way to learn the code base.
- Improve the documentation where it confused you. If it confused you, it
  will confuse somebody else.

## What is not supported

- The tool converts **public-domain** books. It does not remove the
  protection of a work that is still in copyright, and it is not meant to.
- The model weights are downloaded on demand from the Hugging Face hub. If
  the download fails, it is a problem of the network or of the hub, not of
  the conversion.
- There is no graphical interface yet: the web page of Phase 4 is a preview,
  and the Angular interface of Phase 5 does not exist.
