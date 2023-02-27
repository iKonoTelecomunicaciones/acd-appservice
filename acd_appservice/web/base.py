from __future__ import annotations

from aiohttp import web

from ..commands.handler import CommandProcessor
from ..commands.resolve import BulkResolve
from ..config import Config
from ..puppet import Puppet
from ..user import User
from ..util import Util
from .error_responses import INVALID_EMAIL

_config: Config | None = None
_util: Util | None = None
_commands: CommandProcessor | None = None
_bulk_resolve: BulkResolve | None = None

routes: web.RouteTableDef = web.RouteTableDef()


def set_config(config: Config, bulk_resolve: BulkResolve) -> None:
    global _config
    global _util
    global _commands
    global _bulk_resolve

    _util = Util(config=config)
    _config = config
    _commands = CommandProcessor(config=config)
    _bulk_resolve = bulk_resolve
    bulk_resolve.commands = _commands


def get_commands() -> CommandProcessor:
    return _commands


def get_bulk_resolve() -> BulkResolve:
    return _bulk_resolve


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

    if data.get("company_phone"):
        puppet = await Puppet.get_by_phone(data.get("company_phone"))

    puppet_mxid = request.rel_url.query.get("user_email") or data.get("user_email")

    if puppet_mxid:
        if _util.is_email(email=puppet_mxid):
            puppet = await Puppet.get_by_email(puppet_mxid)
        else:
            raise web.json_response(**INVALID_EMAIL)

    if request.rel_url.query.get("user_id") or data.get("user_id"):
        puppet = await Puppet.get_by_custom_mxid(
            request.rel_url.query.get("user_id") or data.get("user_id")
        )

    if not puppet:
        raise web.HTTPBadRequest(text='{"error": "Invalid Authorization"}')

    return puppet
