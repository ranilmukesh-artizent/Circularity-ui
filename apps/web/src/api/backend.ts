/**
 * Which backend the facade (src/api/*.ts) talks to (docs/BACKEND_STEPS.md, B17):
 *   VITE_BACKEND=engine  the demo's logic running in the browser (src/engine/), as before
 *   VITE_BACKEND=api     di-api over HTTP: screens, actions, the live stream, Ask
 * Pages never check this; only the facade does.
 */
export const BACKEND: 'engine' | 'api' = import.meta.env.VITE_BACKEND === 'api' ? 'api' : 'engine';
export const API = BACKEND === 'api';
