/**
 * The settings of the reader and the place where they are kept.
 *
 * The preferences and the reading progress live in the `localStorage` of the
 * browser, so they survive a reload and they never leave the machine.
 */

/** The themes of the reader. */
export type ReaderTheme = 'light' | 'dark' | 'sepia';

/**
 * The way the pages of the book are set.
 *
 * - `plain` leaves the text as it is, aligned to the left.
 * - `book` gives the classic look of a printed book: justified text with
 *   hyphenation, the paragraphs marked with an indent instead of a blank
 *   line, and the headings in small capitals.
 */
export type ReaderStyle = 'plain' | 'book';

/**
 * How many pages are shown at the same time.
 *
 * - `single` shows one page, the way a phone or a tablet reads.
 * - `spread` shows two pages facing each other, the way a printed book is
 *   read.
 */
export type ReaderLayout = 'single' | 'spread';

/** One of the typefaces of the reader. */
export interface ReaderFont {
  /** The identifier of the typeface. */
  readonly id: string;
  /** The name of the typeface. */
  readonly label: string;
  /** The CSS stack of the typeface. */
  readonly stack: string;
}

/** The typefaces that the reader offers. */
export const READER_FONTS: readonly ReaderFont[] = [
  {
    id: 'serif',
    label: 'Serif',
    stack: '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif',
  },
  {
    id: 'humanist',
    label: 'Humanist',
    stack: 'Charter, "Bitstream Charter", Cambria, Georgia, serif',
  },
  {
    id: 'sans',
    label: 'Sans',
    stack: 'Inter, ui-sans-serif, system-ui, "Segoe UI", sans-serif',
  },
  {
    id: 'mono',
    label: 'Monospace',
    stack: 'ui-monospace, "Cascadia Mono", Menlo, Consolas, monospace',
  },
];

/** One of the themes of the reader. */
export interface ReaderThemeSpec {
  /** The identifier of the theme. */
  readonly id: ReaderTheme;
  /** The name of the theme. */
  readonly label: string;
  /** The colour of the page. */
  readonly background: string;
  /** The colour of the text. */
  readonly foreground: string;
  /** The colour of the links. */
  readonly link: string;
  /** The colour scheme that the browser uses for the controls. */
  readonly scheme: 'light' | 'dark';
}

/** The themes of the reader. */
export const READER_THEMES: readonly ReaderThemeSpec[] = [
  {
    id: 'light',
    label: 'Light',
    background: '#ffffff',
    foreground: '#1b1b1b',
    link: '#2f6f4f',
    scheme: 'light',
  },
  {
    id: 'dark',
    label: 'Dark',
    background: '#16181c',
    foreground: '#d9d5cc',
    link: '#8fc7a6',
    scheme: 'dark',
  },
  {
    id: 'sepia',
    label: 'Sepia',
    background: '#f4ecd8',
    foreground: '#43382a',
    link: '#8a5a2b',
    scheme: 'light',
  },
];

/** The settings of the reader. */
export interface ReaderPreferences {
  /** The identifier of the typeface. */
  readonly font: string;
  /** The size of the text, in pixels. */
  readonly size: number;
  /** The leading of the text, as a multiple of the size. */
  readonly leading: number;
  /** The margin of the page, in pixels. */
  readonly margin: number;
  /** The theme of the reader. */
  readonly theme: ReaderTheme;
  /** The way the pages of the book are set. */
  readonly style: ReaderStyle;
  /** How many pages are shown at the same time. */
  readonly layout: ReaderLayout;
  /**
   * Whether the reader hides everything but the book.
   *
   * The reading mode takes the whole window: the header of the application
   * and the toolbar of the reader disappear, so that nothing competes with
   * the page.
   */
  readonly focus: boolean;
}

/** The settings that the reader starts with. */
export const DEFAULT_READER_PREFERENCES: ReaderPreferences = {
  font: 'serif',
  size: 19,
  leading: 1.6,
  margin: 28,
  theme: 'light',
  style: 'book',
  layout: 'spread',
  focus: false,
};

/** The key of the preferences in the `localStorage`. */
export const READER_PREFERENCES_KEY = 'scan2epub.reader.preferences';

/** The key of the reading progress in the `localStorage`. */
export const READER_PROGRESS_KEY = 'scan2epub.reader.progress';

/** Where the reader was left. */
export interface ReaderProgress {
  /** The EPUB CFI of the last place that was read. */
  readonly cfi: string | null;
  /** The fraction of the book that was read, between 0 and 1. */
  readonly fraction: number;
  /** The title of the book. */
  readonly title: string;
  /** When the progress was saved, in milliseconds since the epoch. */
  readonly savedAt: number;
}

/** Read a value of the `localStorage`, without ever failing. */
export function readStorage(key: string): string | null {
  try {
    return globalThis.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

/** Write a value in the `localStorage`, without ever failing. */
export function writeStorage(key: string, value: string): void {
  try {
    globalThis.localStorage?.setItem(key, value);
  } catch {
    /* The storage can be full or blocked: the reader works without it. */
  }
}

/** Read the preferences that were saved, or the default ones. */
export function loadPreferences(): ReaderPreferences {
  const raw = readStorage(READER_PREFERENCES_KEY);
  if (!raw) {
    return DEFAULT_READER_PREFERENCES;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<ReaderPreferences>;
    return {
      font: parsed.font ?? DEFAULT_READER_PREFERENCES.font,
      size: typeof parsed.size === 'number' ? parsed.size : DEFAULT_READER_PREFERENCES.size,
      leading:
        typeof parsed.leading === 'number' ? parsed.leading : DEFAULT_READER_PREFERENCES.leading,
      margin: typeof parsed.margin === 'number' ? parsed.margin : DEFAULT_READER_PREFERENCES.margin,
      theme: isTheme(parsed.theme) ? parsed.theme : DEFAULT_READER_PREFERENCES.theme,
      style: isStyle(parsed.style) ? parsed.style : DEFAULT_READER_PREFERENCES.style,
      layout: isLayout(parsed.layout) ? parsed.layout : DEFAULT_READER_PREFERENCES.layout,
      focus: typeof parsed.focus === 'boolean' ? parsed.focus : DEFAULT_READER_PREFERENCES.focus,
    };
  } catch {
    return DEFAULT_READER_PREFERENCES;
  }
}

/** Read the progress that was saved, if there is one. */
export function loadProgress(): ReaderProgress | null {
  const raw = readStorage(READER_PROGRESS_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<ReaderProgress>;
    if (typeof parsed.fraction !== 'number') {
      return null;
    }
    return {
      cfi: typeof parsed.cfi === 'string' ? parsed.cfi : null,
      fraction: parsed.fraction,
      title: typeof parsed.title === 'string' ? parsed.title : '',
      savedAt: typeof parsed.savedAt === 'number' ? parsed.savedAt : 0,
    };
  } catch {
    return null;
  }
}

/** Return whether a value is one of the themes of the reader. */
export function isTheme(value: unknown): value is ReaderTheme {
  return READER_THEMES.some((theme) => theme.id === value);
}

/** Return whether a value is one of the styles of the reader. */
export function isStyle(value: unknown): value is ReaderStyle {
  return value === 'plain' || value === 'book';
}

/** Return whether a value is one of the layouts of the reader. */
export function isLayout(value: unknown): value is ReaderLayout {
  return value === 'single' || value === 'spread';
}
