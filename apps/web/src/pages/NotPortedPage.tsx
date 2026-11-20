import type { PageProps } from './registry';

/** Placeholder for a route that has no page in the React app. */
export function NotPortedPage({ route }: PageProps) {
  const path = [route.page, route.a, route.b].filter(Boolean).join('/');
  return (
    <div className="phead frph">
      <div>
        <h1>Page not found</h1>
        <p>
          <b>#/{path}</b> is not a page in this app. Use the menu to find what you need.
        </p>
      </div>
    </div>
  );
}
