"""Maximo authentication for the mock (demo credentials, not secrets).

    apikey: circularity-demo-maximo-apikey        API key of the integration user MXINTADM (header, or ?apikey=)
    maxauth: base64("MXINTADM:circularity-demo-1") native Maximo authentication

The demo also lists mTLS; TLS client certificates are terminated before the mock and are not modelled here.
A failed login answers 401 with Maximo's BMXAA7901E error body.
"""

import base64
import binascii

from fastapi import Request

API_KEYS = {"circularity-demo-maximo-apikey": "MXINTADM"}
USERS = {"MXINTADM": "circularity-demo-1"}


def user_of(request: Request) -> str | None:
    """The Maximo user the request authenticates as, or None."""
    key = request.headers.get("apikey") or request.query_params.get("apikey")
    if key:
        return API_KEYS.get(key)
    raw = request.headers.get("maxauth")
    if raw:
        try:
            user, _, password = base64.b64decode(raw, validate=True).decode().partition(":")
        except (binascii.Error, UnicodeDecodeError):
            return None
        return user.upper() if USERS.get(user.upper()) == password else None
    return None
