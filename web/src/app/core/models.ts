/**
 * The shapes of the answers of the scan2epub REST API.
 *
 * They mirror the models of `scan2epub.api.app`; the optional fields are the
 * ones that the service will publish when the remote engines arrive.
 */

/** The answer of `GET /health`. */
export interface HealthResponse {
  readonly status: string;
  readonly version: string;
  readonly engines: readonly string[];
}

/** The description of one OCR engine, from `GET /api/engines`. */
export interface EngineInfo {
  readonly name: string;
  readonly available: boolean;
  readonly details: string;
  /** The price of a page, in US dollars. Only the remote engines have it. */
  readonly cost_per_page?: number | null;
  /** Whether the engine runs somewhere else. */
  readonly remote?: boolean;
}

/** The summary of a conversion, from `POST /api/convert`. */
export interface ConversionSummary {
  readonly title: string;
  readonly pages: number;
  readonly chapters: number;
  readonly size: number;
  readonly duration_seconds: number;
  readonly removed_running_heads: readonly string[];
  readonly removed_page_numbers: number;
  readonly joined_hyphens: number;
  readonly merged_paragraphs: number;
  readonly footnotes: number;
  readonly epub_valid: boolean;
  readonly epub_warnings: readonly string[];
  readonly download: string;
}

/** The metadata that travels with the uploaded PDF. */
export interface ConversionRequest {
  readonly file: File;
  readonly title: string;
  readonly author: string;
  readonly year: string;
  readonly language: string;
}

/** The state of a job of the queue, from `POST /api/jobs`. */
export interface JobResponse {
  readonly id: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly error: string | null;
  readonly download: string | null;
  /** The numbers of the conversion, when the job is finished. */
  readonly summary?: ConversionSummary | null;
}

/**
 * One event of the progress of a job.
 *
 * The events arrive on the stream of `GET /api/jobs/{id}/events`; the name
 * of the event is the name of the stage of the pipeline.
 */
export interface ProgressEvent {
  /** The name of the stage: `ingest`, `ocr`, `epub`, `done`… */
  readonly stage: string;
  /** What the pipeline is doing. */
  readonly message?: string;
  /** The percentage of the stage that is done. */
  readonly percent?: number;
  /** The page that is being worked on. */
  readonly page?: number;
  /** The number of pages of the book. */
  readonly total?: number;
  /** The numbers of the conversion, in the event that ends the job. */
  readonly summary?: ConversionSummary;
  /** The reason why the conversion failed. */
  readonly error?: string;
}
