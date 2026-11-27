# Phase 8 review (P9-8.23): Compose end to end

Reviewer: read-only code review (writer 85), 27 Nov 2026, on `lead-merge` (HEAD `76d6bd30`). Scope: the `P9-8.*` commits
(`fb5edca6` registry, `e193f486` mapping suggestions, `9e3d91fe` OIDC, `aa47ad28` group map, `a3e61c29` SCIM, `207cd766`
composition, `83f39c6f` publish step, and the others of the phase). No test was run; every finding was checked by reading the
code at the cited line. Focus (gate task): Review Focus 6 and 10, maker-checker on compositions, connections and group maps,
secrets, OIDC and SCIM.

## Findings

| # | Severity | Finding | File:line | Verified | Suggested action |
|---|---|---|---|---|---|
| 1 | P1 | SCIM can change the sign-in email of any directory user, Admin included. `_find_user` finds the record by external id or by the record's own id (`admin`); `_upsert` skips the role rule for an Admin account but then writes `email` from the request into the record (`keep`). `resolve_directory_user` signs in whoever presents that email as the linked account, so a holder of the `idp` webhook secret can give the Admin account to an identity of their choice. "Never Admin from a directory" holds for provisioning only. | `services/actions/access.py:723-727`, `:766-775`; `services/oidc.py:205-209` | Yes (code; not run) | Needs code: in `_upsert` refuse an email change (or any write) for a user whose account is Admin, as `scimDeactivateUser` does (`:795-802`); better, never let SCIM change the email of a linked account without a person. Test: SCIM PUT `external_id=admin` with a new email, expect `conflict`. |
| 2 | P2 | OIDC links an existing account by the ID token's `email` claim without checking `email_verified`. An identity provider that lets a user set an unverified email gets the linked account of that address. | `services/oidc.py:203-209` (grep: no `email_verified` in `backend/di`) | Yes | Require `email_verified is True` when the provider sends it; test with a token that says false. |
| 3 | P2 | Login CSRF: the OIDC state and the one-time code are kept in the database only, not tied to the browser that started the login. A victim who opens an attacker's callback URL is signed in as the attacker's account. | `services/oidc.py:96-111`, `:114-125`; `routes/auth.py:49-66` | Yes | Set a short-lived cookie (httponly, samesite lax) with a hash of the state at `/auth/oidc/start` and check it in the callback. |
| 4 | P2 | `registry.release` has no tenant check; `registry.saveEntry` and the connection actions have `_tenant_refusal`. A tenant-scoped manager can release another org's tested connector, and a release makes it visible to every org. Maker-checker compares only the version's creator. | `services/actions/connections.py:232-243` (compare `:124-129`, `:192-203`) | Yes | Call `_tenant_refusal(ctx, row.org_unit_id)` in `release_guard`. |
| 5 | P2 | `_apply_mapping` (and the `asked_owner` branch of `blocking`) read `steps.mapping.fields`, but no code in `backend/di` writes that key: the composition's mapping rows cannot be accepted through any action, so the approve step applies no mapping and the check cannot fire. Dead path with a tenant-relevant write (`mapping.save_version` by `source_id`) behind it. | `services/actions/compose.py:695-707`; `services/modeler/compose.py:49-51` (grep for writers finds none) | Yes (grep) | Either wire `mapping.decide` results into the step, or remove the path; if kept, check each `source_id` belongs to the composition's org. |

## Checked, no findings

- Review Focus 6: `connection.` (except `connection.discover`, which reads up to 500 sample rows), `registry.release`, `compose.sendBack|approve|publish`, `mapping.answerOwner`, `access.` and `credentials.rotate` are in `FORBIDDEN_ACTIONS` (`services/agents/forbidden.py`); `registry.saveEntry` and the mapping saves are `HELD_FOR_PERSON`; the pipeline refuses secret-handling actions for agents (`pipeline.py:139-142`).
- Review Focus 10 and maker-checker: `compose.approve` refuses the creator, submitter and every editor (`compose.py:666`); `compose.publish` refuses a prepared call and runs the rollout's own guard (`:850-867`); `registry.release` refuses the drafter (`connections.py:237`); `access.approveGroupMap` refuses the maker (`group_map.py:82`); an agent cannot approve a group mapping.
- Secrets: `connection.promote` writes the secret through `secrets.put_secret` only; the pipeline imports the redaction of `core/redact.py` for its journal (`pipeline.py:24`; the redaction itself was not read). The SCIM bearer is compared with `hmac.compare_digest` and no secret held means no access (`services/scim.py:113-119`). OIDC keeps no provider token, uses PKCE S256, state, nonce, RS256 only, and checks iss, aud, nonce, exp, sub (`oidc.py:126-150`); a group never gives Admin (`oidc.py:212`, `access.py:657`).
- Tenant boundary: compositions use `_org_ok` on the row's org (`compose.py:140-145`); connection actions use `_tenant_refusal`; the system owner must be able to see the tenant (`connections.py:372-376`).
- Replay and pilot: Compose test run reads the batch of the composition's org (not further traced).

## Needs code

- F1 (P1): SCIM must not edit an Admin-linked record. F2-F5 as listed.

Legal: findings 1-3 concern access control, not accounting or reporting; no Legal review needed beyond the outside-client access review already planned.
