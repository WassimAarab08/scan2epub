import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ConversionStore } from '../../core/conversion.store';
import { formatBytes, formatDuration, formatNumber } from '../../core/format';

/**
 * The third screen: what the conversion did.
 *
 * Every number comes from the summary of the API; nothing is estimated here.
 */
@Component({
  selector: 'app-result',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './result.html',
})
export class ResultComponent {
  protected readonly store = inject(ConversionStore);

  /** The summary of the conversion. */
  protected readonly summary = computed(() => this.store.summary());

  /** The title of the book. */
  protected readonly title = computed(() => this.summary()?.title ?? '');

  /** The name of the file that will be downloaded. */
  protected readonly fileName = computed(() => {
    const download = this.summary()?.download ?? '';
    return download.split('/').pop() ?? 'book.epub';
  });

  /** The size of the book, in a readable way. */
  protected readonly size = computed(() => formatBytes(this.summary()?.size ?? 0));

  /** The duration of the run, in a readable way. */
  protected readonly duration = computed(() =>
    formatDuration(this.summary()?.duration_seconds ?? 0),
  );

  /** The running heads that were removed. */
  protected readonly runningHeads = computed(() => this.summary()?.removed_running_heads ?? []);

  /** Format a number with the separators of the English language. */
  protected readonly formatNumber = formatNumber;
}
