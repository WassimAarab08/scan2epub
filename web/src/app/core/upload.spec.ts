import { describe, expect, it } from 'vitest';

import { formatBytes, formatDuration, formatNumber } from './format';
import { MAX_UPLOAD_BYTES, validateUpload } from './upload';

describe('the checks of the upload', () => {
  it('accepts a PDF', () => {
    expect(validateUpload({ name: 'book.pdf', size: 1000, type: 'application/pdf' })).toBeNull();
  });

  it('accepts a PDF without a content type', () => {
    expect(validateUpload({ name: 'book.PDF', size: 1000, type: '' })).toBeNull();
  });

  it('refuses a file that is not a PDF', () => {
    expect(validateUpload({ name: 'notes.txt', size: 1000, type: 'text/plain' })).toContain(
      'Only PDF',
    );
  });

  it('refuses a content type that is not a PDF', () => {
    expect(validateUpload({ name: 'book.pdf', size: 1000, type: 'image/png' })).toContain(
      'not a PDF',
    );
  });

  it('refuses an empty file', () => {
    expect(validateUpload({ name: 'book.pdf', size: 0, type: 'application/pdf' })).toContain(
      'empty',
    );
  });

  it('refuses a file that is too large', () => {
    expect(
      validateUpload({
        name: 'book.pdf',
        size: MAX_UPLOAD_BYTES + 1,
        type: 'application/pdf',
      }),
    ).toContain('512');
  });
});

describe('the readable sizes', () => {
  it('writes the bytes', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('writes the kibibytes', () => {
    expect(formatBytes(2048)).toBe('2.0 KiB');
  });

  it('writes the mebibytes', () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MiB');
  });

  it('writes the durations', () => {
    expect(formatDuration(12)).toBe('12 s');
    expect(formatDuration(75)).toBe('1 min 15 s');
  });

  it('writes the numbers', () => {
    expect(formatNumber(1234)).toBe('1,234');
  });
});
