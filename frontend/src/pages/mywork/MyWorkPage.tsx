import { useEffect, useState } from 'react';
import { isFraudItem } from '../../api/fraud';
import { assignItem, draftedBy, draftOwner, explainException, resolveItem, useMyWork, type ExceptionDraft, type WorkItem, type WorkKind } from '../../api/mywork';
import { accounts, can, canPage } from '../../api/session';
import { proposals as heldProposals } from '../../api/home';
import { postNonReturnFee } from '../../api/toolFleet';
import { useBackend } from '../../api/useBackend';
import { Modal } from '../../components/Overlay';
import { ProposalItems } from '../../components/ProposalRow';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { PackKpiTiles } from '../analytics/PackView';
import { AgeingCard } from './AgeingCard';
import { LotsCard } from './LotsCard';
import { conflictSummary, countsByKind, dueLabel, KIND_LABEL, KINDS, meaningful, nonReturnLine, PAGE, readable, sortForPerson, workId } from './mywork';

type Dialog = { kind: 'resolve' | 'assign'; item: WorkItem };

/** My work (plan 9, P9-1.7): everything that waits for the signed-in person, in one list. */
export function MyWorkPage() {
  useBackend();
  const s = useMyWork();
  const [kind, setKind] = useState<WorkKind | 'all' | 'fraud'>('all');
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const action = useAction();
  useEffect(() => {
    document.title = 'My work · Circularity Decision Workbench';
  }, []);
  const packs = [...new Set(s.kpis.map((k) => k.pack))];
  const counts = countsByKind(s.items);
  const shown = sortForPerson(s.items).filter((i) => kind === 'all' || (kind === 'fraud' ? isFraudItem(i) : i.kind === kind));
  // F20: in the full list the data conflicts are one summary row at the end, so what only this person can do shows first;
  // the Conflicts chip lists them one by one
  const conflicts = kind === 'all' ? shown.filter((i) => i.kind === 'conflict') : [];
  const rows = kind === 'all' ? shown.filter((i) => i.kind !== 'conflict') : shown;
  // the agents' proposals are the shared card (what accepting does, bulk accept), from Home's list of the same proposals
  const heldIds = new Set(rows.filter((i) => i.kind === 'proposal').map((i) => i.id));
  const held = heldProposals().filter((p) => heldIds.has('p:' + p.id));
  const lead = rows.filter((i) => i.kind === 'approval');
  const rest = rows.filter((i) => i.kind !== 'approval' && i.kind !== 'proposal');
  const postFee = async (line: string) => {
    const r = await action.run(() => postNonReturnFee(line));
    if (r.ok) toast('Fee posted.');
  };
  const renderRow = (i: WorkItem) => (
    <li key={i.id} data-kind={i.kind} data-id={i.id}>
      <span>
        <span className="chip line" style={{ marginRight: 6 }}>{KIND_LABEL[i.kind]}</span>
        <b>{readable(i.title)}</b>
        {i.case_id && <span className="note">Case <a href={'#/product/' + i.case_id}>{i.case_id}</a></span>}
        {meaningful(i.cause) && <span className="note">{readable(meaningful(i.cause))}</span>}
        {i.action && <span className="note">Next: {i.action}</span>}
        {i.kind === 'exception' && workId(i) !== null && <AssistantDraft id={workId(i) as number} />}
        <span className="note">
          For {i.owner}
          {i.due && <> · <span className={'chip ' + (i.overdue ? 'bad' : 'line')}>{dueLabel(i)}</span></>}
        </span>
        <span className="row">
          {workId(i) !== null && <button className="btn sm pri" disabled={action.pending} onClick={() => setDialog({ kind: 'resolve', item: i })}>Resolve</button>}
          {workId(i) !== null && <button className="btn sm" disabled={action.pending} onClick={() => setDialog({ kind: 'assign', item: i })}>Assign</button>}
          {nonReturnLine(i) !== null && <button className="btn sm pri" disabled={action.pending} onClick={() => postFee(nonReturnLine(i) as string)}>Post the fee</button>}
          {i.go && <a className="btn sm" href={'#/' + i.go}>Open</a>}
        </span>
      </span>
    </li>
  );
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
      {!rows.length && !conflicts.length && !held.length && <div className="callout info">Nothing waits for you here.</div>}
      {lead.length > 0 && <ul className="frbl" aria-label="My work">
        {lead.slice(0, limit).map(renderRow)}
      </ul>}
      {held.length > 0 && (
        <section aria-label="Proposals held for you" style={{ margin: '12px 0' }}>
          <p className="note" style={{ margin: '0 0 8px' }}>Agents prepared these. Nothing runs until you accept; accepting runs the action as you.</p>
          <ProposalItems list={held} idPrefix="mwp-" label="Proposals held for you" />
        </section>
      )}
      <ul className="frbl" aria-label="Other work">
        {rest.slice(0, Math.max(0, limit - lead.length)).map(renderRow)}
        {conflicts.length > 0 && (
          <li data-kind="conflict" data-group="conflicts">
            <span>
              <span className="chip line" style={{ marginRight: 6 }}>{KIND_LABEL.conflict}</span>
              <b>{conflictSummary(conflicts.length)}</b>
              <span className="note">Sources disagree on a field of an asset. A data owner settles them in the Conflict Queue.</span>
              <span className="row">
                <a className="btn sm" href="#/integration/conflicts">Review in Conflict Queue →</a>
                <button className="btn sm ghost" onClick={() => setKind('conflict')}>List them here</button>
              </span>
            </span>
          </li>
        )}
      </ul>
      {lead.length + rest.length > limit && (
        <div className="row" style={{ justifyContent: 'space-between', margin: '12px 0' }}>
          <span className="note">Showing {limit} of {lead.length + rest.length}</span>
          <button className="btn sm" onClick={() => setLimit(limit + PAGE)}>Show {Math.min(PAGE, lead.length + rest.length - limit)} more</button>
        </div>
      )}
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
    const r =
      d.kind === 'resolve' && wid !== null
        ? await action.run(() => resolveItem(wid, d.item.kind === 'needs_info' ? 'answered' : 'resolved', text.trim()), { inline: setErr })
        : d.kind === 'assign' && wid !== null
          ? await action.run(() => assignItem(wid, account), { inline: setErr })
          : null;
    if (!r?.ok) return;
    toast(d.kind === 'resolve' ? 'Resolved.' : 'Assigned.');
    onClose();
  };
  const title = { resolve: 'Resolve', assign: 'Assign' }[d.kind] + ': ' + d.item.title;
  const ready = d.kind === 'assign' ? !!account : d.item.kind === 'needs_info' ? !!text.trim() : true;
  return (
    <Modal
      title={title}
      onClose={onClose}
      foot={
        <>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn pri" disabled={action.pending || !ready} onClick={submit}>{d.kind === 'assign' ? 'Assign' : 'Resolve'}</button>
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
            <label htmlFor="mw-note">What was done? Add a note for the record.</label>
            <textarea id="mw-note" maxLength={300} value={text} onChange={(e) => { setText(e.target.value); setErr(''); }} />
          </>
        )}
        <div className="err" role="alert" hidden={!err}>{err}</div>
      </div>
    </Modal>
  );
}
