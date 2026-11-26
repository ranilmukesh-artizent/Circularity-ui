import { useCallback, useEffect, useState } from 'react';
import { importHistory, replayBatches, type BatchView } from '../../api/replay';
import { can, currentAccount } from '../../api/session';
import type { ModelerScreen } from '../../api/types';
import { Panel } from '../../components/kit/Panel';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

/** The packs history can be replayed for (the pack of the template on screen). */
export const REPLAY_PACKS = ['tool_fleet', 'device'];

/** "2025-10-01 to 2026-09-28", or a dash when no row was good. */
export const periodLine = (b: Pick<BatchView, 'period'>): string => (b.period ? `${b.period[0]} to ${b.period[1]}` : '—');

/** Show the panel to the roles that run or read replays, for the packs that have one. */
export const showReplay = (s: ModelerScreen): boolean => REPLAY_PACKS.includes(s.template.key) && can('runReplay');

/**
 * Replay (plan 9, P9-7.1, story X-06): import a CSV of past decisions for this pack and org unit. The file is read in the
 * browser and sent as text; the server checks every row, keeps the good ones and holds the rest with a reason. Shows the rows
 * kept, the decision period and the held rows (the first 50). The Executive role reads only: no import button.
 */
export function ReplayPanel({ s }: { s: ModelerScreen }) {
  const pack = s.template.key;
  const action = useAction();
  const [batches, setBatches] = useState<BatchView[]>([]);
  const [err, setErr] = useState('');
  const canImport = currentAccount()?.role !== 'Executive';

  const load = useCallback(async () => {
    const r = await replayBatches(pack, s.org);
    if (r.ok) setBatches(r.output.batches);
  }, [pack, s.org]);
  useEffect(() => {
    void load();
  }, [load]);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setErr('');
    const csv = await file.text();
    const r = await action.run(() => importHistory(pack, s.org, csv), { inline: setErr, ms: 4200 });
    if (!r.ok) return;
    toast(`${r.output.rows} rows read, ${r.output.held} held.`);
    await load();
  };

  return (
    <Panel title="Replay" sub="Past decisions to test the rules on" cls="mdl-replay">
      {canImport && (
        <div className="mdl-row" data-replay-import>
          <label className="btn sm pri" htmlFor="mdl-rp-file">Import history (CSV)</label>
          <input id="mdl-rp-file" type="file" accept=".csv,text/csv" className="sr" disabled={action.pending}
                 onChange={(e) => { void pick(e.target.files?.[0]); e.target.value = ''; }} />
          <span className="note">De-identified extracts only: item ids are serials or salted hashes.</span>
        </div>
      )}
      {err && <p className="mdl-msg blk" role="alert" data-replay-refusal>{err}</p>}
      {batches.length === 0 && <p className="note" data-replay-empty>No history imported for {s.org} yet.</p>}
      <ul className="mdl-hist">
        {batches.map((b) => (
          <li key={b.id} data-replay-batch={b.id}>
            <b>Batch {b.id}</b>{' '}
            <span className="note">· {b.rows} rows · {b.held} held · {periodLine(b)}</span>
            {b.held > 0 && (
              <ul className="mdl-hist" data-replay-held>
                {Object.entries(b.held_reasons).map(([why, n]) => <li key={why}>{n} × {why}</li>)}
                {b.held_items.map((h) => <li key={h.n} className="note">row {h.n} · {h.item_id} · {h.held_reason}</li>)}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}
