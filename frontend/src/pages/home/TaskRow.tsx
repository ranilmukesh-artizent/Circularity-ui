import { runTaskAct, type TaskItem } from '../../api/home';
import { toast } from '../../components/toast';
import { refused } from '../../hooks/useAction';
import { ask, launch } from '../../utils/launchers';

/** The case id a task's title starts with ("RT-1048 …"), if any. */
export const taskCase = (title: string): string | undefined => (/^(RT-\d{4})/.exec(title) || [])[1];

/** A task's own button: an action (acknowledge) or a link to where the step is done. Yellow only when `primary`. */
export function TaskButton({ i, primary }: { i: TaskItem; primary?: boolean }) {
  const run = async () => {
    const r = await runTaskAct(i.act!, i.arg ?? '');
    if (!refused(r)) toast('Acknowledged. The sender sees it is in hand.');
  };
  const cls = 'btn sm' + (primary ? ' pri' : '');
  return i.act ? <button className={cls} onClick={run}>{i.btn}</button> : <a className={cls} href={'#/' + i.go}>{i.btn}</a>;
}

/** One "Needs you" row on Home: the item's own button, and Ask for a case. One row is `primary`: one yellow button a list. */
export function TaskRow({ i, primary }: { i: TaskItem; primary?: boolean }) {
  const cid = taskCase(i.t);
  return (
    <li className="aor">
      <span className="aot">
        <b>{i.t}</b>
        <span className="note">{i.d}</span>
      </span>
      <span className="row">
        {cid && (
          <button className="lnk" aria-label={'Ask about ' + cid} onClick={() => ask(launch.howToDoTask(i.t, cid))}>
            Ask
          </button>
        )}
        <TaskButton i={i} primary={primary} />
      </span>
    </li>
  );
}
