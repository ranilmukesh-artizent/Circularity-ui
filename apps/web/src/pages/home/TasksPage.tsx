import { useState } from 'react';
import { runTaskAct, taskGroupOf, taskGroups, taskItems, type TaskItem } from '../../api/home';
import { useBackend } from '../../api/useBackend';
import { Icon } from '../../ui/Icon';
import { toast } from '../../ui/toast';
import { askSoon, FrHead, FrKpi, FrPanel, FrSeg } from './kit';

/** One "Needs you" row: the item's own button (an action) or a link to where the step is done. */
export function TaskRow({ i }: { i: TaskItem }) {
  const cid = (/^(RT-\d{4})/.exec(i.t) || [])[1];
  const run = async () => {
    const r = await runTaskAct(i.act!, i.arg ?? '');
    toast(r.ok ? 'Acknowledged. The sender sees it is in hand.' : r.error.message);
  };
  return (
    <li className="aor">
      <span className="aot">
        <b>{i.t}</b>
        <span className="note">{i.d}</span>
      </span>
      <span className="row">
        {cid && (
          <button className="afai" aria-label={'Ask about ' + cid} onClick={askSoon}>
            ✦
          </button>
        )}
        {i.act ? (
          <button className="btn sm pri" onClick={run}>
            {i.btn}
          </button>
        ) : (
          <a className="btn sm pri" href={'#/' + i.go}>
            {i.btn} →
          </a>
        )}
      </span>
    </li>
  );
}

/** My Tasks (frTasks): Needs you, grouped by what it asks of you. */
export function TasksPage() {
  useBackend();
  const [f, setF] = useState('all');
  const G = taskGroups();
  const l = taskItems().map((i) => ({ ...i, g: taskGroupOf(i) }));
  const vis = l.filter((i) => f === 'all' || i.g === f);
  const count = (id: string) => l.filter((i) => i.g === id).length;
  const groups = G.filter((g) => f === 'all' || f === g[0])
    .map((g) => ({ g, it: vis.filter((i) => i.g === g[0]) }))
    .filter((x) => x.it.length);
  return (
    <div className="frpage" id="frTasks">
      <FrHead
        title="My Tasks"
        sub="Everything whose next step is yours, grouped by what it asks of you. The same list feeds Home › Needs you."
        right={<span className={'chip ' + (l.length ? 'warn' : 'ok')} id="frTasksN">{l.length} open</span>}
      />
      <div className="frkpis fr4">
        {G.map((g) => (
          <FrKpi key={g[0]} o={{ ic: g[2], h: g[3], v: count(g[0]), n: count(g[0]), l: g[1], k: g[0] }} />
        ))}
      </div>
      <div className="frbar">
        <FrSeg
          name="tasks" label="Task group" cur={f} onPick={setF}
          items={[['all', 'All (' + l.length + ')'] as [string, string]].concat(G.map((g) => [g[0], g[1] + ' (' + count(g[0]) + ')']))}
        />
      </div>
      {groups.length ? (
        groups.map(({ g, it }) => (
          <FrPanel
            key={g[0]} title={g[1]} sub={it.length + ' item' + (it.length > 1 ? 's' : '')}
            right={<button className="btn sm" onClick={askSoon}><Icon name="spark" /> Do it for me</button>}
          >
            <ul className="aol">
              {it.map((i, k) => <TaskRow key={k} i={i} />)}
            </ul>
          </FrPanel>
        ))
      ) : (
        <div className="empty">
          <b>Nothing waits on you</b>New items appear here when a step becomes yours.
        </div>
      )}
    </div>
  );
}
