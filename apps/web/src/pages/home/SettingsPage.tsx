import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  autonomy, frPref, livePaused, notifTypes, presenterOn, region, regionOptions, roleDescription, setFrPref, setLivePaused, setPresenter, setRegion,
} from '../../api/home';
import { useBackend } from '../../api/useBackend';
import { allowedTenants, canPage, currentAccount, signInEmail, signOut } from '../../api/session';
import { Icon } from '../../ui/Icon';
import { applyTheme, useTheme } from '../../ui/theme';
import { toast } from '../../ui/toast';
import { FrHead, FrPanel, FrSeg } from './kit';

/** The menu's collapsed state belongs to the app shell; Settings drives its own toggle button. */
const railOn = () => !!document.querySelector('.app.rail');
const toggleRail = () => (document.querySelector('.railbtn') as HTMLButtonElement | null)?.click();

/** Settings (frSettings): profile, theme, region and currency, notifications, agent autonomy, presenter options. */
export function SettingsPage() {
  useBackend();
  const nav = useNavigate();
  const theme = useTheme();
  const [rail, setRail] = useState(railOn);
  const a = currentAccount()!;
  const rg = region(), opts = regionOptions(), nf = frPref<Record<string, boolean>>('notif') || {}, auto = autonomy(a.role), access = canPage('access');

  const leave = (msg: string) => {
    signOut();
    nav('/signin', { replace: true });
    toast(msg);
  };
  const lang = (v: string) => {
    setRegion('lang', v);
    document.documentElement.lang = v;
    toast(v === 'en' ? 'English.' : 'Preview: navigation and journey labels translated.');
  };
  const notif = (k: string, on: boolean) => {
    setFrPref('notif', { ...nf, [k]: on });
    toast(on ? 'You will be notified.' : 'Turned off.');
  };
  const pause = (off: boolean) => {
    setLivePaused(off);
    toast(off ? 'Live updates paused. The screen holds still until you turn them back on.' : 'Live updates on.');
  };

  return (
    <div className="frpage" id="frSettings">
      <FrHead title="Settings" sub="Your profile and preferences. Changes apply on this device; access and autonomy stay with Access & Governance." />
      <div className="frset">
        <FrPanel title="Profile" id="stProfile">
          <dl className="frdl">
            <dt>Signed in as</dt><dd>{a.label}</dd>
            <dt>Role</dt><dd>{a.role}</dd>
            <dt>Sign-in ID</dt><dd className="mono">{signInEmail(a)}</dd>
            <dt>Tenants</dt><dd>{allowedTenants().join(', ')}</dd>
            <dt>What the role does</dt><dd className="note">{roleDescription()}</dd>
          </dl>
          <div className="row">
            <button className="btn sm" onClick={() => leave('Sign in with another account to continue.')}>Switch account</button>
            <button className="btn sm" onClick={() => leave('Signed out of ' + a.label + '.')}><Icon name="logout" /> Sign out</button>
          </div>
        </FrPanel>
        <FrPanel title="Appearance" id="stLook">
          <div className="frfr">
            <span>Theme</span>
            <FrSeg name="theme" label="Theme" cur={theme} items={[['light', 'Light', 'sun'], ['dark', 'Dark', 'moon']]} onPick={(v) => applyTheme(v as 'light' | 'dark')} />
          </div>
          <div className="frfr">
            <span>Menu</span>
            <FrSeg
              name="menu" label="Menu" cur={rail ? 'rail' : 'open'} items={[['open', 'Expanded'], ['rail', 'Collapsed']]}
              onPick={(v) => { if ((v === 'rail') !== railOn()) toggleRail(); setRail(v === 'rail'); }}
            />
          </div>
        </FrPanel>
        <FrPanel title="Region and currency" id="stRegion">
          <div className="frfr">
            <label htmlFor="st-lang">Language</label>
            <select className="sel" id="st-lang" value={rg.lang} onChange={(e) => lang(e.target.value)}>
              {opts.lang.map((x) => <option key={x[0]} value={x[0]}>{x[1]}</option>)}
            </select>
          </div>
          <div className="frfr">
            <label htmlFor="st-tz">Time zone</label>
            <select className="sel" id="st-tz" value={rg.tz} onChange={(e) => setRegion('tz', e.target.value)}>
              {opts.tz.map((x) => <option key={x[0]} value={x[0]}>{x[1]}</option>)}
            </select>
          </div>
          <div className="frfr">
            <label htmlFor="st-cur">Local currency</label>
            <select className="sel" id="st-cur" value={rg.cur} onChange={(e) => setRegion('cur', e.target.value)}>
              {opts.cur.map((x) => <option key={x[0]} value={x[0]}>{x[1]}</option>)}
            </select>
          </div>
          <p className="note">Exchange rates are indicative; decisions stay in USD.</p>
        </FrPanel>
        <FrPanel title="Notifications" id="stNotif">
          <div className="frchk">
            {notifTypes().map((n) => (
              <label className="tog" key={n[0]}>
                <input type="checkbox" checked={nf[n[0]] !== false} onChange={(e) => notif(n[0], e.target.checked)} /> {n[1]}
              </label>
            ))}
          </div>
          <p className="note">Alerts always show in the bell and on the Alerts page; these choose what is also sent to you.</p>
        </FrPanel>
        <FrPanel title="Agent autonomy" id="stAuto">
          {auto.length ? (
            <table className="t static tight">
              <tbody>
                {auto.map((x) => (
                  <tr key={x[0]}>
                    <td>{x[0]}</td>
                    <td className="r"><span className="chip line">{x[1]}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="note">Agent autonomy is not available in this build.</p>
          )}
          <p className="note">
            What the agent may do on its own for the {a.role} role, capped by each action's risk tier.{' '}
            {access ? 'Admin changes it under Access & Governance.' : 'Ask Admin to change it.'}
          </p>
          {access && <a className="btn sm" href="#/access/autonomy">Open agent autonomy →</a>}
        </FrPanel>
        <FrPanel title="Presenter options" id="stPres">
          <label className="tog">
            <input type="checkbox" checked={presenterOn()} onChange={(e) => setPresenter(e.target.checked)} /> Show the Presenter menu on this device
          </label>
          <label className="tog">
            <input type="checkbox" checked={livePaused()} onChange={(e) => pause(e.target.checked)} /> Pause live updates
          </label>
          <p className="note">The Presenter menu holds the quick-fill chips and the drills. An audience never sees it unless it is turned on here.</p>
        </FrPanel>
      </div>
    </div>
  );
}
