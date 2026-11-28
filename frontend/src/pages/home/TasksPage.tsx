import { useEffect, useState } from 'react';
import { handedRows } from '../../api/command';
import { isFraudItem } from '../../api/fraud';
import { proposals as heldProposals, taskItems } from '../../api/home';
import { assignItem, draftedBy, draftOwner, explainException, resolveItem, useMyWork, type ExceptionDraft, type WorkItem, type WorkKind } from '../../api/mywork';
import { accounts, can, canPage } from '../../api/session';
import { postNonReturnFee } from '../../api/toolFleet';
import { useBackend } from '../../api/useBackend';
import { TallyStrip, type TallyGroup } from '../../components/kit/TallyStrip';
import { Modal } from '../../components/Overlay';
import { ProposalItems } from '../../components/ProposalRow';
import { toast } from '../../components/toast';
import { useAction } from '../../hooks/useAction';
import { ask, launch } from '../../utils/launchers';
import { PackKpiTiles } from '../analytics/PackView';
import { AgeingCard } from '../mywork/AgeingCard';
import { LotsCard } from '../mywork/LotsCard';
import { conflictSummary, dueLabel, KIND_LABEL, meaningful, nonReturnLine, PAGE, readable, sortForPerson, workId } from '../mywork/mywork';
import type { PageProps } from '../registry';
import { TaskButton, taskCase } from './TaskRow';
import { ageText, KIND_ONE, MINE, parseShow, summary, tasksPath, type Show } from './tasksView';
import './tasks.css';

type Dialog = { kind: 'resolve' | 'assign'; item: WorkItem };

/**
 * My Tasks (28 Nov 2026, decision log): the one page of what waits on the signed-in person. It is the former My work
 * (plan 9, P9-1.7: approvals, agents' proposals held for a person, questions, exceptions, steps, data conflicts) and the
 * demo's My Tasks ("Needs you") in one list, since the second was always part of the first. Three groups: what only this
 * person can do, what they handed on and now wait for, and the data conflicts a data owner settles. The tally strip is
 * the filter, kept in the URL (#/tasks?show=approval). #/mywork opens this page too.
 */
export function TasksPage({ query }: PageProps) {
  useBackend();
  const s = useMyWork();
  const demo = taskItems();
  const handed = canPage('command', 'handed') ? handedRows() : [];
  const show: Show = parseShow(query.get('show'));
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const action = useAction();
  useEffect(() => {
    document.title = 'My Tasks · Circularity Decision Workbench';
  }, []);

  const sorted = sortForPerson(s.items);
  const mine = sorted.filter((i) => i.kind !== 'conflict');
  const conflicts = sorted.filter((i) => i.kind === 'conflict');
  const fraud = sorted.filter(isFraudItem);
  const late = mine.filter((i) => i.overdue).length;

  const groups: TallyGroup[] = [
    ...MINE.map((k) => ({ id: k, label: KIND_LABEL[k], n: mine.filter((i) => i.kind === k).length, late: mine.filter((i) => i.kind === k && i.overdue).length })),
    ...(canPage('command', 'handed') ? [{ id: 'handed', label: 'Waiting on others', n: handed.length, late: handed.filter((h) => h.over).length, gap: true }] : []),
    { id: 'conflict', label: 'Data conflicts', n: conflicts.length, late: 0, gap: true },
  ];

  const rows = show === null ? mine : show === 'fraud' ? fraud : show === 'conflict' ? conflicts : show === 'handed' ? [] : mine.filter((i) => i.kind === show);
  // the agents' proposals are the shared card (what accepting does, bulk accept), from Home's list of the same proposals
  const heldIds = new Set(rows.filter((i) => i.kind === 'proposal').map((i) => i.id));
  const held = heldProposals().filter((p) => heldIds.has('p:' + p.id));
  const lead = rows.filter((i) => i.kind === 'approval');
  const rest = rows.filter((i) => i.kind !== 'approval' && i.kind !== 'proposal');
  const listed = [...lead, ...rest];
  const first = listed[0]?.id; // the one yellow button of the page
  const explained = new Set(listed.filter((i) => i.kind === 'exception' && workId(i) !== null).slice(0, 3).map((i) => i.id));

  const postFee = async (line: string) => {
    const r = await action.run(() => postNonReturnFee(line));
    if (r.ok) toast('Fee posted.');
  };

  const renderRow = (i: WorkItem) => {
    const pri = i.id === first ? ' pri' : '';
    const wid = workId(i), fee = nonReturnLine(i);
    const task = i.id.startsWith('a:') ? demo.find((t) => t.t === i.title) : undefined;
    const cid = i.case_id ?? taskCase(i.title);
    return (
      <li key={i.id} className="mt-row" data-kind={i.kind} data-id={i.id}>
        <div className="mt-main">
          <span className="mt-kind">
            {KIND_ONE[i.kind]}
            {i.overdue && <span className="mt-late"> · {dueLabel(i)}</span>}
            {!i.overdue && i.due && <> · {dueLabel(i)}</>}
          </span>
          <b>{readable(i.title)}</b>
          {meaningful(i.cause) && <span className="note">{readable(meaningful(i.cause))}</span>}
          {i.action && !task && <span className="note">Next: {i.action}</span>}
          {i.kind === 'exception' && wid !== null && <AssistantDraft id={wid} auto={explained.has(i.id)} />}
          <span className="note">
            For {i.owner}
            {i.case_id && <> · case <a href={'#/product/' + i.case_id}>{i.case_id}</a></>}
          </span>
        </div>
        <div className="mt-acts">
          {cid && <button className="btn sm ghost" aria-label={'Ask about ' + cid} onClick={() => ask(launch.howToDoTask(i.title, cid))}>Ask</button>}
          {wid !== null && <button className="btn sm" disabled={action.pending} onClick={() => setDialog({ kind: 'assign', item: i })}>Assign</button>}
          {wid !== null && <button className={'btn sm' + pri} disabled={action.pending} onClick={() => setDialog({ kind: 'resolve', item: i })}>Resolve</button>}
          {fee !== null && <button className={'btn sm' + (wid === null ? pri : '')} disabled={action.pending} onClick={() => postFee(fee)}>Post the fee</button>}
          {task ? <TaskButton i={task} primary={!!pri} /> : i.go && <a className={'btn sm' + (wid === null && fee === null ? pri : '')} href={'#/' + i.go}>Open</a>}
        </div>
      </li>
    );
  };

  const showMine = show !== 'handed'; // the conflicts, when asked for, are listed in the same section
  const nothing = !mine.length && !handed.length && !conflicts.length;
  return (
    <div className="frpage mt" id="frTasks">
      <div className="phead frph">
        <div>
          <h1>My Tasks</h1>
          <p className="mt-sum" id="frTasksN" data-n={mine.length}>{summary(mine.length, late, handed.length)}</p>
        </div>
        {canPage('agent-activity') && <div className="row"><a className="lnk" href="#/agent-activity">What the agents did on your cases</a></div>}
      </div>

      <section className="panel mt-strip" aria-label="What waits, by kind">
        <TallyStrip groups={groups} cur={show === 'fraud' ? null : show} hrefFor={(id) => '#' + tasksPath(id as Show)} label="Filter by kind" />
        <p className="note mt-key">
          One mark is one item; a taller red mark is late. Select a group to see only it.
          {show !== null && <> <a className="lnk" href={'#' + tasksPath(null)}>Show everything</a></>}
          {fraud.length > 0 && show !== 'fraud' && <> <a className="lnk" href={'#' + tasksPath('fraud')}>Fraud and compliance {fraud.length}</a></>}
        </p>
      </section>

      <div id="mywork" className="mt-secs">
        {nothing && (
          <div className="empty">
            <b>Nothing waits on you</b>New items appear here when a step becomes yours.
            {canPage('product') && <> Meanwhile, <a className="lnk" href="#/product/received">see the returned assets</a>.</>}
          </div>
        )}

        {showMine && !nothing && (
          <section className="panel mt-sec" aria-labelledby="mt-mine">
            <header>
              <h2 id="mt-mine">{show === 'fraud' ? 'Fraud and compliance' : show === 'conflict' ? 'Data conflicts' : show ? KIND_LABEL[show as WorkKind] : 'Only you can do'} <span className="num">{listed.length + held.length}</span></h2>
              {show === null && <p className="note">Approvals first, then what agents prepared and hold for you, then questions, tasks and exceptions.</p>}
              {show === 'conflict' && <p className="note">Sources disagree on a field of an asset. A data owner settles them in the <a className="lnk" href="#/integration/conflicts">Conflict Queue</a>.</p>}
            </header>
            {!listed.length && !held.length && <p className="mt-none">{show ? 'Nothing of this kind waits on you.' : 'Nothing here needs you right now.'}</p>}
            {lead.length > 0 && <ul className="mt-list" aria-label="My work">{lead.slice(0, limit).map(renderRow)}</ul>}
            {held.length > 0 && (
              <div className="mt-held" aria-label="Proposals held for you">
                <p className="note">Agents prepared these. Nothing runs until you accept; accepting runs the action as you.</p>
                <ProposalItems list={held} idPrefix="mwp-" label="Proposals held for you" />
              </div>
            )}
            {rest.length > 0 && <ul className="mt-list" aria-label="Other work">{rest.slice(0, Math.max(0, limit - lead.length)).map(renderRow)}</ul>}
            {listed.length > limit && (
              <div className="mt-more">
                <span className="note">Showing {limit} of {listed.length}</span>
                <button className="btn sm" onClick={() => setLimit(limit + PAGE)}>Show {Math.min(PAGE, listed.length - limit)} more</button>
              </div>
            )}
          </section>
        )}

        {(show === null || show === 'handed') && handed.length > 0 && (
          <section className="panel mt-sec" aria-labelledby="mt-handed">
            <header>
              <h2 id="mt-handed">Waiting on others <span className="num">{handed.length}</span></h2>
              <p className="note">Approved steps sent to an enterprise system that has not reported back. Nothing for you to do unless one is late.</p>
            </header>
            <ul className="mt-list" aria-label="Waiting on others">
              {(show === 'handed' ? handed : handed.slice(0, 6)).map((h) => (
                <li key={h.id} className="mt-row" data-kind="handed" data-id={h.id}>
                  <div className="mt-main">
                    <span className="mt-kind">{h.sys}{h.over ? <span className="mt-late"> · late, {ageText(h.age)}</span> : <> · {ageText(h.age)}</>}</span>
                    <b>{h.id} · {h.label}</b>
                    {h.ref && <span className="note">Reference {h.ref}</span>}
                  </div>
                  <div className="mt-acts"><a className="btn sm" href={'#/product/' + h.id}>Open</a></div>
                </li>
              ))}
            </ul>
            {show !== 'handed' && handed.length > 6 && <div className="mt-more"><span className="note">Showing 6 of {handed.length}, oldest first</span><a className="btn sm" href={'#' + tasksPath('handed')}>Show all {handed.length}</a></div>}
          </section>
        )}

        {show === null && conflicts.length > 0 && (
          <section className="panel mt-sec" aria-labelledby="mt-conf">
            <header>
              <h2 id="mt-conf">Data conflicts <span className="num">{conflicts.length}</span></h2>
            </header>
            <ul className="mt-list">
              <li className="mt-row" data-kind="conflict" data-group="conflicts">
                <div className="mt-main">
                  <b>{conflictSummary(conflicts.length)}</b>
                  <span className="note">Sources disagree on a field of an asset. A data owner settles them in the Conflict Queue.</span>
                </div>
                <div className="mt-acts">
                  <a className="btn sm ghost" href={'#' + tasksPath('conflict')}>List them here</a>
                  <a className="btn sm" href="#/integration/conflicts">Review in Conflict Queue</a>
                </div>
              </li>
            </ul>
          </section>
        )}
      </div>

      {show === null && (
        <>
          {[...new Set(s.kpis.map((k) => k.pack))].map((k) => (
            <section key={k} aria-label={'KPIs: ' + s.kpis.find((x) => x.pack === k)?.pack_name}>
              <p className="note" style={{ margin: '0 0 6px' }}>{s.kpis.find((x) => x.pack === k)?.pack_name}</p>
              <PackKpiTiles kpis={s.kpis.filter((x) => x.pack === k)} />
            </section>
          ))}
          {(can('manageLots') || can('approve.decisions')) && <LotsCard />}
          {can('manageFlows') && <AgeingCard />}
        </>
      )}
      {dialog && <ItemDialog d={dialog} onClose={() => setDialog(null)} />}
    </div>
  );
}

/** P9-2.10: "Assistant: cause · recommended action · owner" under an exception, from exception.explain. The assistant only
 *  proposes; the person resolves or assigns with the buttons of the row. The first few rows read it on their own; the
 *  rest read it when asked, so a long list does not spend a model call a row. Nothing shows when it cannot be read. */
function AssistantDraft({ id, auto }: { id: number; auto: boolean }) {
  const [want, setWant] = useState(auto);
  const [draft, setDraft] = useState<ExceptionDraft | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!want) return;
    let live = true;
    void explainException(id).then((r) => {
      if (!live) return;
      if (r.ok) setDraft(r.output);
      else setFailed(true);
    });
    return () => {
      live = false;
    };
  }, [id, want]);
  if (!want) return <span><button className="lnk" onClick={() => setWant(true)}>What the assistant suggests</button></span>;
  if (failed && !auto) return <span className="note">The assistant could not read this one.</span>;
  if (!draft) return auto ? null : <span className="note" role="status">Reading…</span>;
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
