import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { ConversionStore } from './conversion.store';

/**
 * Keep the pages that need a book away from the users that have none.
 *
 * The reader and the summary are only reachable once a conversion has
 * answered; otherwise the user goes back to the upload.
 */
export const requireConversion: CanActivateFn = () => {
  const store = inject(ConversionStore);
  const router = inject(Router);
  return store.summary() ? true : router.createUrlTree(['/']);
};

/**
 * Keep the conversion page away from the users that have not chosen a PDF.
 */
export const requireFile: CanActivateFn = () => {
  const store = inject(ConversionStore);
  const router = inject(Router);
  return store.file() ? true : router.createUrlTree(['/']);
};
