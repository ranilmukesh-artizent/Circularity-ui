import { Suspense, useState } from 'react';
import { fmtDateTime } from '../api/access';
import { money } from '../api/format';
import { usePilotReport } from '../api/orgs';
import { can } from '../api/session';
import { Modal } from './Overlay';

/** What pilot mode means, in one place (the Organisation section and the report show it). */
export const PILOT_TEXT =
  'In pilot mode, decisions run as usual, but no instruction is sent to an enterprise system. Each one is held and ' +
  'listed in the pilot report as what would have been sent. Pilot mode covers the unit and every unit below it.';

/** The pilot report of a unit's subtree (GET /api/screens/orgs/{unit}/pilot; manageOrgs or approve.flows). */
export function PilotReportDialog({ unit, name, onClose }: { unit: string; name: string; onClose: () => void }) {
  return (
    <Modal title={'Pilot report · ' + name} wide onClose={onClose}>
      <Suspense fallback={<p className="note">Loading the report…</p>}>
        <Report unit={unit} />
      </Suspense>
    </Modal>
  );
}

/** "Pilot report" for one org unit (Analytics), only for accounts that may read it (manageOrgs or approve.flows). */
export function PilotReportButton({ id, name, className = 'btn sm' }: { id: string; name: string; className?: string }) {
  const [open, setOpen] = useState(false);
  if (!can('manageOrgs') && !can('approve.flows')) return null;
  return (
    <>
      <button className={className} aria-label={'Pilot report for ' + name} onClick={() => setOpen(true)}>Pilot report</button>
      {open && <PilotReportDialog unit={id} name={name} onClose={() => setOpen(false)} />}
    </>
  );
}

function Report({ unit }: { unit: string }) {
  const r = usePilotReport(unit);
  const routes = Object.entries(r.by_route).sort((a, b) => b[1] - a[1]);
  const figures: [string, string][] = [
    ['Cases', String(r.cases_opened)],
    ['Decisions submitted', String(r.decisions_submitted)],
    ['Decisions approved', String(r.decisions_approved)],
    ['Recommended net value', money(r.recommended_net_total)],
    ['Cases with business rules applied', String(r.rules_applied_count)],
    ['Instructions held', String(r.instructions_held)],
  ];
  return (
    <div id="orgPilotReport">
      <p className="note" style={{ marginTop: 0 }}>
        {r.pilot ? (r.pilot_via === unit ? 'Pilot mode is on.' : 'Pilot mode is on through ' + r.pilot_via + '.') : 'Pilot mode is off. Instructions are sent as usual.'}{' '}
        The figures cover this unit and every unit below it.
      </p>
      <div className="tw">
        <table className="t static tight">
          <tbody>
            {figures.map(([k, v]) => <tr key={k}><td>{k}</td><td className="r num">{v}</td></tr>)}
            {routes.length > 0 && <tr><td>Recommended routes</td><td className="r">{routes.map(([k, n]) => k + ' ' + n).join(' · ')}</td></tr>}
          </tbody>
        </table>
      </div>
      <h4 style={{ margin: '14px 0 6px' }}>What would have been sent</h4>
      {r.held.length ? (
        <div className="tw">
          <table className="t static tight">
            <thead><tr><th>Case</th><th>Step</th><th>Instruction</th><th>To</th><th>Held</th></tr></thead>
            <tbody>
              {r.held.map((x) => (
                <tr key={x.id}>
                  <td className="mono">{x.case_id}</td>
                  <td className="num">{x.step + 1}</td>
                  <td>{x.kind}</td>
                  <td>{x.target}</td>
                  <td className="note">{x.sent_at ? fmtDateTime(x.sent_at) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="note">No instruction has been held yet.</p>
      )}
      <p className="note">{PILOT_TEXT}</p>
    </div>
  );
}
