from __future__ import annotations

import logging
from typing import Dict

from aiohttp import web

from ...puppet import Puppet
from ...user import User, UserRoles
from ...util import Util
from ..base import _resolve_user_identifier, routes
from ..error_responses import (
    INVALID_DESTINATION,
    INVALID_EMAIL,
    INVALID_ROOM_ID,
    INVALID_USER_ID,
    INVALID_USER_ROLE,
    NOT_DATA,
    PUPPET_DOESNOT_EXIST,
    REQUIRED_VARIABLES,
    USER_DOESNOT_EXIST,
)

logger = logging.getLogger()


@routes.get("/v1/get_control_room", allow_head=False)
async def get_control_room(request: web.Request) -> web.Response:
    """
    ---
    summary:        Given a room obtains the acd control room*.
    tags:
        - Mis

    parameters:
    - in: query
      name: room_id
      schema:
        type: string
      required: false
      description: room
    - in: query
      name: company_phone
      schema:
       type: string
      required: false
      description: company phone

    responses:
        '200':
            $ref: '#/components/responses/ControlRoomFound'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    room_id = None
    company_phone = None
    try:
        room_id = request.rel_url.query["room_id"]
    except KeyError:
        try:
            company_phone = request.rel_url.query["company_phone"]
        except KeyError:
            return web.json_response(**REQUIRED_VARIABLES)

    if room_id:
        puppet: Puppet = await Puppet.get_by_portal(portal_room_id=room_id)
    else:
        puppet: Puppet = await Puppet.get_by_phone(company_phone)

    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    data = {
        "control_room_id": puppet.control_room_id,
        "company_phone": puppet.phone,
        "user_id": puppet.mxid,
    }
    return web.json_response(data=data)


@routes.get("/v1/get_control_rooms", allow_head=False)
async def get_control_rooms() -> web.Response:
    """
    ---
    summary:        Get the acd control rooms.
    tags:
        - Mis

    responses:
        '200':
            $ref: '#/components/responses/ControlRooms'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotFound'
    """

    control_room_ids = await Puppet.get_control_room_ids()

    if not control_room_ids:
        return web.json_response(**NOT_DATA)

    return web.json_response(data={"control_room_ids": control_room_ids})


@routes.get("/v1/user/{role}", allow_head=False)
async def get_users_by_role(request: web.Request) -> web.Response:
    """
    ---
    summary:        Get users by role.
    tags:
        - Mis

    responses:
        '200':
            $ref: '#/components/responses/UsersByRole'
        '404':
            $ref: '#/components/responses/NotFound'
    """
    await _resolve_user_identifier(request=request)

    role = request.match_info.get("role", "")

    if not role in UserRoles.__members__:
        return web.json_response(**INVALID_USER_ROLE)

    users = await User.get_users_by_role(role=role)
    return web.json_response(data={"users": users})


@routes.get("/v1/puppet/{puppet_mxid}", allow_head=False)
async def get_puppet(request: web.Request) -> web.Response:
    """
    ---
    summary:        Get puppet information.
    tags:
        - Mis

    responses:
        '200':
            $ref: '#/components/responses/GetPuppetInfoSuccess'
        '404':
            $ref: '#/components/responses/NotFound'
    """
    await _resolve_user_identifier(request=request)

    puppet_mxid = request.match_info.get("puppet_mxid", "")
    puppet: Dict = await Puppet.get_info_by_custom_mxid(puppet_mxid)
    if not puppet:
        return web.json_response(**PUPPET_DOESNOT_EXIST)

    return web.json_response(data=puppet)


@routes.patch("/v1/puppet/{puppet_mxid}")
async def update_puppet(request: web.Request) -> web.Response:
    """
    ---
    summary:    Update puppet information
    tags:
        - Mis

    requestBody:
        required: false
        description: A json with `destination`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        destination:
                            type: string
                        email:
                            type: string
                        phone:
                            type: string
                    example:
                        destination: "!foo:foo.com | @agent1:foo.com | @menubot1:foo.com"
                        email: "sample@foo.com"
                        phone: "573106978412"

    responses:
        '200':
            $ref: '#/components/responses/GetPuppetInfoSuccess'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotFound'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not Util.is_room_id(data.get("destination")) and not Util.is_user_id(
        data.get("destination")
    ):
        return web.json_response(**INVALID_DESTINATION)

    puppet_mxid = request.match_info.get("puppet_mxid", "")
    if not Util.is_user_id(puppet_mxid):
        return web.json_response(**INVALID_USER_ID)

    puppet: Puppet = await Puppet.get_puppet_by_mxid(puppet_mxid, create=False)
    if not puppet:
        return web.json_response(**PUPPET_DOESNOT_EXIST)

    _utils = Util(config=puppet.config)
    if data.get("email") and not _utils.is_email(email=data.get("email")):
        return web.json_response(**INVALID_EMAIL)

    destination = data.get("destination")

    if Util.is_user_id(destination):
        user: User = await User.get_by_mxid(destination, create=False)
        # Check if the new destination is a menubot and
        # if it's different from the current puppet destination.
        # If the conditions are fulfilled,
        # it kicks the current menubot from the control room and invites the new one.
        if user and user.is_menubot and puppet.destination != destination:
            current_menubot = await puppet.menubot_id
            if current_menubot:
                await puppet.intent.kick_user(puppet.control_room_id, current_menubot)
            await puppet.intent.invite_user(puppet.control_room_id, destination)

    puppet.destination = destination or puppet.destination
    puppet.email = data.get("email") or puppet.email
    puppet.phone = data.get("phone") or puppet.phone
    await puppet.save()

    updated_puppet = await Puppet.get_info_by_custom_mxid(puppet_mxid)
    return web.json_response(data=updated_puppet)


@routes.patch("/v1/room_name")
async def update_room_name(request: web.Request) -> web.Response:
    """
    ---
    summary:    Update the name of rooms
    tags:
        - Mis

    requestBody:
        required: false
        description: A json with `room_name`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_name:
                            type: string
                        room_id:
                            type: string
                    example:
                        room_name: John Doe | Joaquin Andrés | Pablo Emilio | {1-9, a-z, A-Z}

    responses:
        '200':
            $ref: '#/components/responses/UpdateRoomNameSuccess'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotFound'
    """
    # await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not Util.is_room_id(data.get("room_id")) and not Util.is_user_id(data.get("room_id")):
        return web.json_response(**INVALID_ROOM_ID)

    logger.debug("**************************** 1")

    puppet: Puppet = await Puppet.get_by_control_room_id(control_room_id=data.get("room_id"))
    if not puppet:
        return web.json_response(**PUPPET_DOESNOT_EXIST)

    logger.debug("**************************** 2")
    logger.debug(f"############################# {puppet=}")

    # logger.debug(f"**************************** {puppet=}")

    # puppet_mxid = data.get("puppet_mxid")
