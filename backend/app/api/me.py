"""Current user."""

from flask import g

from app.api import api_v1
from app.errors import ok
from app.security.authz import api_auth
from app.services import voter_service


@api_v1.get("/me")
@api_auth()
def me():
    return ok(voter_service.profile(g.user))
