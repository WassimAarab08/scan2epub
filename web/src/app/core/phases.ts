/**
 * The stages of a conversion.
 *
 * The service does the work in the background and tells the browser which
 * stage it is in, so the interface shows the real progress and not an
 * estimate. The identifiers below are the names of the stages of the
 * pipeline.
 */

/** One stage of the conversion. */
export interface ConversionPhase {
  /** The identifier of the stage. */
  readonly id: string;
  /** The name of the stage, in English. */
  readonly label: string;
  /** Whether the stage only happens with some settings. */
  readonly optional?: boolean;
}

/** Every stage, in the order in which the pipeline runs them. */
export const CONVERSION_PHASES: readonly ConversionPhase[] = [
  { id: 'upload', label: 'Uploading the scan' },
  { id: 'ingest', label: 'Reading the pages' },
  { id: 'preprocess', label: 'Cleaning the images' },
  { id: 'ocr', label: 'Recognising the text' },
  { id: 'clean', label: 'Cleaning the text' },
  { id: 'correct', label: 'Correcting the text', optional: true },
  { id: 'structure', label: 'Rebuilding the structure' },
  { id: 'epub', label: 'Writing the EPUB' },
  { id: 'validate', label: 'Validating the book' },
];

/**
 * Return the stage that matches an identifier.
 *
 * @param id - The identifier of the stage, as the service names it.
 */
export function phaseById(id: string): ConversionPhase | null {
  return CONVERSION_PHASES.find((phase) => phase.id === id) ?? null;
}

/**
 * Return the stages that the interface shows.
 *
 * The correction with a model only happens when the service is set up with
 * one, so that stage is only shown when the service has used it.
 *
 * @param used - The identifiers of the stages that the service has reached.
 */
export function visiblePhases(used: ReadonlySet<string>): readonly ConversionPhase[] {
  return CONVERSION_PHASES.filter(
    (phase) => !phase.optional || used.has(phase.id) || phase.id === 'upload',
  );
}
