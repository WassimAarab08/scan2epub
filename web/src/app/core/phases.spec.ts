import { describe, expect, it } from 'vitest';

import { CONVERSION_PHASES, phaseById, visiblePhases } from './phases';

describe('the stages of a conversion', () => {
  it('starts with the upload', () => {
    expect(CONVERSION_PHASES[0].id).toBe('upload');
  });

  it('knows the stages of the pipeline', () => {
    expect(phaseById('ocr')?.label).toBe('Recognising the text');
    expect(phaseById('epub')?.label).toBe('Writing the EPUB');
    expect(phaseById('nope')).toBeNull();
  });

  it('hides the correction when the service does not use it', () => {
    const phases = visiblePhases(new Set(['upload', 'ocr']));
    expect(phases.map((phase) => phase.id)).not.toContain('correct');
  });

  it('shows the correction when the service uses it', () => {
    const phases = visiblePhases(new Set(['upload', 'ocr', 'correct']));
    expect(phases.map((phase) => phase.id)).toContain('correct');
  });

  it('always keeps the upload', () => {
    const phases = visiblePhases(new Set<string>());
    expect(phases[0].id).toBe('upload');
  });
});
