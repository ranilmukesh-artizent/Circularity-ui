"""Build the stored drafts of the sample prompts (plan 11, C1). Run inside the api container:

    docker compose exec -T -e PYTHONPATH=/app api python -u scripts/build_stored_drafts.py [pack_key ...]

(default packs: tool_fleet, device, industrial).

For each sample prompt of each pack it runs the real model step of `compose.start` (`pack_author.make_drafter`, the `author`
role of the router) once, passes the draft through `draft_change_set` exactly as `compose.start` does (every check of
`_accept`), and only when a model answered and the checks accepted it writes it to `di/services/modeler/packs/stored_drafts/`.
A rate-limited call is retried up to three times with a growing pause; a prompt that still fails is left out (never a rules
result). The free tier allows a few requests a minute, so there is a pause between prompts as well.
"""

import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime

from di.core.db import SessionLocal
from di.repositories.packs import active_pack
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.agents.config_agent import ChangeSetError, Drafter, ModelDraft, Reading, draft_change_set, read_text
from di.services.agents.playbooks import pack_author
from di.services.modeler.compose import write_stored_draft
from di.services.modeler.pack import Pack, load_pack

DEFAULT_PACKS = ("tool_fleet", "device", "industrial")
ORG = "Customer A"
PAUSES = (20, 45, 90)  # seconds before retry 1, 2, 3
BETWEEN = 15  # seconds between prompts


class Recorder:
    """The live drafter, keeping the model drafts it returned (a prompt is stored only from one)."""

    def __init__(self, live: Drafter) -> None:
        self.live = live
        self.got: list[ModelDraft] = []

    def __call__(
        self, text: str, reading: Reading, packs: Sequence[Pack], answer: str | None, error: str | None
    ) -> ModelDraft | None:
        d = self.live(text, reading, packs, answer, error)
        if d is not None:
            self.got.append(d)
        return d


def build_one(key: str, prompt: str) -> ModelDraft | None:
    """The accepted model draft of one prompt, or None when no model answered or the checks refused it, after three retries."""
    for attempt in range(len(PAUSES) + 1):
        with SessionLocal() as s:
            packs = [active_pack(s, key, ORG)]
            rec = Recorder(pack_author.make_drafter(CallContext(actor=SYSTEM, session=s)))
            try:
                cs = draft_change_set(prompt, ORG, packs=packs, answer=None, drafter=rec)
            except ChangeSetError as e:
                print(f"  refused: {e.message}")
                cs = None
            if cs is not None and cs.by_model and len(rec.got) == 1 and rec.got[0].pack == key:
                return rec.got[0]
            print(f"  no accepted model answer (attempt {attempt + 1})")
        if attempt < len(PAUSES):
            time.sleep(PAUSES[attempt])
    return None


def main(keys: list[str]) -> int:
    failed = 0
    for key in keys:
        pack = load_pack(key)
        read_text("x", [pack])  # fail early on a broken pack
        for n, prompt in enumerate(p for p in pack.prompts if p):
            print(f"{key} prompt {n + 1}: {prompt[:70]}")
            draft = build_one(key, prompt)
            if draft is None:
                failed += 1
                print("  LEFT OUT")
            else:
                write_stored_draft(key, pack.version, prompt, draft.model_dump(mode="json"), datetime.now(UTC).isoformat())
                print(f"  stored ({len(draft.ops)} ops)")
            time.sleep(BETWEEN)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or list(DEFAULT_PACKS)))
