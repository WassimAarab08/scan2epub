import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import type {
  ConversionRequest,
  ConversionSummary,
  EngineInfo,
  HealthResponse,
  JobResponse,
  ProgressEvent,
} from './models';

/**
 * The client of the scan2epub REST API.
 *
 * Every method returns a promise: the interface is driven by signals, and the
 * observable plumbing of the HTTP client stays inside this service.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  /**
   * The names of the events of the stream of the progress.
   *
   * The stream names every event after the stage of the pipeline, so the
   * client has to listen to each one of them.
   */
  private static readonly STAGES = [
    'start',
    'ingest',
    'preprocess',
    'ocr',
    'clean',
    'correct',
    'structure',
    'epub',
    'validate',
    'done',
    'error',
  ] as const;

  private readonly http = inject(HttpClient);

  /** Ask the service whether it is alive. */
  async health(): Promise<HealthResponse> {
    return firstValueFrom(this.http.get<HealthResponse>('/health'));
  }

  /** List the OCR engines and whether they can be used. */
  async engines(): Promise<EngineInfo[]> {
    return firstValueFrom(this.http.get<EngineInfo[]>('/api/engines'));
  }

  /**
   * Convert a PDF into an EPUB.
   *
   * The request is sent as a multipart form, exactly as the API expects it.
   * The answer comes back when the book is finished, which can take a while.
   */
  async convert(request: ConversionRequest): Promise<ConversionSummary> {
    const body = this.buildForm(request);
    return firstValueFrom(this.http.post<ConversionSummary>('/api/convert', body));
  }

  /**
   * Queue a conversion and return the job at once.
   *
   * The work is done in the background, so the browser never waits for the
   * whole book and the progress can be followed on the stream of the events.
   */
  async createJob(request: ConversionRequest): Promise<JobResponse> {
    const body = this.buildForm(request);
    return firstValueFrom(this.http.post<JobResponse>('/api/jobs', body));
  }

  /** Return the state of a job. */
  async job(jobId: string): Promise<JobResponse> {
    return firstValueFrom(this.http.get<JobResponse>(`/api/jobs/${encodeURIComponent(jobId)}`));
  }

  /**
   * Follow the progress of a job.
   *
   * The events arrive on a Server-Sent Events stream, the same one that the
   * API offers. The function returns the way to stop listening.
   *
   * @param jobId - The identifier of the job.
   * @param onEvent - Called with every event of the progress.
   */
  watchJob(jobId: string, onEvent: (event: ProgressEvent) => void): () => void {
    const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
    const handler = (event: Event): void => {
      const message = event as MessageEvent<string>;
      try {
        const payload = JSON.parse(message.data) as Partial<ProgressEvent>;
        onEvent({ ...payload, stage: message.type || payload.stage || '' });
      } catch {
        /* An event that cannot be read is ignored: the next one will come. */
      }
    };
    for (const stage of ApiService.STAGES) {
      source.addEventListener(stage, handler);
    }
    source.onmessage = handler;
    return () => source.close();
  }

  private buildForm(request: ConversionRequest): FormData {
    const body = new FormData();
    body.append('file', request.file, request.file.name);
    if (request.title) {
      body.append('title', request.title);
    }
    if (request.author) {
      body.append('author', request.author);
    }
    if (request.year) {
      body.append('year', request.year);
    }
    if (request.language) {
      body.append('language', request.language);
    }
    if (request.engine) {
      body.append('engine', request.engine);
    }
    return body;
  }
}

/**
 * Return the message that explains a failure of the API.
 *
 * The service answers with `{"detail": "..."}`, and the network failures are
 * described in English too, because the interface is in English.
 */
export function apiErrorMessage(error: unknown): string {
  if (error instanceof HttpErrorResponse) {
    const detail = (error.error as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string' && detail.length > 0) {
      return detail;
    }
    if (error.status === 0) {
      return 'The service is unreachable. Is `scan2epub serve` running?';
    }
    if (error.status === 413) {
      return 'The file is too large.';
    }
    if (error.status === 415) {
      return 'The file must be a PDF.';
    }
    return `The service answered with the error ${error.status}.`;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return 'The conversion failed.';
}
