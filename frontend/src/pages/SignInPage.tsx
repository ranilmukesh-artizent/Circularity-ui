import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { logos } from '../api/nav';
import { SSO_START_URL, accounts, exchangeSsoCode, homeRoute, rolePolicy, signInEmail, signInWith, ssoConfig } from '../api/session';
import type { Account } from '../api/types';
import { Icon } from '../components/Icon';
import { useTheme, toggleTheme } from '../utils/theme';
import { toast } from '../components/toast';

/** Sign-in form (the demo's signInFormHTML). Authentication is simulated: any non-empty password is accepted. */
export function SignInPage({ next }: { next?: string }) {
  const nav = useNavigate();
  const theme = useTheme();
  const [id, setId] = useState('');
  const [pw, setPw] = useState('');
  const [err, setErr] = useState('');
  const [sso, setSso] = useState(false);
  const [org, setOrg] = useState<{ enabled: boolean; label?: string }>({ enabled: false });
  const [params] = useSearchParams();
  const ssoCode = params.get('sso');
  const exchanged = useRef(false); // a one-time code is swapped once, also under StrictMode's second effect run
  const idRef = useRef<HTMLInputElement>(null);
  const pwRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    document.title = 'Sign in · Circularity Decision Workbench';
    document.getElementById('app')?.classList.add('signedout');
    idRef.current?.focus();
    return () => document.getElementById('app')?.classList.remove('signedout');
  }, []);

  useEffect(() => {
    void ssoConfig().then(setOrg);
    const refused = params.get('sso_error');
    if (refused) setErr(refused);
  }, [params]);

  useEffect(() => {
    if (!ssoCode || exchanged.current) return;
    exchanged.current = true;
    void exchangeSsoCode(ssoCode).then((r) => {
      if (r.ok) entered(r.account);
      else setErr(r.message);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once for the code in the URL
  }, [ssoCode]);

  function entered(a: Account) {
    toast('Signed in as ' + a.label + '. ' + rolePolicy(a.role).desc, 4200);
    nav('/' + (next || homeRoute(a)), { replace: true });
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const r = await signInWith(id, pw);
    if (!r.ok) return fail(r.message, r.field === 'pw' ? pwRef : idRef);
    setErr('');
    entered(r.account);
  }

  function singleSignOn() {
    if (!id.trim()) return fail('Enter your work email to continue with single sign-on.', idRef);
    setErr('');
    setSso(true);
    window.setTimeout(async () => {
      const r = await signInWith(id, '', true);
      if (!r.ok) {
        setSso(false);
        return fail(r.message, idRef);
      }
      entered(r.account);
    }, 600);
  }

  function fail(m: string, ref: React.RefObject<HTMLInputElement>) {
    setErr(m);
    ref.current?.focus();
  }

  return (
    <div className="si">
      <div className="sibox">
        <div className="sil">
          <img src={logos().dark} alt="Artizent" />
          <h1>
            Circularity
            <br />
            Decision Workbench
          </h1>
          <p>
            Decide the best next use for every returned asset, with the evidence from your enterprise systems and the predicted value
            side by side.
          </p>
          <div className="sitag">In production you sign in with your company account.</div>
        </div>
        <div className="sir si2">
          <div className="row between">
            <h2>Sign in</h2>
            <button className="iconbtn" aria-label="Toggle theme" onClick={toggleTheme}>
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
          </div>
          <p className="note" style={{ margin: '4px 0 0' }}>
            Use your work email or user ID.
          </p>
          {org.enabled && (
            <>
              <button className="btn pri si2b" type="button" style={{ marginTop: 12 }} onClick={() => window.location.assign(SSO_START_URL)}>
                {org.label ?? 'Sign in with your organisation'}
              </button>
              <div className="si2or" aria-hidden="true">
                or use the demo sign-in
              </div>
            </>
          )}
          <form className="si2f" noValidate onSubmit={submit}>
            <div className="fld">
              <label htmlFor="si-id">Work email or user ID</label>
              <input
                ref={idRef} id="si-id" name="username" type="text" placeholder="name@company.com" autoComplete="username"
                autoCapitalize="none" spellCheck={false} list="si-ids" aria-describedby="si-err" value={id} onChange={(e) => setId(e.target.value)}
              />
            </div>
            <div className="fld">
              <label htmlFor="si-pw">Password</label>
              <input
                ref={pwRef} id="si-pw" name="password" type="password" autoComplete="current-password" aria-describedby="si-err"
                value={pw} onChange={(e) => setPw(e.target.value)}
              />
            </div>
            <div className="err" id="si-err" role="alert" hidden={!err}>
              {err}
            </div>
            <div className="si2help">
              <span className="note">You stay signed in on this device until you sign out.</span>
              <span className="note">Forgot your password? Contact your administrator.</span>
            </div>
            <button className="btn pri si2b" type="submit">
              Sign in
            </button>
            <div className="si2or" aria-hidden="true">
              or
            </div>
            <button className={'btn si2b' + (sso ? ' wait' : '')} type="button" disabled={sso} onClick={singleSignOn}>
              {sso ? 'Redirecting to your organisation’s identity provider…' : 'Continue with single sign-on'}
            </button>
          </form>
          <datalist id="si-ids">
            {accounts().map((a) => (
              <option key={a.id} value={signInEmail(a)}>
                {a.label}
              </option>
            ))}
          </datalist>
        </div>
      </div>
    </div>
  );
}
