/**
 * The replay a person runs before Compose's Publish step shows figures (owner decision, 28 Nov 2026: the step shows replay
 * figures only from a real replay run of the draft; "No replay report yet" otherwise). Helper for smoke-p9-9, p9-10 and p9-11.
 *
 *   await replayTheDraft(p, { modeler: MODELER, csv: path to fixtures/replay/<pack>.csv, open, timeout })
 *
 * In the Modeler of the pack and org (planner.a): gives the org its own flow when it reads the workspace's, makes a draft when
 * the flow is published (Add rule: a rule without a path compiles to nothing, so the draft decides as the published flow does),
 * opens the Replay step of the lifecycle bar, imports the history and replays the draft until its report shows. The publish
 * step reads the report of the run on the draft as it is now (`rollout_repo.done_replay`: same draft version and content).
 * `open(p, url, ready)` is the smoke's own: goto, reload, wait for `ready`.
 */
export async function replayTheDraft(p, { modeler, csv, open, timeout = 180000 }) {
  await open(p, modeler, '.mdl-life');
  const status = p.locator('.mdl-life [data-status]').first();
  const fork = p.getByRole('button', { name: /^Give .* its own flow$/ });
  if (await fork.waitFor({ timeout: 8000 }).then(() => true, () => false)) {
    await fork.click();
    await fork.waitFor({ state: 'detached', timeout });
  }
  if ((await status.getAttribute('data-status')) === 'pub') {
    await p.getByRole('button', { name: 'Add rule', exact: true }).click();
    // the 2 s autosave writes the draft; the bar then reads "Draft · v<n>"
    await p.locator('.mdl-life [data-status="draft"]').waitFor({ timeout });
  }
  const replay = p.locator('.mdl-life').getByRole('button', { name: 'Replay', exact: true });
  await replay.waitFor({ timeout });
  await replay.click();
  const panel = p.locator('.mdl-replay');
  await panel.waitFor({ timeout });
  await panel.locator('#mdl-rp-file').setInputFiles(csv);
  const run = panel.locator('[data-replay-run]').first();
  await run.waitFor({ timeout });
  await run.locator('select').selectOption('draft');
  const reports = () => panel.locator('[data-replay-report]').evaluateAll((xs) => xs.map((x) => x.getAttribute('data-replay-report')));
  const before = new Set(await reports()); // an earlier run's report shows when the drawer opens: wait for this run's
  await run.getByRole('button', { name: 'Replay the draft', exact: true }).click();
  const refused = panel.locator('[data-replay-refusal]');
  const end = Date.now() + timeout;
  for (;;) {
    if (await refused.count()) throw new Error('the replay was refused: ' + (await refused.first().innerText()));
    if ((await reports()).some((id) => !before.has(id))) break;
    if (Date.now() > end) throw new Error('the replay of the draft showed no report');
    await p.waitForTimeout(1500);
  }
  return (await status.innerText().catch(() => '')).trim();
}
