import { checkOwner, checks, checksNotRun, checksRunAt, runChecks, status } from '../../api/home';
import { fmtDate } from '../../api/format';
import { useBackend } from '../../api/hooks';
import { Icon } from '../../ui/Icon';
import { toast } from '../../ui/toast';
import { askSoon, FrHead, FrKpi, FrPanel, FrSt } from './kit';

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
      <FrHead
        title="Data Checks"
        sub="One data model feeds every page, so numbers reconcile everywhere. These checks run on every load; run them again at any time."
        right={<button className="btn pri" onClick={run}><Icon name="play" /> Run data checks</button>}
      />
      <div className="frkpis fr4">
        <FrKpi o={{ ic: 'checks', h: 'int', v: ok, n: ok, l: 'Checks passing', k: '' }} />
        <FrKpi o={{ ic: 'alert', h: 'alert', v: res.length - ok, n: res.length - ok, l: 'Checks failing', k: '' }} />
        <FrKpi o={{ ic: 'clock', h: 'neutral', v: fmtDate(at), l: 'Last run', sub: new Date(at).toISOString().slice(11, 16) + ' UTC', k: '' }} />
        <FrKpi o={{ ic: 'shield', h: 'agent', v: res.length, n: res.length, l: 'Checks in total', k: '' }} />
      </div>
      <FrPanel title="Checks" sub={ok + ' of ' + res.length + ' pass'}>
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
                  <td><FrSt s={r.ok ? status('success', 'Pass') : status('failed', 'Fail')} /></td>
                  <td>{checkOwner(r.name)}</td>
                  <td><button className="lnk" onClick={askSoon}><Icon name="spark" /> Explain</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </FrPanel>
      {skipped.length > 0 && (
        <FrPanel title="Not run here" sub={skipped.length + ' checks test the demo page itself'}>
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
                    <td><FrSt s={status('disconnected', 'Not run')} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </FrPanel>
      )}
    </div>
  );
}
