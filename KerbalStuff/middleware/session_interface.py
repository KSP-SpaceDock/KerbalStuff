from typing import Union
from flask import session
from flask.sessions import SecureCookieSessionInterface
from flask_login import current_user

class OnlyLoggedInSessionInterface(SecureCookieSessionInterface):

    """Don't send session cookies for anonymous users"""
    def save_session(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if not current_user:
            # Tell client to delete the session cookie
            session.clear()
        return super().save_session(*args, **kwargs)
