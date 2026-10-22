import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ReaderStore } from './reader.store';
import { READER_PREFERENCES_KEY, READER_PROGRESS_KEY } from './reader-preferences';

describe('the store of the reader', () => {
  let store: ReaderStore;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
    store = TestBed.inject(ReaderStore);
  });

  it('starts with the default settings', () => {
    expect(store.preferences().font).toBe('serif');
    expect(store.theme().id).toBe('light');
  });

  it('saves the settings', () => {
    store.setSize(24);
    store.setTheme('sepia');
    expect(store.preferences().size).toBe(24);
    expect(store.theme().id).toBe('sepia');
    expect(localStorage.getItem(READER_PREFERENCES_KEY)).toContain('sepia');
  });

  it('remembers where the reader was', () => {
    store.saveProgress({ cfi: 'epubcfi(/6/4!/4)', fraction: 0.25, title: 'The book' });
    expect(store.progress()?.fraction).toBe(0.25);
    expect(localStorage.getItem(READER_PROGRESS_KEY)).toContain('epubcfi');
  });

  it('forgets where the reader was', () => {
    store.saveProgress({ cfi: null, fraction: 0.5, title: 'The book' });
    store.clearProgress();
    expect(store.progress()).toBeNull();
  });
});
