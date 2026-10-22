import { Injectable, computed, signal } from '@angular/core';

import {
  READER_PREFERENCES_KEY,
  READER_PROGRESS_KEY,
  READER_THEMES,
  loadPreferences,
  loadProgress,
  writeStorage,
  type ReaderPreferences,
  type ReaderProgress,
  type ReaderLayout,
  type ReaderStyle,
  type ReaderTheme,
} from './reader-preferences';

/**
 * The settings of the reader and the reading progress.
 *
 * Both are kept in the `localStorage` of the browser, so a reader who comes
 * back finds the book where it was left.
 */
@Injectable({ providedIn: 'root' })
export class ReaderStore {
  /** The settings of the reader. */
  readonly preferences = signal<ReaderPreferences>(loadPreferences());

  /** Where the reader was left the last time. */
  readonly progress = signal<ReaderProgress | null>(loadProgress());

  /** The theme that is selected. */
  readonly theme = computed(
    () => READER_THEMES.find((theme) => theme.id === this.preferences().theme) ?? READER_THEMES[0],
  );

  /** Change some of the settings and save them. */
  update(patch: Partial<ReaderPreferences>): void {
    const next: ReaderPreferences = { ...this.preferences(), ...patch };
    this.preferences.set(next);
    writeStorage(READER_PREFERENCES_KEY, JSON.stringify(next));
  }

  /** Choose the typeface. */
  setFont(font: string): void {
    this.update({ font });
  }

  /** Choose the size of the text. */
  setSize(size: number): void {
    this.update({ size });
  }

  /** Choose the leading of the text. */
  setLeading(leading: number): void {
    this.update({ leading });
  }

  /** Choose the margin of the page. */
  setMargin(margin: number): void {
    this.update({ margin });
  }

  /** Choose the theme. */
  setTheme(theme: ReaderTheme): void {
    this.update({ theme });
  }

  /** Choose the way the pages of the book are set. */
  setStyle(style: ReaderStyle): void {
    this.update({ style });
  }

  /** Choose how many pages are shown at the same time. */
  setLayout(layout: ReaderLayout): void {
    this.update({ layout });
  }

  /** Enter or leave the reading mode, where only the book is shown. */
  setFocus(focus: boolean): void {
    this.update({ focus });
  }

  /** Remember where the reader was. */
  saveProgress(progress: Omit<ReaderProgress, 'savedAt'>): void {
    const saved: ReaderProgress = { ...progress, savedAt: Date.now() };
    this.progress.set(saved);
    writeStorage(READER_PROGRESS_KEY, JSON.stringify(saved));
  }

  /** Forget where the reader was. */
  clearProgress(): void {
    this.progress.set(null);
    writeStorage(READER_PROGRESS_KEY, '');
  }
}
