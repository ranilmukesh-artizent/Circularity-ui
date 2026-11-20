import { Component, Suspense, type ReactNode } from 'react';
import { retryFailed } from '../api/client';

/** "Loading…" while a page waits for its first answer from di-api (the facade suspends on a cache miss). */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="note" role="status" aria-live="polite" style={{ padding: '24px 4px' }}>
      {label}
    </div>
  );
}

interface State { error: Error | null }

/** Shows a failed read (a refusal or an unreachable server) in place of the page, with a retry. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.retry();
  }

  /** Refetch the reads that failed (else the cache would throw the same error again), then render the page. */
  retry = () => {
    retryFailed();
    this.setState({ error: null });
  };

  render() {
    const e = this.state.error;
    if (!e) return this.props.children;
    return (
      <div className="card" role="alert" style={{ padding: 16, margin: '16px 0' }}>
        <b>This page could not load.</b>
        <p className="note">{e.message}</p>
        <button className="btn" onClick={this.retry}>Try again</button>
      </div>
    );
  }
}

/** Suspense and error boundary together, reset when the route changes. */
export function Boundary({ children, resetKey }: { children: ReactNode; resetKey?: string }) {
  return (
    <ErrorBoundary resetKey={resetKey}>
      <Suspense fallback={<Loading />}>{children}</Suspense>
    </ErrorBoundary>
  );
}
