import type { PageProps } from './registry';

const DEMO = 'https://ranilmukesh-artizent.github.io/Circularity-ui/';

/** Placeholder for a screen that has not moved to React yet. */
export function NotPortedPage({ route }: PageProps) {
  const path = [route.page, route.a, route.b].filter(Boolean).join('/');
  return (
    <div className="phead frph">
      <div>
        <h1>Coming to the new app</h1>
        <p>
          <b>#/{path}</b> has not moved to the React app yet.{' '}
          <a href={DEMO + '#/' + path} target="_blank" rel="noreferrer">
            Open it in the static demo
          </a>
          .
        </p>
      </div>
    </div>
  );
}
