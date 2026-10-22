/**
 * The checks that the chosen PDF has to pass.
 *
 * The API refuses the files that are not PDFs and the ones that are too
 * large; the interface refuses them earlier, with a clear message.
 */

import { formatBytes } from './format';

export { formatBytes };

/** The largest PDF the API accepts, in bytes. */
export const MAX_UPLOAD_BYTES = 512 * 1024 * 1024;

/** The content types that the API accepts. */
export const ACCEPTED_TYPES: readonly string[] = [
  'application/pdf',
  'application/octet-stream',
  'binary/octet-stream',
];

/** The parts of a file that the checks look at. */
export interface UploadCandidate {
  readonly name: string;
  readonly size: number;
  readonly type?: string;
}

/**
 * Check a file before it is uploaded.
 *
 * @returns The reason why the file is refused, or `null` when it is fine.
 */
export function validateUpload(file: UploadCandidate): string | null {
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    return 'Only PDF files can be converted.';
  }
  if (file.type && !ACCEPTED_TYPES.includes(file.type)) {
    return `The type "${file.type}" is not a PDF.`;
  }
  if (file.size <= 0) {
    return 'The file is empty.';
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return 'The file is larger than 512 MiB.';
  }
  return null;
}
