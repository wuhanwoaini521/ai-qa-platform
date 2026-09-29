"""Tiny in-memory system under test for the first executable examples."""

from dataclasses import dataclass


@dataclass(frozen=True)
class LoginResult:
    authenticated: bool
    destination: str


def login(username: str, password: str) -> LoginResult:
    """Return the route a demo user would see after a login attempt."""
    if username == "demo_user" and password == "demo_password":
        return LoginResult(authenticated=True, destination="/dashboard")
    return LoginResult(authenticated=False, destination="/login")
