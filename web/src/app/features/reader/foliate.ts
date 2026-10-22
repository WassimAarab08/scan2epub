/**
 * The loader of the foliate-js modules.
 *
 * The library is vendored in `src/assets/foliate-js` (MIT licence, see the
 * `LICENSE` file next to it) and it is loaded with a dynamic import of its
 * own URL. The browser only fetches it when the reader is opened, so it
 * never weighs on the first bundle.
 */

/** One item of the table of contents of a book. */
export interface TocItem {
  readonly label: string;
  readonly href: string;
  readonly subitems?: readonly TocItem[];
}

/** The parts of the renderer that the reader uses. */
export interface FoliateRenderer {
  setStyles?(css: string): void;
  /**
   * Change an attribute of the paginator.
   *
   * The attribute `max-column-count` decides how many pages are shown at
   * the same time: one page or a spread of two.
   */
  setAttribute?(name: string, value: string): void;
  next(distance?: number): Promise<void>;
  prev(distance?: number): Promise<void>;
}

/** The parts of the foliate view that the reader uses. */
export interface FoliateView extends HTMLElement {
  book: {
    readonly toc?: readonly TocItem[];
    readonly metadata?: Record<string, unknown>;
  };
  renderer: FoliateRenderer;
  open(book: Blob | string): Promise<void>;
  init(options?: { lastLocation?: string; showTextStart?: boolean }): Promise<void>;
  goTo(target: string | number): Promise<unknown>;
  close(): void;
}

/** Return the URL of a file of the vendored library. */
export function foliateUrl(file = 'view.js'): string {
  return new URL(`assets/foliate-js/${file}`, document.baseURI).href;
}

/**
 * Load the foliate view.
 *
 * The import is not a literal on purpose: the bundler has to leave it alone
 * and let the browser fetch the module from the assets.
 */
export async function loadFoliateView(): Promise<new () => FoliateView> {
  const module = (await import(foliateUrl())) as {
    View: new () => FoliateView;
  };
  return module.View;
}
