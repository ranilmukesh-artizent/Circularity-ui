"""Request bodies of the sign-in and access endpoints (di.routes.auth)."""

from pydantic import BaseModel


class Login(BaseModel):
    username: str
    password: str


class DelegationIn(BaseModel):
    enabled: bool
