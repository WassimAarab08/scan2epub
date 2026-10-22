import { ErrorHandler, Injectable } from '@angular/core';

/**
 * The handler of the errors of the application.
 *
 * The paginator of foliate-js observes the size of the book, and the browser
 * complains when the observation and the layout chase each other. It is a
 * known quirk that does not break anything, so it is not reported.
 */
@Injectable()
export class AppErrorHandler implements ErrorHandler {
  handleError(error: unknown): void {
    if (isResizeObserverLoop(error)) {
      return;
    }
    console.error(error);
  }
}

/** Return whether an error is the complaint of the browser about the observer. */
export function isResizeObserverLoop(error: unknown): boolean {
  if (!error || typeof error !== 'object') {
    return false;
  }
  const message = 'message' in error ? String(error.message ?? '') : '';
  return message.includes('ResizeObserver loop');
}
