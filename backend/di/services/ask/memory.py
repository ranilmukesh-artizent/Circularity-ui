"""Ask's short conversation memory: the last few turns per conversation, kept per account (state collection "ask_turns").

A conversation is one item: {account, turns: [{q, a, provider, at}]}, the newest MAX_TURNS kept. Its id (ASK-<n>) is
returned with every answer; a follow-up question sends it back. A conversation belongs to the account that started
it: another account's id (or an unknown one) starts a new conversation, so nobody reads someone else's turns.

What the model is given from memory is the questions and the final answers only (no tool results): the data behind
an earlier answer is read again, through the access policy, when the model needs it.
"""

from sqlalchemy.orm import Session

from di.core import clock, state
from di.mcp.calllog import iso_ms

COLLECTION = "ask_turns"
MAX_TURNS = 6
ANSWER_MAX = 1200  # characters of an earlier answer kept for the model
state.register(COLLECTION, lambda: [])


def load(s: Session, account_id: str, conversation_id: str | None) -> tuple[str | None, list[dict]]:
    """(the conversation id if it is this account's, its turns); (None, []) for a new conversation."""
    if not conversation_id:
        return None, []
    item = state.get(s, COLLECTION, conversation_id)
    if not item or item.get("account") != account_id:
        return None, []
    return conversation_id, item.get("turns") or []


def messages(turns: list[dict]) -> list[dict]:
    """Earlier turns as chat messages for a model."""
    out = []
    for t in turns:
        out += [{"role": "user", "content": t["q"]}, {"role": "assistant", "content": (t.get("a") or "")[:ANSWER_MAX]}]
    return out


def save(s: Session, account_id: str, conversation_id: str | None, turns: list[dict], q: str, a: str, provider: str) -> str:
    """Add a turn; returns the conversation id (a new one when the conversation is new). The caller commits."""
    if conversation_id is None:
        conversation_id = f"ASK-{state.next_number(s, COLLECTION, 'ASK-', 0)}"
    turns = [*turns, {"q": q, "a": a, "provider": provider, "at": iso_ms(clock.now())}][-MAX_TURNS:]
    state.put(s, COLLECTION, conversation_id, {"account": account_id, "turns": turns})
    return conversation_id
