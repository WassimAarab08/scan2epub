import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { ConversionStore } from '../../core/conversion.store';
import { OCR_LANGUAGES } from '../../core/languages';
import { formatBytes, validateUpload } from '../../core/upload';

/**
 * The first screen: the PDF, the metadata and the engine.
 *
 * The state lives in the store; this component only reads it and forwards
 * what the user types.
 */
@Component({
  selector: 'app-upload',
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './upload.html',
})
export class UploadComponent {
  protected readonly store = inject(ConversionStore);
  private readonly router = inject(Router);

  /** The languages that the recognition understands. */
  protected readonly languages = OCR_LANGUAGES;

  /** Whether a file is being dragged over the page. */
  protected readonly dragging = signal(false);

  /** The reason why the last chosen file was refused. */
  protected readonly rejection = signal<string | null>(null);

  /** The size of the chosen file, in a readable way. */
  protected readonly fileSize = computed(() => {
    const file = this.store.file();
    return file ? formatBytes(file.size) : '';
  });

  /** Whether the form can be sent. */
  protected readonly ready = computed(() => this.store.file() !== null && !this.store.isRunning());

  /** Accept a file that was dropped on the page. */
  protected onDragOver(event: DragEvent): void {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
    this.dragging.set(true);
  }

  /** Stop showing the drop zone as active. */
  protected onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
  }

  /** Take the file that was dropped on the page. */
  protected onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      this.accept(file);
    }
  }

  /** Take the file that was chosen with the file picker. */
  protected onFileChosen(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (file) {
      this.accept(file);
    }
  }

  /** Forget the chosen file. */
  protected clearFile(): void {
    this.store.setFile(null);
    this.rejection.set(null);
  }

  /** Send the form to the conversion. */
  protected async convert(): Promise<void> {
    if (!this.ready()) {
      return;
    }
    await this.router.navigate(['/progress']);
  }

  private accept(file: File): void {
    const problem = validateUpload(file);
    if (problem) {
      this.rejection.set(problem);
      this.store.setFile(null);
      return;
    }
    this.rejection.set(null);
    this.store.setFile(file);
  }
}
