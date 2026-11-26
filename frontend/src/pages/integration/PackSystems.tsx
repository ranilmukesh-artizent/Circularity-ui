/* The mock systems of each pack, grouped by pack (UI audit gaps 10 and 11): "Used vehicles: dealer system, auction, title
   registry ...". Register one with source.reconnect (the existing action: it registers the system shared and connects it, a
   sync queued). Every one is a synthetic system simulated for this environment; none is a real vendor connection.
   Shown in the New integration dialog and in the Source Map. */
import { useState } from 'react';
import { packSystems, reconnectSource } from '../../api/integration';
import { toast } from '../../components/toast';
import { refused } from '../../hooks/useAction';
import { canMgr } from './FabricContext';
import { groupByPack } from './packGroups';

export function PackSystems({ onDone, openOnly }: { onDone?: () => void; openOnly?: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const groups = groupByPack(packSystems()).filter((g) => !openOnly || g.open > 0);
  if (!groups.length) return null;
  const mgr = canMgr();

  async function register(id: string, name: string) {
    if (busy) return;
    setBusy(id);
    const r = await reconnectSource(id);
    setBusy(null);
    if (refused(r)) return;
    toast(name + ' is registered and connecting. It is a synthetic system simulated for this environment.');
    onDone?.();
  }

  return (
    <section aria-label="Systems for each pack" className="packsys">
      <h3 style={{ margin: '14px 0 4px' }}>Systems for each pack</h3>
      <p className="note" style={{ marginTop: 0 }}>Simulated systems the packs read. Register one to connect it; nothing here is a real vendor connection.</p>
      {groups.map((g) => (
        <div key={g.pack} style={{ marginBottom: 10 }}>
          <b>{g.name}</b> <span className="note">{g.systems.length} systems, {g.open} not registered</span>
          <ul style={{ listStyle: 'none', margin: '4px 0 0', padding: 0, display: 'grid', gap: 4 }}>
            {g.systems.map((s) => (
              <li key={s.id} className="row" style={{ alignItems: 'center', gap: 8 }}>
                <span style={{ flex: 1 }}>{s.name} <span className="note">{s.type}</span></span>
                {s.registered
                  ? <span className="chip line">Registered</span>
                  : <button className="btn sm" disabled={!mgr || busy !== null} onClick={() => void register(s.id, s.name)} aria-label={'Register ' + s.name}>{busy === s.id ? 'Registering…' : 'Register'}</button>}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
