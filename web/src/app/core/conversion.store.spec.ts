import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversionStore } from './conversion.store';
import type { ConversionSummary } from './models';

const summary: ConversionSummary = {
  title: 'The book',
  pages: 120,
  chapters: 4,
  size: 2048,
  duration_seconds: 12.5,
  removed_running_heads: ['The Book'],
  removed_page_numbers: 120,
  joined_hyphens: 33,
  merged_paragraphs: 8,
  footnotes: 2,
  epub_valid: true,
  epub_warnings: [],
  download: '/api/download/job/book.epub',
};

/** A stand-in for the stream of the events, which jsdom does not have. */
class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly listeners = new Map<string, ((event: Event) => void)[]>();
  closed = false;

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener): void {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener as (event: Event) => void);
    this.listeners.set(type, listeners);
  }

  onmessage: ((event: Event) => void) | null = null;

  close(): void {
    this.closed = true;
  }

  /** Send an event to the listeners of the stream. */
  emit(type: string, data: unknown): void {
    const event = { type, data: JSON.stringify(data) } as MessageEvent<string>;
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

function pdf(name = 'book.pdf'): File {
  return new File(['%PDF-1.4'], name, { type: 'application/pdf' });
}

/** Wait for the promises of the store to move on. */
async function tick(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('the store of the conversion', () => {
  let store: ConversionStore;
  let http: HttpTestingController;

  beforeEach(() => {
    FakeEventSource.instances = [];
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(ConversionStore);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
    vi.unstubAllGlobals();
  });

  it('starts idle', () => {
    expect(store.status()).toBe('idle');
    expect(store.canConvert()).toBe(false);
    expect(store.summary()).toBeNull();
  });

  it('asks the service for the engines', async () => {
    const promise = store.loadEngines();
    http
      .expectOne('/api/engines')
      .flush([{ name: 'tesseract', available: true, details: 'version 5' }]);
    http.expectOne('/health').flush({ status: 'ok', version: '1.2.3', engines: ['tesseract'] });
    await promise;

    expect(store.engines()).toHaveLength(1);
    expect(store.engineName()).toBe('tesseract');
    expect(store.health()?.version).toBe('1.2.3');
    expect(store.enginesLoaded()).toBe(true);
  });

  it('suggests a title from the name of the file, without filling it in', () => {
    store.setFile(pdf('my_old-book.pdf'));
    expect(store.suggestedTitle()).toBe('my old book');
    expect(store.title()).toBe('');
  });

  it('refuses to convert without a file', async () => {
    const result = await store.start();
    expect(result).toBeNull();
    expect(store.status()).toBe('error');
    expect(store.error()).toContain('Choose a PDF');
  });

  it('queues the file and keeps the summary', async () => {
    store.setFile(pdf());
    store.setAuthor('Anónimo');
    const promise = store.start();

    const request = http.expectOne('/api/jobs');
    const body = request.request.body as FormData;
    expect(body.get('file')).toBeInstanceOf(File);
    expect(body.get('author')).toBe('Anónimo');
    expect(body.get('language')).toBe('spa');
    request.flush({ id: 'job-1', status: 'queued', created_at: '', updated_at: '', error: null });
    await tick();

    const stream = FakeEventSource.instances[0];
    expect(stream.url).toContain('/api/jobs/job-1/events');
    stream.emit('done', { summary });

    const result = await promise;
    expect(result?.pages).toBe(120);
    expect(store.status()).toBe('done');
    expect(store.downloadUrl()).toBe('/api/download/job/book.epub');
  });

  it('shows the real stage of the service', async () => {
    store.setFile(pdf());
    const promise = store.start();
    http
      .expectOne('/api/jobs')
      .flush({ id: 'job-2', status: 'queued', created_at: '', updated_at: '', error: null });
    await tick();

    const stream = FakeEventSource.instances[0];
    stream.emit('ocr', { message: 'Page 3 recognised', page: 3, total: 10, percent: 30 });
    expect(store.stage()).toBe('ocr');
    expect(store.page()).toBe(3);
    expect(store.total()).toBe(10);
    expect(store.phaseIndex()).toBe(3);

    stream.emit('done', { summary });
    await promise;
  });

  it('keeps the message of a failure of the service', async () => {
    store.setFile(pdf());
    const promise = store.start();
    http
      .expectOne('/api/jobs')
      .flush({ id: 'job-3', status: 'queued', created_at: '', updated_at: '', error: null });
    await tick();

    FakeEventSource.instances[0].emit('error', { message: 'The pages could not be read.' });
    await promise;

    expect(store.status()).toBe('error');
    expect(store.error()).toBe('The pages could not be read.');
    expect(store.summary()).toBeNull();
  });

  it('keeps the message of a failure of the upload', async () => {
    store.setFile(pdf());
    const promise = store.start();
    http
      .expectOne('/api/jobs')
      .flush({ detail: 'The file is empty.' }, { status: 400, statusText: 'Bad Request' });
    await promise;

    expect(store.status()).toBe('error');
    expect(store.error()).toBe('The file is empty.');
    expect(store.summary()).toBeNull();
  });

  it('forgets everything when it is reset', async () => {
    store.setFile(pdf());
    const promise = store.start();
    http
      .expectOne('/api/jobs')
      .flush({ id: 'job-4', status: 'queued', created_at: '', updated_at: '', error: null });
    await tick();
    FakeEventSource.instances[0].emit('done', { summary });
    await promise;

    store.reset();
    expect(store.status()).toBe('idle');
    expect(store.summary()).toBeNull();
    expect(store.elapsed()).toBe(0);
  });
});
