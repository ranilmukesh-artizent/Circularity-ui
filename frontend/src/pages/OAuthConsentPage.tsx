import { useEffect, useState } from 'react';
import { answerConsent, consentRequest, SCOPE_TEXT, type ConsentRequest } from '../api/agents';

/**
 * Consent page of the OAuth flow for outside MCP clients (plan 9, P9-13.10), at #/oauth/consent?req=<signed request>.
 * A top-level page like the sign-in page (App renders it outside the shell); a signed-out person signs in first and
 * comes back here. Allow or Deny sends the browser to the client's redirect URI with the answer. An agent never
 * consents: the server refuses an agent's token.
 */
export function OAuthConsentPage({ req }: { req: string }) {
  const [ask, setAsk] = useState<ConsentRequest | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    document.title = 'Allow access · Circularity Decision Workbench';
    consentRequest(req).then(setAsk, (e: unknown) => setErr(e instanceof Error ? e.message : 'This request is not valid.'));
  }, [req]);
  const answer = async (approve: boolean) => {
    setBusy(true);
    try {
      window.location.assign((await answerConsent(req, approve)).redirect);
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not send your answer.');
      setBusy(false);
    }
  };
  return (
    <div id="app" className="app signedout">
      <main className="panel" style={{ maxWidth: 520, margin: '10vh auto', padding: 24 }}>
        <h1>Allow access</h1>
        {err && <div className="callout bad" role="alert">{err}</div>}
        {ask && (
          <>
            <p>
              <b>{ask.client_name}</b> wants to act as <b>{ask.agent_name}</b> for you, with:
            </p>
            <ul>{ask.scopes.map((s) => <li key={s}>{SCOPE_TEXT[s] ?? s}</li>)}</ul>
            <p className="note">It can prepare work for you. It cannot approve anything: approvals stay with people.</p>
            <button className="btn pri" disabled={busy} onClick={() => answer(true)}>Allow</button>{' '}
            <button className="btn" disabled={busy} onClick={() => answer(false)}>Deny</button>
          </>
        )}
      </main>
    </div>
  );
}
