import asyncio
import inspect
import re

from asgiref.sync import sync_to_async
from django.contrib.auth import get_backends, user_login_failed
from django.core.exceptions import PermissionDenied
from django.core.handlers.asgi import ASGIRequest
from django.views.decorators.debug import sensitive_variables

SENSITIVE_CREDENTIALS = re.compile("api|token|key|secret|password|signature", re.I)
CLEANSED_SUBSTITUTE = "********************"


@sensitive_variables("credentials")
def _clean_credentials(credentials):
    """
    Clean a dictionary of credentials of potentially sensitive info before sending to less secure functions.
    Not comprehensive - intended for user_login_failed signal
    """
    for key in credentials:
        if SENSITIVE_CREDENTIALS.search(key):
            credentials[key] = CLEANSED_SUBSTITUTE
    return credentials


@sensitive_variables("credentials")
async def authenticate(request=None, **credentials):
    """If the given credentials are valid, return a User object."""
    for backend in get_backends():
        backend_signature = inspect.signature(backend.authenticate)
        try:
            backend_signature.bind(request, **credentials)
        except TypeError:
            # This backend doesn't accept these credentials as arguments. Try the next one.
            continue
        try:
            if hasattr(backend, "authenticate_async"):
                user = await backend.authenticate_async(request, **credentials)
            elif asyncio.iscoroutinefunction(backend.authenticate):
                user = await backend.authenticate(request, **credentials)
            else:
                if isinstance(request, ASGIRequest):
                    user = await sync_to_async(backend.authenticate)(request, **credentials)
                else:
                    user = backend.authenticate(request, **credentials)
        except PermissionDenied:
            # This backend says to stop in our tracks - this user should not be allowed in at all.
            break
        if user is None:
            continue
        # Annotate the user object with the path of the backend.
        user.backend = f"{backend.__module__}.{backend.__class__.__qualname__}"
        return user

    # The credentials supplied are invalid to all backends, fire signal
    user_login_failed.send(
        sender=__name__, credentials=_clean_credentials(credentials), request=request
    )
    return None
