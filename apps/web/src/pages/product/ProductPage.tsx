/**
 * The `product` page (Decision Workbench): Returned assets, Expected returns, Pool optimizer, Asset intelligence,
 * and live cases (#/product/<CASE_ID>[/<view>]), which the case area draws.
 */
import { Navigate } from 'react-router-dom';
import { money } from '../../api/format';
import { useBackend } from '../../api/useBackend';
import { caseById, demoVisible, isCaseId, pool, tenantOK } from '../../api/product';
import { CasePage } from '../case/CasePage';
import type { PageProps } from '../registry';
import { AssetPage } from './AssetPage';
import { ReturnedAssetsPage } from './ReturnedAssetsPage';
import './product.css';

export function ProductPage({ route, query }: PageProps) {
  useBackend();
  const a = route.a;
  if (a === 'asset') {
    // journey links (?jstep=1–5) open the case's stage page instead, replacing the history entry (stResolve)
    const js = parseInt(query.get('jstep') ?? '', 10);
    if (route.b && caseById(route.b) && js >= 1 && js <= 5 && demoVisible(route.b)) return <Navigate to={`/product/${route.b}/stage/${js}`} replace />;
    return <AssetPage key={route.b ?? ''} id={route.b} zone={query.get('zone')} />;
  }
  if (a === 'pools') return <PoolsPage />;
  if (a && isCaseId(a)) return <CasePage caseId={a} view={route.b} query={query} />;
  return <ReturnedAssetsPage view={a === 'expected' ? 'expected' : 'received'} focus={query.get('focus')} />;
}

/** Pool optimizer (poolsPage): hidden while FEAT.pools is off, so canPage('product', 'pools') keeps it out of reach. */
function PoolsPage() {
  useBackend();
  const ids = ['RT-1048', 'RT-1052'].filter((id) => { const c = caseById(id); return !!c && tenantOK(c.owner); });
  return (
    <>
      <div className="phead">
        <div>
          <div className="crumbs"><a href="#/product">Returned assets</a> / Pool optimizer</div>
          <h1>Pool optimizer</h1>
          <p>Scarce assets, components, repair capacity and buyer demand are matched across the whole pool, with each resource allocated once.</p>
        </div>
      </div>
      {!ids.length && <div className="empty"><b>No pools in your tenants</b>Pools appear here when they include assets from a tenant you can see.</div>}
      <div className="grid g2">
        {ids.map((id) => {
          const p = pool(id)!;
          return (
            <div key={id} className="panel">
              <div className="ph">
                <h3>{id === 'RT-1048' ? 'Motors for Site 3 and Site 5' : 'Tool batches for Site 2, Site 6 and the dealer lot'}</h3>
                <span className="stp" title="Journey step 4"><b>4</b></span>
              </div>
              <div className="pb">
                <div className="grid g2">
                  <div><div className="note">Per-asset greedy</div><div className="num" style={{ font: '800 26px var(--f-display)' }}>{money(p.greedy.total)}</div></div>
                  <div><div className="note">Pool-optimized</div><div className="num" style={{ font: '800 26px var(--f-display)' }}>{money(p.optimal.total)}</div></div>
                </div>
                <div className="callout ok" style={{ margin: '12px 0' }}>Pool optimization adds <b>{money(p.uplift)}</b> and prevents duplicate allocation.</div>
                <div className="note">Assets: {p.supplies.map((s) => s.id).join(', ')} · Demand lines: {p.dests.map((d) => d.id).join(', ')}</div>
                <div style={{ marginTop: 12 }}><a className="btn pri" href={'#/product/' + id}>Open {id}</a></div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

