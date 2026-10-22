import { Injectable, computed, inject, signal } from '@angular/core';

import { ApiService, apiErrorMessage } from './api.service';
import { estimateCost, type CostEstimate } from './cost';
import { DEFAULT_LANGUAGE } from './languages';
import type { ConversionSummary, EngineInfo, HealthResponse, ProgressEvent } from './models';
import { phaseById, visiblePhases, type ConversionPhase } from './phases';

/** The state of the conversion. */
export type ConversionStatus = 'idle' | 'running' | 'done' | 'error';

/**
 * The state of the whole application.
 *
 * It is a small signal store: the form, the run and the summary live here,
 * and the components only read the signals and call the methods.
 */
@Injectable({ providedIn: 'root' })
export class ConversionStore {
  private readonly api = inject(ApiService);
  private stopWatch: (() => void) | null = null;
  private ticker: ReturnType<typeof setInterval> | null = null;
  private startedAt = 0;

  /** The PDF that will be converted. */
  readonly file = signal<File | null>(null);
  /** The title of the book. */
  readonly title = signal('');
  /** The author of the book. */
  readonly author = signal('');
  /** The year of the book. */
  readonly year = signal('');
  /** The language of the recognition. */
  readonly language = signal(DEFAULT_LANGUAGE);
  /** The name of the engine that will do the recognition. */
  readonly engineName = signal('');
  /** The engines that the service offers. */
  readonly engines = signal<readonly EngineInfo[]>([]);
  /** Whether the engines have been asked for. */
  readonly enginesLoaded = signal(false);
  /** The answer of the health check. */
  readonly health = signal<HealthResponse | null>(null);
  /** The state of the conversion. */
  readonly status = signal<ConversionStatus>('idle');
  /** The summary of the last conversion. */
  readonly summary = signal<ConversionSummary | null>(null);
  /** The message of the last failure. */
  readonly error = signal<string | null>(null);
  /** The seconds that have gone by since the run started. */
  readonly elapsed = signal(0);
  /** The identifier of the job that is running. */
  readonly jobId = signal<string | null>(null);
  /** The stage that the service is in. */
  readonly stage = signal('upload');
  /** What the service is doing. */
  readonly message = signal('');
  /** The percentage of the stage that is done, between 0 and 100. */
  readonly stagePercent = signal(0);
  /** The page that is being worked on. */
  readonly page = signal<number | null>(null);
  /** The number of pages of the book. */
  readonly total = signal<number | null>(null);
  /** The stages that the service has reached. */
  readonly stages = signal<ReadonlySet<string>>(new Set<string>());

  /** The engine that is selected. */
  readonly selectedEngine = computed<EngineInfo | null>(
    () => this.engines().find((engine) => engine.name === this.engineName()) ?? null,
  );

  /** What the run is expected to cost. */
  readonly cost = computed<CostEstimate>(() =>
    estimateCost(this.selectedEngine(), this.file()?.size ?? 0),
  );

  /** The stages that the interface shows. */
  readonly phases = computed<readonly ConversionPhase[]>(() => visiblePhases(this.stages()));

  /** The stage that the interface is showing. */
  readonly phase = computed<ConversionPhase>(() => {
    const current = phaseById(this.stage());
    return current ?? this.phases()[0] ?? { id: 'upload', label: 'Uploading the scan' };
  });

  /** The index of the stage that the interface is showing. */
  readonly phaseIndex = computed<number>(() => {
    const phases = this.phases();
    const index = phases.findIndex((phase) => phase.id === this.phase().id);
    return index < 0 ? 0 : index;
  });

  /**
   * The percentage of the run that is done.
   *
   * The service tells how much of the stage is done, so the bar moves with
   * the real progress of the pipeline.
   */
  readonly progress = computed<number>(() => {
    const phases = this.phases();
    if (phases.length === 0) {
      return 0;
    }
    const index = this.phaseIndex();
    const fraction = Math.min(1, Math.max(0, this.stagePercent() / 100));
    return Math.min(100, ((index + fraction) / phases.length) * 100);
  });

  /** Whether a PDF has been chosen and no run is in flight. */
  readonly canConvert = computed<boolean>(
    () => this.file() !== null && this.status() !== 'running',
  );

  /** Whether the conversion is running. */
  readonly isRunning = computed<boolean>(() => this.status() === 'running');

  /** The path of the generated EPUB, when there is one. */
  readonly downloadUrl = computed<string>(() => this.summary()?.download ?? '');

  /** Ask the service about the engines and about itself. */
  async loadEngines(): Promise<void> {
    try {
      const [engines, health] = await Promise.all([
        this.api.engines(),
        this.api.health().catch(() => null),
      ]);
      this.engines.set(engines);
      this.health.set(health);
      const current = this.engineName();
      const usable = engines.find((engine) => engine.available);
      if (!current || !engines.some((engine) => engine.name === current)) {
        this.engineName.set(usable?.name ?? engines[0]?.name ?? '');
      }
    } catch (error) {
      this.error.set(apiErrorMessage(error));
    } finally {
      this.enginesLoaded.set(true);
    }
  }

  /** Choose the PDF that will be converted. */
  setFile(file: File | null): void {
    this.file.set(file);
  }

  /** The title suggested by the name of the file, used as a placeholder. */
  readonly suggestedTitle = computed<string>(() => {
    const file = this.file();
    if (!file) {
      return '';
    }
    return file.name
      .replace(/\.pdf$/i, '')
      .replace(/[_-]+/g, ' ')
      .trim();
  });

  /** Set the title of the book. */
  setTitle(title: string): void {
    this.title.set(title);
  }

  /** Set the author of the book. */
  setAuthor(author: string): void {
    this.author.set(author);
  }

  /** Set the year of the book. */
  setYear(year: string): void {
    this.year.set(year);
  }

  /** Set the language of the recognition. */
  setLanguage(language: string): void {
    this.language.set(language);
  }

  /** Set the engine that will do the recognition. */
  setEngine(name: string): void {
    this.engineName.set(name);
  }

  /**
   * Convert the chosen PDF.
   *
   * The file is queued and the work is done in the background, so the
   * browser never waits for the whole book. The progress arrives on the
   * stream of the events of the job.
   *
   * @returns The summary of the conversion, or `null` when it failed.
   */
  async start(): Promise<ConversionSummary | null> {
    const file = this.file();
    if (!file) {
      this.error.set('Choose a PDF first.');
      this.status.set('error');
      return null;
    }

    this.error.set(null);
    this.summary.set(null);
    this.elapsed.set(0);
    this.status.set('running');
    this.stage.set('upload');
    this.message.set('Uploading the scan');
    this.stagePercent.set(0);
    this.page.set(null);
    this.total.set(null);
    this.stages.set(new Set<string>(['upload']));
    this.startedAt = Date.now();
    this.startTicker();

    try {
      const job = await this.api.createJob({
        file,
        title: this.title().trim(),
        author: this.author().trim(),
        year: this.year().trim(),
        language: this.language(),
        engine: this.engineName(),
      });
      this.jobId.set(job.id);
      return await this.follow(job.id);
    } catch (error) {
      this.error.set(apiErrorMessage(error));
      this.status.set('error');
      return null;
    } finally {
      this.stopTicker();
    }
  }

  /** Forget the current run and start again. */
  reset(): void {
    this.stopWatching();
    this.status.set('idle');
    this.summary.set(null);
    this.error.set(null);
    this.elapsed.set(0);
    this.jobId.set(null);
  }

  /**
   * Follow the progress of a job until it is over.
   *
   * @param jobId - The identifier of the job.
   */
  private follow(jobId: string): Promise<ConversionSummary | null> {
    return new Promise<ConversionSummary | null>((resolve) => {
      this.stopWatch = this.api.watchJob(jobId, (event) => {
        if (event.stage === 'done') {
          this.stopWatching();
          const summary = event.summary ?? null;
          this.summary.set(summary);
          this.status.set('done');
          resolve(summary);
          return;
        }
        if (event.stage === 'error') {
          this.stopWatching();
          this.error.set(event.message ?? event.error ?? 'The conversion failed.');
          this.status.set('error');
          resolve(null);
          return;
        }
        this.applyProgress(event);
      });
    });
  }

  /** Show the progress that the service reports. */
  private applyProgress(event: ProgressEvent): void {
    if (event.stage) {
      this.stage.set(event.stage);
      this.stages.update((stages) => new Set([...stages, event.stage]));
    }
    if (event.message) {
      this.message.set(event.message);
    }
    if (typeof event.percent === 'number') {
      this.stagePercent.set(event.percent);
    }
    if (typeof event.page === 'number') {
      this.page.set(event.page);
    }
    if (typeof event.total === 'number') {
      this.total.set(event.total);
    }
  }

  private stopWatching(): void {
    if (this.stopWatch !== null) {
      this.stopWatch();
      this.stopWatch = null;
    }
  }

  private startTicker(): void {
    this.stopTicker();
    this.ticker = setInterval(() => {
      this.elapsed.set((Date.now() - this.startedAt) / 1000);
    }, 250);
  }

  private stopTicker(): void {
    if (this.ticker !== null) {
      clearInterval(this.ticker);
      this.ticker = null;
    }
  }
}
