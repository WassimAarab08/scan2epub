import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { App } from './app';

/** Let the promises of the service and the rendering settle. */
async function settle(fixture: ComponentFixture<App>): Promise<void> {
  await fixture.whenStable();
  await new Promise((resolve) => setTimeout(resolve, 0));
  await fixture.whenStable();
}

describe('the shell of the application', () => {
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('shows the name of the project', async () => {
    const fixture = TestBed.createComponent(App);
    await settle(fixture);

    http
      .expectOne('/api/engines')
      .flush([{ name: 'tesseract', available: true, details: 'version 5' }]);
    http.expectOne('/health').flush({ status: 'ok', version: '1.0.0', engines: ['tesseract'] });
    await settle(fixture);

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('scan2epub');
  });

  it('shows the version of the service', async () => {
    const fixture = TestBed.createComponent(App);
    await settle(fixture);

    http
      .expectOne('/api/engines')
      .flush([{ name: 'tesseract', available: true, details: 'version 5' }]);
    http.expectOne('/health').flush({ status: 'ok', version: '2.1.0', engines: ['tesseract'] });
    await settle(fixture);

    expect((fixture.nativeElement as HTMLElement).textContent).toContain('2.1.0');
  });
});
