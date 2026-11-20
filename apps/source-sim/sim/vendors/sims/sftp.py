"""The partner's SFTP server (asyncssh), started inside source-sim by the mock's `startup` hook.

    host source-sim (localhost from the host), port 2222 (env SIMS_SFTP_PORT)
    user di-connector, password rcy-demo (password authentication only)
    host key: Ed25519, derived from a fixed seed so it is the same on every start (the connector pins it; HOST_KEY)
    chroot: the drop directory (drop.root()); the client sees /outbound
    SFTP only (no shell, exec or SCP) and read only: every write, create, rename, delete or attribute change is
    refused with SSH_FX_PERMISSION_DENIED, as on a partner's outbound share.
Faults (/_sim/faults, system rcy): `unavailable` and `error` refuse the login; `latency` delays it. `token_expired`
does not apply (password auth, as Basic auth over HTTP).
"""

import asyncio
import errno
import hashlib
import hmac
import logging
import os

import asyncssh
from asyncssh import sftp as S
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sim.vendors.sims import drop

log = logging.getLogger("sim.sims")
USER, PASSWORD = "di-connector", "rcy-demo"
_KEY_SEED = hashlib.sha256(b"Sims Lifecycle Services demo SFTP host key").digest()


def port() -> int:
    return int(os.environ.get("SIMS_SFTP_PORT", "2222"))


def host_key() -> asyncssh.SSHKey:
    pem = Ed25519PrivateKey.from_private_bytes(_KEY_SEED).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, serialization.NoEncryption()
    )
    return asyncssh.import_private_key(pem)


HOST_KEY = host_key().export_public_key("openssh").decode().split()[0:2]  # ["ssh-ed25519", "AAAA…"]


def _faults() -> list[dict]:
    from sim import faults
    from sim.db import engine

    with engine.connect() as conn:
        return faults.active(conn, "rcy")


class _Server(asyncssh.SSHServer):
    def begin_auth(self, username: str) -> bool:  # noqa: ARG002 - asyncssh's server interface
        return True

    def password_auth_supported(self) -> bool:
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        try:
            active = await asyncio.to_thread(_faults)
        except Exception:  # noqa: BLE001 - no database: no faults
            active = []
        for f in active:
            if f["kind"] == "latency":
                await asyncio.sleep((f.get("value") or 0) / 1000)
            elif f["kind"] in ("unavailable", "error"):
                return False
        return username == USER and hmac.compare_digest(password.encode(), PASSWORD.encode())


def _denied(*_args, **_kw):
    raise asyncssh.SFTPPermissionDenied("Read-only partner drop")


class ReadOnlySFTP(asyncssh.SFTPServer):
    """The drop, chrooted and read only."""

    WRITE_FLAGS = S.FXF_WRITE | S.FXF_APPEND | S.FXF_CREAT | S.FXF_TRUNC | S.FXF_EXCL

    def __init__(self, chan):
        super().__init__(chan, chroot=str(drop.root()).encode())

    def open(self, path, pflags, attrs):
        if pflags & self.WRITE_FLAGS:
            _denied()
        return super().open(path, pflags, attrs)

    def open56(self, path, desired_access, flags, attrs):
        write = S.ACE4_WRITE_DATA | S.ACE4_APPEND_DATA | S.ACE4_WRITE_ATTRIBUTES
        if desired_access & write or (flags & S.FXF_ACCESS_DISPOSITION) != S.FXF_OPEN_EXISTING:
            _denied()
        return super().open56(path, desired_access, flags, attrs)

    setstat = lsetstat = fsetstat = remove = rename = posix_rename = mkdir = rmdir = symlink = link = _denied


class _NotStarted:
    def close(self) -> None:
        pass


async def serve(port_: int | None = None, host: str = "") -> asyncssh.SSHAcceptor:
    """Listen for SFTP clients (port 0: any free port; the acceptor's get_port() tells which)."""
    drop.outbound().mkdir(parents=True, exist_ok=True)
    return await asyncssh.listen(
        host,
        port() if port_ is None else port_,
        server_host_keys=[host_key()],
        server_factory=_Server,
        sftp_factory=ReadOnlySFTP,
        allow_scp=False,
        reuse_address=True,
        login_timeout=30,
    )


async def startup():
    """The Mock startup hook. Another process in this container may already serve the port (a test run, or the old
    process during a reload): the service retries for a few seconds, a test process (no background loops) does not."""
    from sim.config import get_settings

    tries = 10 if get_settings().background else 1
    for i in range(tries):
        try:
            server = await serve()
            log.info("Sims SFTP server listening on port %s", port())
            return server
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
            if i + 1 < tries:
                await asyncio.sleep(0.5)
    log.info("Sims SFTP port %s is already served by another process", port())
    return _NotStarted()
