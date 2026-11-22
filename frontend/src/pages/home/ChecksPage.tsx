import { checkOwner, checks, checksNotRun, checksRunAt, runChecks, status } from '../../api/home';
import { fmtDate } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import { Icon } from '../../components/Icon';
import { toast } from '../../components/toast';
import { askSoon } from '../../utils/askBus';
import { Panel } from '../../components/kit/Panel';
import { StatusPill } from '../../components/kit/StatusPill';
import { HomeHeader } from './HomeHeader';
import { HomeKpi } from './HomeKpi';

/** Data Checks (frChecks): the integrity checks as a page. */
export function ChecksPage() {
  useBackend();
  const res = checks(), ok = res.filter((r) => r.ok).length, at = checksRunAt(), skipped = checksNotRun();
  const run = () => {
    const r = runChecks();
    toast(r.ok + ' of ' + r.total + ' checks pass.');
  };
  return (
    <div className="frpage" id="frChecks">
      <HomeHeader
        title="Data Checks"
        sub="One data model feeds every page, so numbers reconcile everywhere. These checks run on every load; run them again at any time."
        right={<button className="btn pri" onClick={run}><Icon name="play" /> Run data checks</button>}
      />
      <div className="frkpis fr4">
        <HomeKpi o={{ ic: 'checks', h: 'int', v: ok, n: ok, l: 'Checks passing', k: '' }} />
        <HomeKpi o={{ ic: 'alert', h: 'alert', v: res.length - ok, n: res.length - ok, l: 'Checks failing', k: '' }} />
        <HomeKpi o={{ ic: 'clock', h: 'neutral', v: fmtDate(at), l: 'Last run', sub: new Date(at).toISOString().slice(11, 16) + ' UTC', k: '' }} />
        <HomeKpi o={{ ic: 'shield', h: 'agent', v: res.length, n: res.length, l: 'Checks in total', k: '' }} />
      </div>
      <Panel title="Checks" sub={ok + ' of ' + res.length + ' pass'}>
        <div className="tw">
          <table className="t static">
            <thead>
              <tr><th>Check</th><th>What is checked</th><th>Last result</th><th>Owner</th><th /></tr>
            </thead>
            <tbody>
              {res.map((r) => (
                <tr key={r.name}>
                  <td><b>{r.name}</b></td>
                  <td className="note">{r.detail}</td>
                  <td><StatusPill {...(r.ok ? status('success', 'Pass') : status('failed', 'Fail'))} /></td>
                  <td>{checkOwner(r.name)}</td>
                  <td><button className="lnk" onClick={askSoon}><Icon name="spark" /> Explain</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {skipped.length > 0 && (
        <Panel title="Not run here" sub={skipped.length + ' checks test the demo page itself'}>
          <div className="tw">
            <table className="t static">
              <thead>
                <tr><th>Check</th><th>Why it is not run</th><th>Last result</th></tr>
              </thead>
              <tbody>
                {skipped.map((r) => (
                  <tr key={r.name}>
                    <td><b>{r.name}</b></td>
                    <td className="note">{r.reason}</td>
                    <td><StatusPill {...status('disconnected', 'Not run')} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}
