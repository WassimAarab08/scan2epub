import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ConversionStore } from '../../core/conversion.store';
import { formatDuration } from '../../core/format';
import { CONVERSION_PHASES } from '../../core/phases';

/**
 * The second screen: the stages of the conversion.
 *
 * The API answers with the whole book at once, so the stages are driven by
 * the time that has gone by. The numbers of the summary arrive with the
 * answer and are shown on the next screen.
 */
@Component({
  selector: 'app-progress',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './progress.html',
})
export class ProgressComponent {
  protected readonly store = inject(ConversionStore);
  private readonly router = inject(Router);

  /** Every stage of the conversion. */
  protected readonly phases = CONVERSION_PHASES;

  /** The name of the file that is being converted. */
  protected readonly fileName = computed(() => this.store.file()?.name ?? '');

  /** The elapsed time, in a readable way. */
  protected readonly elapsed = computed(() => formatDuration(this.store.elapsed()));

  constructor() {
    void this.run();
  }

  /** Start the conversion, unless it is already running. */
  private async run(): Promise<void> {
    const status = this.store.status();
    if (status === 'done') {
      await this.router.navigate(['/result']);
      return;
    }
    if (status === 'running') {
      return;
    }
    const summary = await this.store.start();
    if (summary) {
      await this.router.navigate(['/result']);
    }
  }

  /** Try the conversion again after a failure. */
  protected async retry(): Promise<void> {
    const summary = await this.store.start();
    if (summary) {
      await this.router.navigate(['/result']);
    }
  }
}
