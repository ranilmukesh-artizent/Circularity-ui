/**
 * The medical-rental sections of a case (plan 9 UI audit gap 7): decontamination, certification against the rental length,
 * turnaround and service planning, the repair approval, the follow-through and the write-off. Shared by the Overview panel and
 * the stage tabs; read only (every fact comes with the case screen). Decontamination, certification and write-off wording needs
 * review by Kinective's Legal team before it is relied on.
 */
import type { CaseRec } from '../../../api/case';
import { Kv } from '../CaseBlocks';
import { gateLine } from '../gates';
import { certRows, deconLine, followRows, medicalView, repairHold, serviceDates, serviceLines, turnaroundLines, writeOffLine } from './medView';

/** G-MED-DECON: the decontamination record against check-in, with the held reason when it is missing. */
export function Decontamination({ c }: { c: CaseRec }) {
  if (!medicalView(c)) return null;
  const g = c.gates?.find((x) => x.id === 'G-MED-DECON');
  return (
    <>
      <Kv rows={[['Decontamination', deconLine(g)]]} />
      {g && !g.passed && <p className="note stpad tx-bad">{gateLine(g)}</p>}
    </>
  );
}

/** Certification and preventive maintenance against the end of each rental request. */
export function CertificationWindow({ c }: { c: CaseRec }) {
  if (!medicalView(c)) return null;
  const rows = certRows(c);
  const dates = serviceDates(c);
  return (
    <>
      {dates.length > 0 && <Kv rows={dates} />}
      {rows.length === 0 ? <p className="note stpad">No rental request is on file for this device.</p> : (
        <ul className="stsys stpad" aria-label="Rental requests">
          {rows.map((r) => (
            <li key={r.id} className={r.ok ? '' : 'tx-bad'}>
              <b>{r.id}</b> · {r.rental}: {r.text}{r.advice ? ` · ${r.advice}` : ''}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Turnaround at close and the service orders: the one proposed and those booked. */
export function TurnaroundService({ c }: { c: CaseRec }) {
  if (!medicalView(c)) return null;
  const lines = [...turnaroundLines(c), ...serviceLines(c)];
  if (!lines.length) return <p className="note stpad">No turnaround is measured and no service is planned yet.</p>;
  return (
    <ul className="stsys stpad" aria-label="Turnaround and service">
      {lines.map((l) => <li key={l}>{l}</li>)}
    </ul>
  );
}

/** The repair over its limit, held for the fleet manager. Nothing when there is none. */
export function RepairApproval({ c }: { c: CaseRec }) {
  const h = medicalView(c) ? repairHold(c) : null;
  if (!h) return null;
  return (
    <div className="stpad" role="note">
      <p className="tx-bad" style={{ margin: 0 }}>{h.reason}</p>
      <ul className="stsys">{h.lines.map((l) => <li key={l}>{l}</li>)}</ul>
    </div>
  );
}

/** The steps sent after approval, and the write-off of a retired device held for a person. */
export function FollowThrough({ c }: { c: CaseRec }) {
  if (!medicalView(c)) return null;
  const rows = followRows(c);
  const off = writeOffLine(c);
  const data = c.gates?.find((x) => x.id === 'G-DATA-3');
  return (
    <>
      {rows.length === 0 ? <p className="note stpad">No decision is approved yet, so no steps are planned.</p> : (
        <ol className="stsys stpad" aria-label="Follow-through">
          {rows.map((r) => <li key={r.key}>{r.label} · {r.state}</li>)}
        </ol>
      )}
      {data && <p className={'note stpad' + (data.passed ? '' : ' tx-bad')}>{data.name}: {gateLine(data)}</p>}
      {off && <p className="stpad" style={{ margin: '8px 0 0' }}>{off}</p>}
    </>
  );
}
