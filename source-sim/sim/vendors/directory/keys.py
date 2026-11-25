"""RS256 signing for the directory mock: one RSA key pair per process and a compact JWS builder.

Owns: the key pair (generated at import, so every start has a new `kid`), `sign_jwt`, the JWKS document and the
RFC 7636 S256 transform. Never does: store a token, read a user, or log a token or key. No dependency beyond
`cryptography` (locked through asyncssh).
"""

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_NUMBERS = _KEY.public_key().public_numbers()


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _int(n: int) -> str:
    return b64url(n.to_bytes((n.bit_length() + 7) // 8, "big"))


KID = b64url(hashlib.sha256(_int(_NUMBERS.n).encode()).digest())[:16]


def jwks() -> dict[str, Any]:
    return {"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": KID, "n": _int(_NUMBERS.n), "e": _int(_NUMBERS.e)}]}


def sign_jwt(claims: dict[str, Any]) -> str:
    """A compact JWS, RS256: base64url(header).base64url(payload).base64url(signature)."""
    head = b64url(json.dumps({"alg": "RS256", "typ": "JWT", "kid": KID}, separators=(",", ":")).encode())
    body = b64url(json.dumps(claims, separators=(",", ":")).encode())
    sig = _KEY.sign(f"{head}.{body}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{head}.{body}.{b64url(sig)}"


def pkce_s256(verifier: str) -> str:
    return b64url(hashlib.sha256(verifier.encode()).digest())
