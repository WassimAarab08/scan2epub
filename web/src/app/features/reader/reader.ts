import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { ConversionStore } from '../../core/conversion.store';
import { buildReaderCss } from '../../core/reader-css';
import { ReaderStore } from '../../core/reader.store';
import {
  READER_FONTS,
  READER_THEMES,
  type ReaderLayout,
  type ReaderStyle,
  type ReaderTheme,
} from '../../core/reader-preferences';
import { loadFoliateView, type FoliateView, type TocItem } from './foliate';

/** How often the reading progress is written, in milliseconds. */
const SAVE_INTERVAL = 2000;

/**
 * The integrated reader.
 *
 * The book is opened with foliate-js, a small library that renders EPUB 3 in
 * the browser. The typeface, the size, the leading, the margins and the theme
 * are applied to the pages of the book, and the place where the reader was
 * left is kept in the `localStorage`.
 */
@Component({
  selector: 'app-reader',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reader.html',
  styleUrl: './reader.css',
})
export class ReaderComponent implements OnDestroy {
  protected readonly store = inject(ConversionStore);
  protected readonly reader = inject(ReaderStore);

  /** The typefaces that the reader offers. */
  protected readonly fonts = READER_FONTS;

  /** The themes that the reader offers. */
  protected readonly themes = READER_THEMES;

  /** The place where the book is rendered. */
  protected readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');

  /** Whether the book is open. */
  protected readonly ready = signal(false);

  /** The message of the last failure. */
  protected readonly error = signal<string | null>(null);

  /** The table of contents of the book. */
  protected readonly toc = signal<readonly TocItem[]>([]);

  /** Whether the table of contents is shown. */
  protected readonly contentsOpen = signal(false);

  /** The fraction of the book that was read, between 0 and 1. */
  protected readonly fraction = signal(0);

  /** The title of the book. */
  protected readonly title = computed(() => this.store.summary()?.title || 'The book');

  /** The colour of the page, from the theme. */
  protected readonly background = computed(() => this.reader.theme().background);

  /** The colour of the text, from the theme. */
  protected readonly foreground = computed(() => this.reader.theme().foreground);

  private readonly view = signal<FoliateView | null>(null);
  private lastSave = 0;
  private lastCfi: string | null = null;
  private lastFraction = 0;

  constructor() {
    effect(() => {
      const preferences = this.reader.preferences();
      const view = this.view();
      if (view) {
        view.renderer.setStyles?.(buildReaderCss(preferences));
        this.applyLayout(view, preferences.layout);
      }
    });
  }

  /**
   * Tell the paginator how many pages it has to show.
   *
   * The attribute `max-column-count` of the paginator is the number of
   * columns of the layout: one page or a spread of two facing pages.
   */
  private applyLayout(view: FoliateView, layout: ReaderLayout): void {
    view.renderer.setAttribute?.('max-column-count', layout === 'spread' ? '2' : '1');
  }

  /** Open the book once the page is ready. */
  async ngAfterViewInit(): Promise<void> {
    document.addEventListener('fullscreenchange', this.onFullscreenChange);
    await this.open();
  }

  /** Release the book when the page is left. */
  ngOnDestroy(): void {
    document.removeEventListener('fullscreenchange', this.onFullscreenChange);
    this.saveProgress(true);
    this.view()?.close();
    this.view.set(null);
  }

  /**
   * Enter or leave the reading mode.
   *
   * The mode hides the menus of the application and asks the browser for the
   * whole screen. A browser that refuses the full screen still gets the mode:
   * the menus are gone and the page has the whole window.
   */
  protected async setFocus(focus: boolean): Promise<void> {
    this.reader.setFocus(focus);
    try {
      if (focus) {
        await document.documentElement.requestFullscreen?.();
      } else if (document.fullscreenElement) {
        await document.exitFullscreen();
      }
    } catch {
      // The full screen is a bonus: the reading mode works without it.
    }
  }

  /** Leave the reading mode when the reader leaves the full screen. */
  private readonly onFullscreenChange = (): void => {
    if (!document.fullscreenElement && this.reader.preferences().focus) {
      this.reader.setFocus(false);
    }
  };

  /** Choose the typeface. */
  protected setFont(font: string): void {
    this.reader.setFont(font);
  }

  /** Choose the size of the text. */
  protected setSize(event: Event): void {
    this.reader.setSize(Number((event.target as HTMLInputElement).value));
  }

  /** Choose the leading of the text. */
  protected setLeading(event: Event): void {
    this.reader.setLeading(Number((event.target as HTMLInputElement).value));
  }

  /** Choose the margin of the page. */
  protected setMargin(event: Event): void {
    this.reader.setMargin(Number((event.target as HTMLInputElement).value));
  }

  /** Choose the theme. */
  protected setTheme(theme: ReaderTheme): void {
    this.reader.setTheme(theme);
  }

  /** Choose the way the pages of the book are set. */
  protected setStyle(style: ReaderStyle): void {
    this.reader.setStyle(style);
  }

  /** Choose how many pages are shown at the same time. */
  protected setLayout(layout: ReaderLayout): void {
    this.reader.setLayout(layout);
  }

  /** Show or hide the table of contents. */
  protected toggleContents(): void {
    this.contentsOpen.update((open) => !open);
  }

  /** Go to a chapter of the table of contents. */
  protected async goTo(item: TocItem): Promise<void> {
    await this.view()?.goTo(item.href);
    this.contentsOpen.set(false);
  }

  /** Turn the page. */
  protected async turn(direction: 'next' | 'previous'): Promise<void> {
    const view = this.view();
    if (!view) {
      return;
    }
    if (direction === 'next') {
      await view.renderer.next();
    } else {
      await view.renderer.prev();
    }
  }

  private async open(): Promise<void> {
    const download = this.store.summary()?.download;
    if (!download) {
      this.error.set('There is no book to read. Convert one first.');
      return;
    }

    try {
      const response = await fetch(download);
      if (!response.ok) {
        throw new Error(`The book could not be fetched (${response.status}).`);
      }
      const blob = await response.blob();
      const file = new File([blob], 'book.epub', { type: 'application/epub+zip' });

      const View = await loadFoliateView();
      const view = document.createElement('foliate-view') as FoliateView;
      this.host().nativeElement.append(view);
      view.addEventListener('relocate', (event) => this.onRelocate(event));

      await view.open(file);
      const saved = this.reader.progress();
      await view.init({
        lastLocation: saved?.cfi ?? undefined,
        showTextStart: true,
      });

      this.view.set(view);
      this.toc.set(view.book?.toc ?? []);
      this.ready.set(true);
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'The book could not be opened.');
    }
  }

  private onRelocate(event: Event): void {
    const detail = (event as CustomEvent<{ cfi?: string; fraction?: number }>).detail;
    this.lastCfi = detail?.cfi ?? null;
    this.lastFraction = detail?.fraction ?? 0;
    this.fraction.set(this.lastFraction);
    this.saveProgress();
  }

  /**
   * Remember where the reader was.
   *
   * The events of the paginator arrive very often, so they are throttled;
   * the last one is always written when the page is left.
   */
  private saveProgress(force = false): void {
    const now = Date.now();
    if (!force && now - this.lastSave < SAVE_INTERVAL) {
      return;
    }
    this.lastSave = now;
    this.reader.saveProgress({
      cfi: this.lastCfi,
      fraction: this.lastFraction,
      title: this.title(),
    });
  }
}
