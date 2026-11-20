import { useState } from 'react';
import { acknowledgeAlert, alertAssignee, alertKinds, alerts, assignAlert, status, type Alert } from '../../api/home';
import { useBackend } from '../../api/useBackend';
import { Icon } from '../../ui/Icon';
import { Modal } from '../../ui/Overlay';
import { toast } from '../../ui/toast';
import { askSoon } from '../../ui/askBus';
import { Panel } from '../../ui/kit/Panel';
import { Segmented } from '../../ui/kit/Segmented';
import { StatusPill } from '../../ui/kit/StatusPill';
import { Timeline } from '../../ui/kit/Timeline';
import { AttentionCard } from './AttentionCard';
import { HomeHeader } from './HomeHeader';

const ROLES = ['Developer', 'Approver', 'Planner', 'Engineer', 'Finance', 'Warehouse Manager', 'Admin'];

/** Alerts (frAlertsPage): acknowledge, assign, open or explain each one. */
export function AlertsPage() {
  useBackend();
  const [f, setF] = useState('all');
  const [assign, setAssign] = useState<Alert | null>(null);
  const [to, setTo] = useState(ROLES[0]);
  const l = alerts(), open = l.filter((a) => !a.ack), vis = l.filter((a) => f === 'all' || a.kind === f);
  const kinds = alertKinds().filter((k) => k[0] === 'all' || l.some((a) => a.kind === k[0]));
  const high = open.filter((a) => a.sev >= 2).length;

  const ack = async (a: Alert) => {
    if (await acknowledgeAlert(a.id)) toast('Acknowledged. The sender sees it is in hand.');
  };
  const doAssign = () => {
    if (!assign) return;
    assignAlert(assign.id, to);
    setAssign(null);
    toast('Assigned to ' + to + '.');
  };

  return (
    <div className="frpage" id="frAlerts">
      <HomeHeader
        title="Alerts"
        sub="Escalations from the handoff clock, failing workflows, stale or unavailable sources, expiring credentials, open conflicts and notifications. Acknowledge, assign or open each one."
        right={<span className={'chip ' + (open.length ? 'bad' : 'ok')} id="frAlertsN">{open.length} open</span>}
      />
      {open.length > 0 && <AttentionCard head={open.length + ' alert' + (open.length > 1 ? 's' : '') + ' open'} line={high + ' high severity. Clear the oldest escalations first.'} />}
      <div className="frbar">
        <Segmented
          name="alerts" label="Alert type" cur={f} onPick={setF}
          items={kinds.map((k) => [k[0], k[1] + ' (' + (k[0] === 'all' ? l.length : l.filter((a) => a.kind === k[0]).length) + ')'])}
        />
      </div>
      <Panel title="Open and recent">
        {vis.length ? (
          <Timeline
            cls="fral"
            rows={vis.map((a) => {
              const who = alertAssignee(a.id);
              return {
                key: a.id, cls: a.ack ? 'ack' : '', ic: a.ic, h: a.h, t: a.t,
                s: a.s + (who ? ' · assigned to ' + who : ''),
                x: (
                  <>
                    <a className="lnk" href={'#/' + a.go}>Open</a>
                    {!a.ack && (
                      <>
                        <button className="lnk" onClick={() => ack(a)}>Acknowledge</button>
                        <button className="lnk" onClick={() => { setTo(ROLES[0]); setAssign(a); }}>Assign</button>
                      </>
                    )}
                    <button className="lnk" onClick={askSoon}><Icon name="spark" /> Explain</button>
                  </>
                ),
                st: <StatusPill {...(a.ack ? status('ack') : a.sev >= 2 ? status('failed', 'High') : status('open', 'Medium'))} />,
              };
            })}
          />
        ) : (
          <div className="empty">
            <b>No alerts of this type</b>Choose All to see every alert.
          </div>
        )}
      </Panel>
      {assign && (
        <Modal
          title="Assign alert"
          onClose={() => setAssign(null)}
          foot={
            <>
              <button className="btn" onClick={() => setAssign(null)}>Cancel</button>
              <button className="btn pri" onClick={doAssign}>Assign</button>
            </>
          }
        >
          <p style={{ marginTop: 0 }}>
            <b>{assign.t}</b>
          </p>
          <label htmlFor="frAsg">Assign to the owning role</label>
          <select className="sel" id="frAsg" value={to} onChange={(e) => setTo(e.target.value)}>
            {ROLES.map((r) => <option key={r}>{r}</option>)}
          </select>
          <p className="note">The role sees it in Alerts with your name as the sender. Recorded in the audit log.</p>
        </Modal>
      )}
    </div>
  );
}
