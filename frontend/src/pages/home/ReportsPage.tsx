import { useState } from 'react';
import { asOfLabel, logReportExported, logReportViewed, reportLink, reportRows, reports, toCsv, type Report } from '../../api/home';
import { reportCell } from './reportCells';
import { useBackend } from '../../api/useBackend';
import { allowedTenants } from '../../api/session';
import { Icon } from '../../components/Icon';
import { Modal } from '../../components/Overlay';
import { toast } from '../../components/toast';
import { ask, launch } from '../../utils/launchers';
import { IconTile } from '../../components/kit/IconTile';
import { HomeHeader } from './HomeHeader';

const PERIODS: [string, string][] = [['30', 'Last 30 days'], ['90', 'Last 90 days'], ['365', 'Last 12 months']];
type Cell = string | number;

function download(csv: string, name: string) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = name;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Reports (frReports): six reports, each with a preview, scope and export (CSV, or PDF through print). */
export function ReportsPage() {
  useBackend();
  const [tenant, setTenant] = useState('All');
  const [period, setPeriod] = useState('90');
  const [print, setPrint] = useState<{ r: Report; rows: Cell[][] } | null>(null);
  const L = reports(), ten = allowedTenants();

  const csv = (r: Report) => {
    download(toCsv(reportRows(r.id, tenant, period)), 'circularity-' + r.id + '-' + tenant.toLowerCase().replace(/\s+/g, '-') + '.csv');
    logReportExported(r.t);
    toast(r.t + ' exported as CSV.');
  };
  const pdf = (r: Report) => {
    setPrint({ r, rows: reportRows(r.id, tenant, period) });
    logReportViewed(r.t);
  };
  const doPrint = () => {
    document.body.classList.add('frprinting');
    window.setTimeout(() => {
      try {
        window.print();
      } catch {
        /* print unavailable */
      }
      document.body.classList.remove('frprinting');
    }, 50);
  };

  return (
    <div className="frpage" id="frReports">
      <HomeHeader title="Reports" sub="Six reports built from the same data as every page. Choose the scope, preview, then export as CSV or print to PDF." />
      <div className="frbar">
        <label htmlFor="frRepT">Tenant</label>
        <select className="sel" id="frRepT" value={tenant} onChange={(e) => setTenant(e.target.value)}>
          <option value="All">All in view</option>
          {ten.map((t) => <option key={t}>{t}</option>)}
        </select>
        <label htmlFor="frRepP">Period</label>
        <select className="sel" id="frRepP" value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((o) => <option key={o[0]} value={o[0]}>{o[1]}</option>)}
        </select>
      </div>
      <div className="frrep">
        {L.map((r) => {
          const link = reportLink(r.id);
          if (link)
            return (
              <section className="panel frrc" id={'rep-' + r.id} key={r.id}>
                <div className="frrch">
                  <IconTile ic={r.ic} h={r.h} />
                  <div>
                    <h3>{r.t}</h3>
                    <p className="note">{r.d}</p>
                  </div>
                </div>
                <div className="frrcf">
                  <span className="note">Preview, scope and export are on the audit log.</span>
                  <span className="row">
                    <a className="btn sm pri" href={'#/' + link}><Icon name="audit" /> Open the audit log</a>
                  </span>
                </div>
              </section>
            );
          const rows = reportRows(r.id, tenant, period), body = rows.slice(1, 5);
          return (
            <section className="panel frrc" id={'rep-' + r.id} key={r.id}>
              <div className="frrch">
                <IconTile ic={r.ic} h={r.h} />
                <div>
                  <h3>{r.t}</h3>
                  <p className="note">{r.d}</p>
                </div>
              </div>
              <div className="tw frrpv">
                <table className="t static tight">
                  <thead>
                    <tr>{rows[0].map((h, i) => <th key={i}>{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {body.length ? (
                      body.map((x, i) => (
                        <tr key={i}>
                          {x.map((v, j) => {
                            const c = reportCell(rows[0][j], v);
                            return <td key={j} className={(c.num ? 'r num ' : '') + (c.id || /^(stage|tenant)$/i.test(String(rows[0][j])) ? 'nowrap' : '') + (c.empty ? ' note' : '')}>{c.text}</td>;
                          })}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={rows[0].length} className="note">No rows in this scope.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="frrcf">
                <span className="note">{rows.length - 1} row{rows.length === 2 ? '' : 's'}</span>
                <span className="row">
                  <button className="btn sm" onClick={() => ask(launch.summariseReport(r.t))}>Summarise</button>
                  <button className="btn sm" onClick={() => pdf(r)}><Icon name="report" /> PDF</button>
                  <button className="btn sm pri" onClick={() => csv(r)}><Icon name="download" /> CSV</button>
                </span>
              </div>
            </section>
          );
        })}
      </div>
      {print && (
        <Modal
          title={print.r.t} wide onClose={() => setPrint(null)}
          foot={
            <>
              <button className="btn" onClick={() => setPrint(null)}>Close</button>
              <button className="btn pri" onClick={doPrint}>Print or save as PDF</button>
            </>
          }
        >
          <div className="frprint">
            <p className="note">Northfield Industrial Leasing · {tenant === 'All' ? 'All tenants in view' : tenant} · {asOfLabel()}</p>
            <div className="tw">
              <table className="t static tight">
                <thead>
                  <tr>{print.rows[0].map((h, i) => <th key={i}>{h}</th>)}</tr>
                </thead>
                <tbody>
                  {print.rows.slice(1, 200).map((x, i) => (
                    <tr key={i}>{x.map((v, j) => {
                      const c = reportCell(print.rows[0][j], v);
                      return <td key={j} className={(c.id ? 'nowrap' : '') + (c.empty ? ' note' : '')}>{c.text}</td>;
                    })}</tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
