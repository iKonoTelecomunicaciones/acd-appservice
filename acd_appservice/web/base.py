from __future__ import annotations

from aiohttp import web

from ..config import Config
from ..puppet import Puppet
from ..user import User
from ..util import Util
from .error_responses import INVALID_EMAIL

_config: Config | None = None
_util: Util | None = None

routes: web.RouteTableDef = web.RouteTableDef()

base_path_doc = "acd_appservice/web/api"


def set_config(config: Config) -> None:
    global _config
    global _util
    _util = Util(config=config)
    _config = config


def get_config() -> Config:
    return _config


async def _resolve_user_identifier(request: web.Request) -> User | None:
    """This function takes a request object, and returns a user object if the user_id is valid,
    otherwise it returns None

    Parameters
    ----------
    request : web.Request
        web.Request

    Returns
    -------
        A user object

    """

    try:
        authorization: str = request.headers["Authorization"]
        user_request = authorization.split(" ")[1]
    except KeyError:
        raise web.HTTPUnauthorized(
            text='{"error": "You must specify the mxid of the user making the request in headers"}'
        )

    user: User = await User.get_by_mxid(user_request)

    if not user:
        raise web.HTTPUnauthorized(text='{"error": "Invalid authentication"}')

    return user


async def _resolve_puppet_identifier(request: web.Request) -> Puppet | None:
    """It takes a request, and returns a puppet if the request is valid

    Parameters
    ----------
    request : web.Request
        web.Request

    Returns
    -------
        A puppet object

    """

    data = {}
    if request.body_exists:
        data = await request.json()

    puppet_mxid: str = (
        request.rel_url.query.get("user_email")
        or request.rel_url.query.get("user_id")
        or data.get("user_email")
        or data.get("user_id")
    )

    if not puppet_mxid:
        raise web.HTTPBadRequest(text='{"error": "Invalid Authorization"}')

    puppet_mxid = puppet_mxid.lower().strip()

    puppet = await Puppet.get_by_custom_mxid(puppet_mxid)

    # Checking if the received puppet identifier is an email address.
    # If it is, it will get the puppet by email.
    # If not, it will raise an error.
    if not puppet:
        if _util.is_email(email=puppet_mxid):
            puppet = await Puppet.get_by_email(puppet_mxid)
        else:
            raise web.HTTPNotAcceptable(text=f"{INVALID_EMAIL}")

    if not puppet:
        raise web.HTTPBadRequest(text="{'error': 'User doesn't exist'}")

    return puppet
