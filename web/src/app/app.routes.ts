import { Routes } from '@angular/router';

import { requireConversion, requireFile } from './core/guards';
import { ProgressComponent } from './features/progress/progress';
import { ResultComponent } from './features/result/result';
import { UploadComponent } from './features/upload/upload';

export const routes: Routes = [
  {
    path: '',
    component: UploadComponent,
    title: 'scan2epub — Convert a scanned book',
  },
  {
    path: 'progress',
    component: ProgressComponent,
    title: 'scan2epub — Converting',
    canActivate: [requireFile],
  },
  {
    path: 'result',
    component: ResultComponent,
    title: 'scan2epub — The book is ready',
    canActivate: [requireConversion],
  },
  {
    path: 'reader',
    loadComponent: () =>
      import('./features/reader/reader').then((module) => module.ReaderComponent),
    title: 'scan2epub — Reader',
    canActivate: [requireConversion],
  },
  { path: '**', redirectTo: '' },
];
