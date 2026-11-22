import { useQuery } from '@tanstack/react-query';
import { getJson, type Health } from '../api/health';

const LABELS: Record<string, string> = { database: 'Database (di)', source_sim: 'Source systems (source-sim)' };

/** Phase 0 placeholder: shows that web → di-api → Postgres and source-sim are wired up. Replaced by Sign-in in phase 6. */
export function StatusPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ['health'],
    queryFn: () => getJson<Health>('/api/health'),
    refetchInterval: 5000,
  });

  return (
    <main style={{ maxWidth: 640, margin: '0 auto', padding: '48px 16px' }}>
      <h1 style={{ font: '800 28px/1.2 var(--f-display)', margin: '0 0 4px' }}>Circularity</h1>
      <p style={{ color: 'var(--muted)', margin: '0 0 24px' }}>Full-stack POC · stack status</p>

      <section
        style={{ background: 'var(--panel)', border: '1px solid var(--line)', borderRadius: 12, boxShadow: 'var(--shadow)' }}
      >
        <Row label="API (di-api)" ok={!error && !isLoading} detail={isLoading ? 'checking…' : error ? String(error) : 'reachable'} />
        {data &&
          Object.entries(data.checks).map(([key, c]) => (
            <Row
              key={key}
              label={LABELS[key] ?? key}
              ok={c.ok}
              detail={c.ok ? describe(c) : (c.error ?? 'unavailable')}
            />
          ))}
      </section>
    </main>
  );
}

function describe(c: Record<string, unknown>): string {
  if (typeof c.migration === 'string') return `migration ${c.migration}`;
  if (typeof c.systems === 'number') return `${c.systems} systems`;
  return 'ok';
}

function Row({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', padding: '12px 16px', borderTop: '1px solid var(--line2)' }}>
      <span
        aria-hidden
        style={{ width: 8, height: 8, borderRadius: 4, flex: 'none', background: ok ? 'var(--ok)' : 'var(--bad)' }}
      />
      <strong style={{ fontWeight: 600, flex: 1 }}>{label}</strong>
      <span style={{ color: ok ? 'var(--ink2)' : 'var(--bad)', fontFamily: 'var(--f-mono)', fontSize: 12, textAlign: 'right' }}>
        {ok ? 'OK' : 'Down'} · {detail}
      </span>
    </div>
  );
}
