import { describe, expect, it } from 'vitest';

import { DEFAULT_REMOTE_RATE, estimateCost, estimatePages, isLocalEngine } from './cost';
import type { EngineInfo } from './models';

const local: EngineInfo = {
  name: 'tesseract',
  available: true,
  details: 'version 5.3.0',
};

const remote: EngineInfo = {
  name: 'remote-ocr',
  available: true,
  details: 'a remote engine',
  remote: true,
  cost_per_page: 0.05,
};

describe('the estimate of the cost', () => {
  it('knows the local engines', () => {
    expect(isLocalEngine('tesseract')).toBe(true);
    expect(isLocalEngine('remote-ocr')).toBe(false);
  });

  it('is free when the engine is local', () => {
    const estimate = estimateCost(local, 4_000_000);
    expect(estimate.local).toBe(true);
    expect(estimate.amount).toBeNull();
    expect(estimate.label).toContain('no cost');
  });

  it('adds the pages of a remote engine', () => {
    const estimate = estimateCost(remote, 4_000_000);
    expect(estimate.local).toBe(false);
    expect(estimate.pages).toBe(20);
    expect(estimate.amount).toBeCloseTo(1);
    expect(estimate.label).toContain('$1.00');
  });

  it('uses the default rate when the engine does not publish one', () => {
    const estimate = estimateCost({ ...remote, cost_per_page: null }, 1_000_000);
    expect(estimate.amount).toBeCloseTo(estimate.pages * DEFAULT_REMOTE_RATE);
  });

  it('guesses the pages from the size of the file', () => {
    expect(estimatePages(0)).toBe(0);
    expect(estimatePages(200_000)).toBe(1);
    expect(estimatePages(1_000_000)).toBe(5);
  });

  it('is free when there is no engine at all', () => {
    expect(estimateCost(null, 1_000_000).local).toBe(true);
  });
});
