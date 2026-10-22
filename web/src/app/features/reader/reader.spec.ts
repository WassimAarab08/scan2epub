import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { ConversionStore } from '../../core/conversion.store';
import { ReaderComponent } from './reader';

/** The parts of the component that the tests read. */
interface ReaderInternals {
  error(): string | null;
  ready(): boolean;
}

describe('the reader', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [ReaderComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
  });

  it('complains when there is no book to read', async () => {
    const fixture = TestBed.createComponent(ReaderComponent);
    await fixture.whenStable();
    const component = fixture.componentInstance as unknown as ReaderInternals;

    expect(component.ready()).toBe(false);
    expect(component.error()).toContain('no book');
  });

  it('does not open anything without a book', async () => {
    const store = TestBed.inject(ConversionStore);
    expect(store.summary()).toBeNull();

    const fixture = TestBed.createComponent(ReaderComponent);
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('foliate-view')).toBeNull();
  });
});
