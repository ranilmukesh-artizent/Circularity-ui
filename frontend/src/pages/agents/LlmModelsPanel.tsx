import { useState } from 'react';
import { setLlmModel, type AgentsScreen, type LlmModel } from '../../api/agents';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';

const cooling = (iso: string) => 'Cooling down until ' + iso.slice(11, 16) + ' UTC';

/**
 * Language models (plan 9, P9-2.3): the models Circularity may call, in the order they are tried, with their roles,
 * limits and use this minute and today. Admin switches one on or off and changes its priority (llm.setModel); a model
 * that was told to wait (a 429) or used up its budget shows "Cooling down until …". Admin only: agents never see it.
 */
export function LlmModelsPanel({ s }: { s: AgentsScreen }) {
  const action = useAction();
  const [priority, setPriority] = useState<Record<string, string>>({});
  if (!s.can.manage) return null;
  const change = async (m: LlmModel, patch: Parameters<typeof setLlmModel>[1], done: string) => {
    const r = await action.run(() => setLlmModel(m.id, patch));
    if (r.ok) toast(m.model + done);
  };
  return (
    <section className="sect" id="agLlm">
      <div className="sh">
        <h2>Language models</h2>
        <span className="note">{s.llm.filter((m) => m.enabled).length} of {s.llm.length} on · tried in priority order</span>
      </div>
      <div className="panel">
        {s.llm.length ? (
          <div className="tw">
            <table className="t static">
              <thead>
                <tr>
                  <th>Model</th><th>Roles</th><th className="r">Limits per min · day</th><th className="r">Used this minute</th>
                  <th className="r">Used today</th><th>Status</th><th>Priority</th><th></th>
                </tr>
              </thead>
              <tbody>
                {s.llm.map((m) => (
                  <tr key={m.id} data-llm={m.id}>
                    <td><b className="mono">{m.model}</b> <span className="note mono">{m.provider}</span></td>
                    <td>{m.roles.map((r) => <span key={r} className="chip line" style={{ marginRight: 4 }}>{r}</span>)}</td>
                    <td className="r num">{m.rpm} req · {m.tpm} tok · {m.rpd} req</td>
                    <td className="r num">{m.used_minute.requests} req · {m.used_minute.tokens} tok</td>
                    <td className="r num">{m.used_day.requests} req</td>
                    <td>
                      <span className={'chip ' + (m.enabled ? 'ok' : 'line')}>{m.enabled ? 'On' : 'Off'}</span>
                      {m.cooling_until && <div className="note">{cooling(m.cooling_until)}</div>}
                    </td>
                    <td>
                      <label className="sr" htmlFor={'llm-pr-' + m.id}>Priority of {m.model}</label>
                      <input
                        id={'llm-pr-' + m.id} type="number" min={0} style={{ width: 64 }} value={priority[m.id] ?? String(m.priority)}
                        onChange={(e) => setPriority({ ...priority, [m.id]: e.target.value })}
                      />{' '}
                      <button
                        className="btn sm" disabled={action.pending || priority[m.id] === undefined || priority[m.id] === String(m.priority)}
                        onClick={() => change(m, { priority: Number(priority[m.id]) }, ' priority changed.')}
                      >
                        Set
                      </button>
                    </td>
                    <td className="nowrap">
                      <button className="btn sm" disabled={action.pending} onClick={() => change(m, { enabled: !m.enabled }, m.enabled ? ' is off.' : ' is on.')}>
                        {m.enabled ? 'Turn off' : 'Turn on'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="pb"><div className="empty"><b>No language models</b>Without one, every answer comes from the rules.</div></div>
        )}
      </div>
    </section>
  );
}
