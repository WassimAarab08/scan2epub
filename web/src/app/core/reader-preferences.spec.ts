import { beforeEach, describe, expect, it } from 'vitest';

import { buildReaderCss } from './reader-css';
import {
  DEFAULT_READER_PREFERENCES,
  READER_PREFERENCES_KEY,
  READER_PROGRESS_KEY,
  loadPreferences,
  loadProgress,
  readStorage,
  writeStorage,
} from './reader-preferences';

describe('the settings of the reader', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('starts with the default settings', () => {
    expect(loadPreferences()).toEqual(DEFAULT_READER_PREFERENCES);
  });

  it('survives a reload', () => {
    writeStorage(
      READER_PREFERENCES_KEY,
      JSON.stringify({ font: 'sans', size: 22, leading: 1.4, margin: 10, theme: 'dark' }),
    );
    expect(loadPreferences()).toEqual({
      font: 'sans',
      size: 22,
      leading: 1.4,
      margin: 10,
      theme: 'dark',
      style: DEFAULT_READER_PREFERENCES.style,
      layout: DEFAULT_READER_PREFERENCES.layout,
      focus: DEFAULT_READER_PREFERENCES.focus,
    });
  });

  it('remembers the reading mode', () => {
    writeStorage(READER_PREFERENCES_KEY, JSON.stringify({ focus: true }));
    expect(loadPreferences().focus).toBe(true);
  });

  it('keeps the style and the layout of the reader', () => {
    writeStorage(
      READER_PREFERENCES_KEY,
      JSON.stringify({ style: 'plain', layout: 'single' }),
    );
    const preferences = loadPreferences();
    expect(preferences.style).toBe('plain');
    expect(preferences.layout).toBe('single');
  });

  it('ignores a style that does not exist', () => {
    writeStorage(READER_PREFERENCES_KEY, JSON.stringify({ style: 'neon', layout: 'three' }));
    expect(loadPreferences().style).toBe(DEFAULT_READER_PREFERENCES.style);
    expect(loadPreferences().layout).toBe(DEFAULT_READER_PREFERENCES.layout);
  });

  it('falls back when the saved settings are broken', () => {
    writeStorage(READER_PREFERENCES_KEY, 'not json');
    expect(loadPreferences()).toEqual(DEFAULT_READER_PREFERENCES);
  });

  it('ignores a theme that does not exist', () => {
    writeStorage(READER_PREFERENCES_KEY, JSON.stringify({ theme: 'neon' }));
    expect(loadPreferences().theme).toBe('light');
  });

  it('remembers where the reader was', () => {
    writeStorage(
      READER_PROGRESS_KEY,
      JSON.stringify({ cfi: 'epubcfi(/6/4!/4/2)', fraction: 0.42, title: 'The book', savedAt: 1 }),
    );
    const progress = loadProgress();
    expect(progress?.cfi).toBe('epubcfi(/6/4!/4/2)');
    expect(progress?.fraction).toBe(0.42);
  });

  it('has no progress when nothing was saved', () => {
    expect(loadProgress()).toBeNull();
  });

  it('reads nothing when the storage is empty', () => {
    expect(readStorage('scan2epub.nothing')).toBeNull();
  });
});

describe('the stylesheet of the reader', () => {
  it('applies the typeface, the size and the leading', () => {
    const css = buildReaderCss({
      font: 'sans',
      size: 21,
      leading: 1.8,
      margin: 20,
      theme: 'light',
      style: 'plain',
      layout: 'single',
      focus: false,
    });
    expect(css).toContain('font-size: 21px');
    expect(css).toContain('line-height: 1.8');
    expect(css).toContain('padding: 20px');
    expect(css).toContain('Inter');
  });

  it('justifies the text in the style of a book', () => {
    const css = buildReaderCss({ ...DEFAULT_READER_PREFERENCES, style: 'book' });
    expect(css).toContain('text-align: justify');
    expect(css).toContain('hyphens: auto');
    expect(css).toContain('text-indent');
  });

  it('leaves the text alone in the plain style', () => {
    const css = buildReaderCss({ ...DEFAULT_READER_PREFERENCES, style: 'plain' });
    expect(css).not.toContain('text-align: justify');
  });

  it('applies the theme', () => {
    const dark = buildReaderCss({ ...DEFAULT_READER_PREFERENCES, theme: 'dark' });
    expect(dark).toContain('#16181c');
    const sepia = buildReaderCss({ ...DEFAULT_READER_PREFERENCES, theme: 'sepia' });
    expect(sepia).toContain('#f4ecd8');
  });

  it('refuses a negative margin', () => {
    const css = buildReaderCss({ ...DEFAULT_READER_PREFERENCES, margin: -10 });
    expect(css).toContain('padding: 0px');
  });
});
