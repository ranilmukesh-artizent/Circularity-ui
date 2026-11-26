import { useEffect, useState } from 'react';
import { acceptProposal, rejectProposal } from '../../api/agents';
import { isFraudItem } from '../../api/fraud';
import { assignItem, draftedBy, draftOwner, explainException, resolveItem, useMyWork, type ExceptionDraft, type WorkItem, type WorkKind } from '../../api/mywork';
import { accounts, can, canPage } from '../../api/session';
import { postNonReturnFee } from '../../api/toolFleet';
import { useBackend } from '../../api/useBackend';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { PackKpiTiles } from '../analytics/PackView';
import { AgeingCard } from './AgeingCard';
import { LotsCard } from './LotsCard';
import { conflictGroupTitle, countsByKind, dueLabel, groupConflicts, KIND_LABEL, KINDS, nonReturnLine, proposalId, sortItems, workId } from './mywork';

type Dialog = { kind: 'resolve' | 'assign' | 'reject'; item: WorkItem };

/** My work (plan 9, P9-1.7): everything that waits for the signed-in person, in one list. */
export function MyWorkPage() {
  useBackend();
  const s = useMyWork();
  const [kind, setKind] = useState<WorkKind | 'all' | 'fraud'>('all');
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const action = useAction();
  useEffect(() => {
    document.title = 'My work · Circularity Decision Workbench';
  }, []);
  const packs = [...new Set(s.kpis.map((k) => k.pack))];
  const counts = countsByKind(s.items);
  const picked = sortItems(s.items).filter((i) => kind === 'all' || (kind === 'fraud' ? isFraudItem(i) : i.kind === kind));
  // in "All", the conflicts are one row below everything else; the Conflicts chip lists them one by one
  const grouped = kind === 'all' ? groupConflicts(picked) : { rows: picked, conflicts: [] as WorkItem[] };
  const rows = grouped.rows;
  const conflictGo = grouped.conflicts.every((c) => c.go === grouped.conflicts[0]?.go) ? grouped.conflicts[0]?.go : null;
  const accept = async (i: WorkItem) => {
    const id = proposalId(i);
    if (id === null) return;
    const r = await action.run(() => acceptProposal(id));
    if (r.ok) toast('Done: the action ran as you.');
  };
  const postFee = async (line: string) => {
    const r = await action.run(() => postNonReturnFee(line));
    if (r.ok) toast('Fee posted.');
  };
  return (
    <div className="frpage" id="mywork">
      <div className="phead">
        <div>
          <h1>My work</h1>
          <p>Exceptions, approvals, questions and proposals that wait for you, most urgent first.</p>
          {canPage('agent-activity') && <p><a href="#/agent-activity">See what the agents did on your cases</a></p>}
        </div>
      </div>
      {packs.map((k) => (
        <section key={k} aria-label={'KPIs: ' + s.kpis.find((x) => x.pack === k)?.pack_name} style={{ marginBottom: 12 }}>
          <p className="note" style={{ margin: '0 0 6px' }}>{s.kpis.find((x) => x.pack === k)?.pack_name}</p>
          <PackKpiTiles kpis={s.kpis.filter((x) => x.pack === k)} />
        </section>
      ))}
      {(can('manageLots') || can('approve.decisions')) && <LotsCard />}
      {can('manageFlows') && <AgeingCard />}
      <div className="row" role="group" aria-label="Filter by kind" style={{ marginBottom: 12, gap: 8, flexWrap: 'wrap' }}>
        <button className={'chip ' + (kind === 'all' ? 'ok' : 'line')} aria-pressed={kind === 'all'} onClick={() => setKind('all')}>
          All {s.items.length}
        </button>
        {KINDS.map((k) => (
          <button key={k} className={'chip ' + (kind === k ? 'ok' : 'line')} aria-pressed={kind === k} onClick={() => setKind(k)}>
            {KIND_LABEL[k]} {counts[k]}
          </button>
        ))}
        <button className={'chip ' + (kind === 'fraud' ? 'ok' : 'line')} aria-pressed={kind === 'fraud'} onClick={() => setKind('fraud')}>
          Fraud and compliance {s.items.filter(isFraudItem).length}
        </button>
      </div>
      {!rows.length && !grouped.conflicts.length && <div className="callout info">Nothing waits for you here.</div>}
      <ul className="frbl" aria-label="My work">
        {rows.map((i) => (
          <li key={i.id} data-kind={i.kind} data-id={i.id}>
            <span>
              <span className="chip line" style={{ marginRight: 6 }}>{KIND_LABEL[i.kind]}</span>
              <b>{i.title}</b>
              {i.case_id && <> · <a href={'#/product/' + i.case_id}>{i.case_id}</a></>}
              {i.cause && <span className="note">{i.cause}</span>}
              {i.action && <span className="note">Next: {i.action}</span>}
              {i.kind === 'exception' && workId(i) !== null && <AssistantDraft id={workId(i) as number} />}
              <span className="note">
                For {i.owner}
                {i.due && <> · <span className={'chip ' + (i.overdue ? 'bad' : 'line')}>{dueLabel(i)}</span></>}
              </span>
              <span className="row">
                {workId(i) !== null && <button className="btn sm pri" disabled={action.pending} onClick={() => setDialog({ kind: 'resolve', item: i })}>Resolve</button>}
                {workId(i) !== null && <button className="btn sm" disabled={action.pending} onClick={() => setDialog({ kind: 'assign', item: i })}>Assign</button>}
                {proposalId(i) !== null && <button className="btn sm pri" disabled={action.pending} onClick={() => accept(i)}>Accept</button>}
                {proposalId(i) !== null && <button className="btn sm" disabled={action.pending} onClick={() => setDialog({ kind: 'reject', item: i })}>Reject</button>}
                {nonReturnLine(i) !== null && <button className="btn sm pri" disabled={action.pending} onClick={() => postFee(nonReturnLine(i) as string)}>Post the fee</button>}
                {i.go && <a className="btn sm" href={'#/' + i.go}>Open</a>}
              </span>
            </span>
          </li>
        ))}
        {grouped.conflicts.length > 0 && (
          <li data-kind="conflict" data-id="conflicts">
            <span>
              <span className="chip line" style={{ marginRight: 6 }}>{KIND_LABEL.conflict}</span>
              <b>{conflictGroupTitle(grouped.conflicts.length)}</b>
              <span className="note">They hold decisions until a source is chosen.</span>
              <span className="row">
                <a className="btn sm pri" href={'#/' + (conflictGo ?? 'integration/conflicts')}>Open the conflict queue</a>
                <button className="btn sm" onClick={() => setKind('conflict')}>List them here</button>
              </span>
            </span>
          </li>
        )}
      </ul>
      {dialog && <ItemDialog d={dialog} onClose={() => setDialog(null)} />}
    </div>
  );
}

/** P9-2.10: "Assistant: cause · recommended action · owner" under an exception, from exception.explain. The assistant only
 *  proposes; the person resolves or assigns with the buttons of the row. Nothing shows when the draft cannot be read. */
function AssistantDraft({ id }: { id: number }) {
  const [draft, setDraft] = useState<ExceptionDraft | null>(null);
  useEffect(() => {
    let live = true;
    void explainException(id).then((r) => {
      if (live && r.ok) setDraft(r.output);
    });
    return () => {
      live = false;
    };
  }, [id]);
  if (!draft) return null;
  return (
    <span className="note" data-testid="assistant-draft">
      Assistant: {draft.cause} · {draft.recommended_action} · {draftOwner(draft)}
      <br />
      {draftedBy(draft)}
      {draft.sources.length > 0 && <> · from {[...new Set(draft.sources.map((s) => s.source))].join(', ')}</>}
    </span>
  );
}

function ItemDialog({ d, onClose }: { d: Dialog; onClose: () => void }) {
  const action = useAction();
  const [text, setText] = useState('');
  const [account, setAccount] = useState('');
  const [err, setErr] = useState('');
  const people = accounts();
  const submit = async () => {
    const wid = workId(d.item);
    const pid = proposalId(d.item);
    const r =
      d.kind === 'resolve' && wid !== null
        ? await action.run(() => resolveItem(wid, d.item.kind === 'needs_info' ? 'answered' : 'resolved', text.trim()), { inline: setErr })
        : d.kind === 'assign' && wid !== null
          ? await action.run(() => assignItem(wid, account), { inline: setErr })
          : pid !== null
            ? await action.run(() => rejectProposal(pid, text.trim()), { inline: setErr })
            : null;
    if (!r?.ok) return;
    toast(d.kind === 'resolve' ? 'Resolved.' : d.kind === 'assign' ? 'Assigned.' : 'Proposal rejected.');
    onClose();
  };
  const title = { resolve: 'Resolve', assign: 'Assign', reject: 'Reject' }[d.kind] + ': ' + d.item.title;
  const ready = d.kind === 'assign' ? !!account : d.kind === 'reject' || (d.kind === 'resolve' && d.item.kind === 'needs_info') ? !!text.trim() : true;
  return (
    <Modal
      title={title}
      onClose={onClose}
      foot={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn pri" disabled={action.pending || !ready} onClick={submit}>{d.kind === 'assign' ? 'Assign' : d.kind === 'reject' ? 'Reject' : 'Resolve'}</button>
        </>
      }
    >
      <div className="fld">
        {d.kind === 'assign' ? (
          <>
            <label htmlFor="mw-account">Who takes it?</label>
            <select id="mw-account" value={account} onChange={(e) => { setAccount(e.target.value); setErr(''); }}>
              <option value="">Choose a person</option>
              {people.map((a) => <option key={a.id} value={a.id}>{a.label} · {a.role}</option>)}
            </select>
          </>
        ) : (
          <>
            <label htmlFor="mw-note">{d.kind === 'reject' ? "Why not? The agent's owner sees this." : 'What was done? Add a note for the record.'}</label>
            <textarea id="mw-note" maxLength={300} value={text} onChange={(e) => { setText(e.target.value); setErr(''); }} />
          </>
        )}
        <div className="err" role="alert" hidden={!err}>{err}</div>
      </div>
    </Modal>
  );
}
