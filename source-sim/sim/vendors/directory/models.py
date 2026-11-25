"""State of the directory mock: users, groups and the short-lived codes and tokens, all in memory.

Owns: the dataclasses and the one `STATE` that `seed.py` fills and `routes.py` reads. Never does: touch Postgres (a
restart or `reset` brings back the seed), sign anything, or log a code or token. Nothing here is a real identity.
"""

from dataclasses import dataclass, field

CODE_TTL = 60.0  # seconds an authorization code lives
TOKEN_TTL = 3600  # seconds an access token and an ID token live


@dataclass
class User:
    id: str
    email: str
    name: str
    groups: list[str] = field(default_factory=list)


@dataclass
class AuthCode:
    user_id: str
    client_id: str
    redirect_uri: str
    challenge: str
    nonce: str | None
    expires: float


@dataclass
class State:
    users: dict[str, User] = field(default_factory=dict)  # active users, in insertion order
    pending: dict[str, User] = field(default_factory=dict)  # joiners-to-be, by email: not active until added
    codes: dict[str, AuthCode] = field(default_factory=dict)
    tokens: dict[str, tuple[str, float]] = field(default_factory=dict)  # access token -> (user id, expiry)


STATE = State()
