import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversionStore } from '../../core/conversion.store';
import { UploadComponent } from './upload';

/** The parts of the component that the tests drive. */
interface UploadInternals {
  onDrop(event: DragEvent): void;
  onFileChosen(event: Event): void;
  convert(): Promise<void>;
  rejection(): string | null;
}

function dropEvent(file: File): DragEvent {
  return {
    preventDefault: () => undefined,
    dataTransfer: { files: [file] },
  } as unknown as DragEvent;
}

describe('the upload screen', () => {
  let store: ConversionStore;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [UploadComponent],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    store = TestBed.inject(ConversionStore);
    router = TestBed.inject(Router);
  });

  it('takes the PDF that is dropped on the page', () => {
    const fixture = TestBed.createComponent(UploadComponent);
    const component = fixture.componentInstance as unknown as UploadInternals;
    const file = new File(['%PDF-1.4'], 'book.pdf', { type: 'application/pdf' });

    component.onDrop(dropEvent(file));

    expect(store.file()).toBe(file);
    expect(component.rejection()).toBeNull();
  });

  it('refuses a file that is not a PDF', () => {
    const fixture = TestBed.createComponent(UploadComponent);
    const component = fixture.componentInstance as unknown as UploadInternals;

    component.onDrop(dropEvent(new File(['hello'], 'notes.txt', { type: 'text/plain' })));

    expect(store.file()).toBeNull();
    expect(component.rejection()).toContain('Only PDF');
  });

  it('sends the user to the conversion', async () => {
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(UploadComponent);
    const component = fixture.componentInstance as unknown as UploadInternals;
    store.setFile(new File(['%PDF-1.4'], 'book.pdf', { type: 'application/pdf' }));

    await component.convert();

    expect(navigate).toHaveBeenCalledWith(['/progress']);
  });

  it('does not send the user without a file', async () => {
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(UploadComponent);
    const component = fixture.componentInstance as unknown as UploadInternals;

    await component.convert();

    expect(navigate).not.toHaveBeenCalled();
  });
});
