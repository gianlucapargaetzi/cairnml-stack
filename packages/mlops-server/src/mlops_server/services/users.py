from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.ids import new_id
from mlops_server.models import User
from mlops_server.security.oidc import IdpIdentity


def upsert_user(session: Session, identity: IdpIdentity) -> User:
    user = session.scalar(select(User).where(User.idp_subject == identity.subject))
    if user is None:
        user = User(id=new_id("usr"), idp_subject=identity.subject, username=identity.username,
                    roles=list(identity.roles))
        session.add(user)
    else:
        user.username = identity.username
        user.roles = list(identity.roles)
    return user
