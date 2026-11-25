# Lane B machine notes (for writers; read with WRITER-BRIEF.md)

This lane runs on Windows with Docker inside WSL (`Ubuntu-24.04`). Git Bash fails here with "fork: Resource
temporarily unavailable", and there is no host Python or Docker CLI. Use these instead of the brief's Git Bash lines:

- **Git:** the PowerShell tool (`git merge --ff-only feature/plan-09-lane-b`, `git add -- <paths>`,
  `git commit -F <file>`). Write the commit message to a file first.
- **wt-check:** one foreground PowerShell command with a long timeout (600000 ms), from anywhere. Writers share
  three check slots (since the VM has 11 GB): take yours with `flock /tmp/wt-slot-<k mod 3>.lock` (writers 3 and 6:
  slot 0; writers 1 and 4: slot 1; writers 2 and 5: slot 2):
  ```
  wsl -d Ubuntu-24.04 -u root --cd <your worktree's Windows path> -- flock /tmp/wt-slot-<k mod 3>.lock env WT_BASE=feature/plan-09-lane-b WT_LINT=0 bash scripts/dev/wt-check.sh <k> tests/test_x.py
  ```
  If the command hits the timeout while it waits for the slot, run it again; never move it to the background.
  - Drop `WT_LINT=0` for the full check.
  - **Add `WT_WEB=1` whenever you changed `frontend/`.** WSL's git can't read a Windows worktree, so the script can't
    detect frontend changes on its own.
- **source-sim tests** (`source-sim/tests/*`): they use the shared database `sources_test`, so take the lock:
  ```
  wsl -d Ubuntu-24.04 -u root --cd <worktree> -- flock /tmp/sim-test.lock docker compose -p circularity-ui run --rm --no-deps -T source-sim pytest -q -p no:cacheprovider tests/test_x.py
  ```
  Run only your own test files. Report them; the lead runs them again on the main stack.
- **Python scripts** (for example `scripts/dev/*.py`): `wsl -d Ubuntu-24.04 -u root --cd <worktree> -- python3 ...`.
- **Memory:** the Docker VM has about 11 GB, shared by up to six writers and the lead. Always run wt-check under your slot
  lock, run one check at a time, and never leave one running when you finish.
- **Temporary source-sim** (to prove a sync test against your new mock): only under your slot lock, on a database
  `sources_w<k>`, and removed before you release it.
- **Forbidden checks:** in product code, call `di.services.agents.forbidden.forbidden(action_id)`, never `action_id.startswith(FORBIDDEN_ACTIONS)`: since lane A's aa47ad2, AGENT_EXEMPT lets a few actions through (`connection.discover`).
