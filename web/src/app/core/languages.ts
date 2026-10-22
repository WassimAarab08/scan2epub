/**
 * The languages that the OCR engine understands.
 *
 * The list is static on purpose: it describes the models that ship with the
 * recogniser, and it does not change with the installation.
 */

/** One language of the OCR engine. */
export interface OcrLanguage {
  /** The code that the API expects, for example `spa_old`. */
  readonly code: string;
  /** The name of the language, in English. */
  readonly label: string;
}

/** Every language that can be selected for the recognition. */
export const OCR_LANGUAGES: readonly OcrLanguage[] = [
  { code: 'spa', label: 'Spanish (modern spelling)' },
  { code: 'spa_old', label: 'Spanish (before 1900)' },
  { code: 'eng', label: 'English' },
  { code: 'fra', label: 'French' },
  { code: 'deu', label: 'German' },
  { code: 'ita', label: 'Italian' },
  { code: 'por', label: 'Portuguese' },
];

/** The language that is selected by default. */
export const DEFAULT_LANGUAGE = 'spa';

/** Return the name of a language, or its code when it is unknown. */
export function languageLabel(code: string): string {
  return OCR_LANGUAGES.find((language) => language.code === code)?.label ?? code;
}
