/**
 * The estimate of what a run costs.
 *
 * The local engine runs on the machine of the user and it is free. The remote
 * engines are not here yet: the API will publish their price with
 * `GET /api/engines`, and this module will use it as soon as it does.
 */

import type { EngineInfo } from './models';

/** The engines that run on the machine of the user. */
export const LOCAL_ENGINES: readonly string[] = ['tesseract'];

/** The price of a page when the engine does not publish one, in US dollars. */
export const DEFAULT_REMOTE_RATE = 0.02;

/** The size of an average scanned page, in bytes. */
export const BYTES_PER_PAGE = 200_000;

/** The estimate of the cost of a run. */
export interface CostEstimate {
  /** Whether the engine runs on the machine of the user. */
  readonly local: boolean;
  /** The price in US dollars, or `null` for a local engine. */
  readonly amount: number | null;
  /** The sentence that the interface shows. */
  readonly label: string;
  /** The number of pages that the estimate is based on. */
  readonly pages: number;
}

/** Return whether an engine runs on the machine of the user. */
export function isLocalEngine(name: string): boolean {
  return LOCAL_ENGINES.includes(name);
}

/**
 * Guess the number of pages of a PDF from its size.
 *
 * It is only used to turn a price per page into a price per book; the real
 * number of pages arrives with the summary.
 */
export function estimatePages(fileSizeBytes: number): number {
  if (!fileSizeBytes || fileSizeBytes <= 0) {
    return 0;
  }
  return Math.max(1, Math.round(fileSizeBytes / BYTES_PER_PAGE));
}

/**
 * Estimate what a run costs.
 *
 * @param engine - The engine that will do the recognition.
 * @param fileSizeBytes - The size of the PDF that will be uploaded.
 */
export function estimateCost(engine: EngineInfo | null, fileSizeBytes: number): CostEstimate {
  const pages = estimatePages(fileSizeBytes);

  if (!engine) {
    return {
      local: true,
      amount: null,
      label: 'Local engine — no cost.',
      pages,
    };
  }

  const local = engine.remote === false || isLocalEngine(engine.name);
  if (local) {
    return {
      local: true,
      amount: null,
      label: 'Local engine — no cost.',
      pages,
    };
  }

  const rate =
    typeof engine.cost_per_page === 'number' && engine.cost_per_page > 0
      ? engine.cost_per_page
      : DEFAULT_REMOTE_RATE;
  const amount = pages * rate;

  return {
    local: false,
    amount,
    label: `About $${amount.toFixed(2)} for ${pages} page${pages === 1 ? '' : 's'} ($${rate.toFixed(2)} per page).`,
    pages,
  };
}
