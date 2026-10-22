# scan2epub — the web interface

The Angular application that converts a scanned book into an EPUB 3 and reads
it without leaving the browser.

The interface is a thin client of the REST API of `scan2epub`: it uploads the
PDF, shows the stages of the conversion, shows the summary and opens the
generated book in an integrated reader.

## Requirements

- **Node.js 22 or newer** and npm 10 or newer.
- **The service of `scan2epub`**, running on `http://127.0.0.1:8000`:

  ```console
  $ scan2epub serve
  ```

  The development server proxies `/api`, `/health` and `/openapi.json` to
  that address (see `proxy.conf.json`), so the browser never talks to
  another origin.

## Getting started

```console
$ cd web
$ npm install
$ npm start
```

The application is then on <http://localhost:4200>. The proxy needs the
service to be running, otherwise the interface says that it is unreachable.

## The commands

| Command | What it does |
| --- | --- |
| `npm start` | The development server, on <http://localhost:4200>, with the proxy. |
| `npm run build` | The production build, in `dist/web/browser`. |
| `npm run watch` | The build in watch mode, without optimising. |
| `npm test` | The unit tests, with Vitest. Add `-- --watch=false` to run them once. |

## How it is built

- **Angular 22** with standalone components, signals and the application
  builder. There is no NgRx and no state library: the state is a small signal
  store in `src/app/core`.
- **Tailwind CSS 4**, through the `@tailwindcss/postcss` plugin. The design
  tokens are declared in `src/styles.css` and the templates use the utilities.
- **Vitest**, the test runner that ships with Angular 22, over jsdom.

### The folders

```
src/app/
  core/       The state, the client of the API and the pure helpers.
  features/   The four screens: upload, progress, result and reader.
  app.ts      The shell: the header, the pages and the footer.
```

### The state

`ConversionStore` holds the form, the run and the summary. `ReaderStore`
holds the settings of the reader and the place where the reader was left.
Both are services with signals; the components read the signals and call the
methods.

### The screens

- **Upload** — a drop zone that takes a PDF, the title, the author, the year,
  the language of the recognition and the engine. The estimate of the cost of
  the run is shown next to the button: the local engines are free, and the
  remote ones will publish their price with `GET /api/engines`.
- **Progress** — the stages of the conversion with a bar, because the service
  answers with the whole book at once. The stages are driven by the time that
  has gone by; the real numbers arrive with the answer.
- **Result** — what the conversion did: the pages, the chapters, the running
  heads that were removed, the hyphenations that were rejoined, the paragraphs
  that were merged, the footnotes and the result of the validation. The EPUB
  can be downloaded or read on the spot.
- **Reader** — the book, opened with [foliate-js](https://github.com/johnfactotum/foliate-js).
  The typeface, the size, the leading, the margins and the three themes
  (light, dark and sepia) are applied to the pages, and the reading progress
  is kept in the `localStorage` of the browser.

### foliate-js

The library is vendored in `src/assets/foliate-js` (MIT licence, the licence
file is next to the code). It is **not** part of the bundle: the reader loads
it with a dynamic import of its own URL, so the browser only fetches it when
the reader is opened. That is why the first bundle stays small.

To update the library, copy the files of the upstream repository over
`src/assets/foliate-js`:

```console
$ cp ../tests/browser/assets/foliate-js/*.js src/assets/foliate-js/
$ cp ../tests/browser/assets/foliate-js/vendor/zip.js src/assets/foliate-js/vendor/
```

## The production build

```console
$ npm run build
```

The result is in `dist/web/browser`. It is a static site: any web server can
serve it, as long as it sends the unknown paths to `index.html` and the
`/api` requests to the service.

The budget of the first bundle is 400 kB, and the build fails when it is
exceeded.
