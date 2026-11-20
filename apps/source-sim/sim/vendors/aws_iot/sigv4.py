"""AWS Signature Version 4, as the AWS IoT Core mock verifies it (docs/BACKEND_STEPS.md, B5c).

Documentation followed: https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html

    Authorization: AWS4-HMAC-SHA256 Credential=<access key>/<yyyymmdd>/<region>/<service>/aws4_request,
                   SignedHeaders=host;x-amz-date[;…], Signature=<hex>
    X-Amz-Date:    yyyymmddThhmmssZ (wall-clock UTC; more than 15 minutes off is refused, as AWS does)

The canonical request is METHOD, canonical URI, canonical query string, canonical headers, signed headers and the
hex SHA-256 of the body (or X-Amz-Content-Sha256 when sent). The string to sign is "AWS4-HMAC-SHA256", the date,
the credential scope and the hex SHA-256 of the canonical request; the key is HMAC("AWS4"+secret, date, region,
service, "aws4_request").
SIMPLIFIED (documented): the canonical URI is the request path as the mock receives it, including the mock's host
prefix (/aws-iot/iot or /aws-iot/data), URI-encoded once ('/' kept); real AWS signs the path on its own host and
encodes each segment twice. Presigned URLs (signature in the query string) and session tokens are not supported.
"""

import hashlib
import hmac
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote

ALGORITHM = "AWS4-HMAC-SHA256"
MAX_SKEW_SECONDS = 15 * 60
_AUTH = re.compile(r"^AWS4-HMAC-SHA256\s+Credential=([^,\s]+)\s*,\s*SignedHeaders=([^,\s]+)\s*,\s*Signature=([0-9a-f]+)\s*$")


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    k = _hmac(("AWS4" + secret).encode(), date)
    k = _hmac(k, region)
    k = _hmac(k, service)
    return _hmac(k, "aws4_request")


def canonical_uri(path: str) -> str:
    return quote(path, safe="/-_.~")


def canonical_query(pairs: list[tuple[str, str]]) -> str:
    enc = sorted((quote(k, safe="-_.~"), quote(v, safe="-_.~")) for k, v in pairs)
    return "&".join(f"{k}={v}" for k, v in enc)


def string_to_sign(
    method: str, path: str, query: list[tuple[str, str]], headers: dict[str, str], signed: list[str], payload_hash: str,
    amz_date: str, scope: str,
) -> str:  # fmt: skip
    canon_headers = "".join(f"{h}:{' '.join(headers.get(h, '').split())}\n" for h in signed)
    creq = "\n".join([method.upper(), canonical_uri(path), canonical_query(query), canon_headers, ";".join(signed), payload_hash])
    return "\n".join([ALGORITHM, amz_date, scope, hashlib.sha256(creq.encode()).hexdigest()])


def sign(
    method: str, path: str, query: list[tuple[str, str]], host: str, body: bytes, access_key: str, secret: str,
    region: str, service: str, now: datetime | None = None,
) -> dict[str, str]:  # fmt: skip
    """The headers a client adds to sign one request (used by the tests; di has its own copy of this)."""
    now = now or datetime.now(UTC)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = amz_date[:8]
    payload_hash = hashlib.sha256(body).hexdigest()
    headers = {"host": host, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash}
    signed = sorted(headers)
    scope = f"{date}/{region}/{service}/aws4_request"
    sts = string_to_sign(method, path, query, headers, signed, payload_hash, amz_date, scope)
    sig = hmac.new(signing_key(secret, date, region, service), sts.encode(), hashlib.sha256).hexdigest()
    return {
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": f"{ALGORITHM} Credential={access_key}/{scope}, SignedHeaders={';'.join(signed)}, Signature={sig}",
    }


class SigError(Exception):
    """A refused signature: `code` is the AWS error type (all HTTP 403)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def verify(
    method: str, path: str, raw_query: str, headers: dict[str, str], body: bytes, secrets: dict[str, str], region: str,
    service: str, now: datetime | None = None,
) -> str:  # fmt: skip
    """Check one request's SigV4 signature. Returns the access key id; raises SigError the way AWS refuses."""
    auth = headers.get("authorization", "")
    if not auth:
        raise SigError("MissingAuthenticationTokenException", "Missing Authentication Token")
    m = _AUTH.match(auth.strip())
    if not m:
        raise SigError(
            "IncompleteSignatureException",
            "Authorization header requires 'Credential', 'SignedHeaders' and 'Signature' parameters (AWS4-HMAC-SHA256).",
        )
    credential, signed_raw, signature = m.groups()
    parts = credential.split("/")
    if len(parts) != 5 or parts[4] != "aws4_request":
        raise SigError("IncompleteSignatureException", f"Credential should be scoped to a valid region. Got {credential}")
    key_id, date, cred_region, cred_service, _ = parts
    if key_id not in secrets:
        raise SigError("UnrecognizedClientException", "The security token included in the request is invalid.")
    if cred_region != region:
        raise SigError("InvalidSignatureException", f"Credential should be scoped to a valid region, not '{cred_region}'.")
    if cred_service != service:
        raise SigError("InvalidSignatureException", f"Credential should be scoped to correct service: '{service}'.")
    signed = signed_raw.split(";")
    if "host" not in signed or "x-amz-date" not in signed:
        raise SigError("IncompleteSignatureException", "SignedHeaders must include host and x-amz-date.")
    amz_date = headers.get("x-amz-date", "")
    try:
        at = datetime.strptime(amz_date, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError as e:
        raise SigError("IncompleteSignatureException", "Missing or malformed X-Amz-Date header.") from e
    if amz_date[:8] != date:
        raise SigError(
            "InvalidSignatureException",
            "Date in Credential scope does not match YYYYMMDD from ISO-8601 version of date from HTTP.",
        )
    now = now or datetime.now(UTC)
    if abs((now - at).total_seconds()) > MAX_SKEW_SECONDS:
        raise SigError(
            "InvalidSignatureException",
            f"Signature expired: {amz_date} is now earlier than {now.strftime('%Y%m%dT%H%M%SZ')} (15 min skew allowed).",
        )
    actual_hash = hashlib.sha256(body).hexdigest()
    sent_hash = headers.get("x-amz-content-sha256")
    if sent_hash and sent_hash not in (actual_hash, "UNSIGNED-PAYLOAD"):
        raise SigError(
            "InvalidSignatureException", "The provided 'x-amz-content-sha256' header does not match what was computed."
        )
    payload_hash = sent_hash or actual_hash
    query = parse_qsl(raw_query, keep_blank_values=True)
    scope = f"{date}/{region}/{service}/aws4_request"
    sts = string_to_sign(method, path, query, headers, signed, payload_hash, amz_date, scope)
    expected = hmac.new(signing_key(secrets[key_id], date, region, service), sts.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SigError(
            "InvalidSignatureException",
            "The request signature we calculated does not match the signature you provided. Check your AWS Secret "
            "Access Key and signing method. Consult the service documentation for details.",
        )
    return key_id
