"""Teamcenter sessions for the mock (demo credentials, not secrets).

    user di_connector / password Circularity-demo-tc-1   group Engineering, role Designer (the integration user)
    user infodba      / password infodba                 group dba, role DBA (the default administrator)

Core-2011-06-Session/login opens a session and the web tier returns it in the JSESSIONID cookie; every later call
sends the cookie. A session ends on logout or after 30 minutes without a call.
"""

import secrets
import time
from dataclasses import dataclass

USERS = {
    "di_connector": ("Circularity-demo-tc-1", "Engineering", "Designer"),
    "infodba": ("infodba", "dba", "DBA"),
}
IDLE_SECONDS = 30 * 60


@dataclass
class Session:
    user: str
    group: str
    role: str
    discriminator: str
    seen: float


SESSIONS: dict[str, Session] = {}


def login(user: str, password: str, group: str, role: str, discriminator: str) -> str | None:
    known = USERS.get(user)
    if known is None or known[0] != password:
        return None
    if group and group != known[1]:
        return None
    sid = secrets.token_hex(16).upper()
    SESSIONS[sid] = Session(user, group or known[1], role or known[2], discriminator, time.time())
    return sid


def session_user(sid: str) -> str | None:
    s = SESSIONS.get(sid)
    if s is None or time.time() - s.seen > IDLE_SECONDS:
        SESSIONS.pop(sid, None)
        return None
    s.seen = time.time()
    return s.user
