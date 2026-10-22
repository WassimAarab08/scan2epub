import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';

import { ConversionStore } from './core/conversion.store';
import { ReaderStore } from './core/reader.store';

/**
 * The shell of the application: the header, the pages and the footer.
 *
 * The pages of the conversion fill the whole width of the window and scroll
 * with the page. The reader is the exception: it takes the whole height of
 * the window and manages its own scrolling.
 */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
})
export class App {
  protected readonly store = inject(ConversionStore);
  protected readonly reader = inject(ReaderStore);
  private readonly router = inject(Router);

  /** Whether the reader is open, and the page must not scroll. */
  protected readonly readerRoute = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects.startsWith('/reader')),
    ),
    { initialValue: this.router.url.startsWith('/reader') },
  );

  constructor() {
    void this.store.loadEngines();
  }
}
