from __future__ import annotations

from typing import Dict

from aiohttp import web

from ...db.user import User, UserRoles
from ...puppet import Puppet
from ..base import routes
from ..error_responses import (
    INVALID_USER_ROLE,
    NOT_DATA,
    PUPPET_DOESNOT_EXIST,
    REQUIRED_VARIABLES,
    USER_DOESNOT_EXIST,
)


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
        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
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
            $ref: '#/components/responses/ControlRoomFound'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotFound'
    """

    control_room_ids = await Puppet.get_control_room_ids()

    if not control_room_ids:
        return web.json_response(**NOT_DATA)

    return web.json_response(data={"control_room_ids": control_room_ids})


@routes.get("/v1/get_users/{user_role}", allow_head=False)
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

    user_role = request.match_info.get("user_role", "")
    if not user_role.upper() in UserRoles.__members__:
        return web.json_response(**INVALID_USER_ROLE)

    users = await User.get_users_by_role(role=user_role.lower())
    return web.json_response(data={"users": users})


@routes.get("/v1/get_puppet/{puppet_mxid}", allow_head=False)
async def get_puppet(request: web.Request) -> web.Response:
    """
    ---
    summary:        Get users by role.
    tags:
        - Mis

    responses:
        '200':
            $ref: '#/components/responses/GetPuppetInfoSuccess'
        '404':
            $ref: '#/components/responses/NotFound'
    """
    puppet_mxid = request.match_info.get("puppet_mxid", "")
    puppet: Dict = await Puppet.get_info_by_custom_mxid(puppet_mxid)
    if not puppet:
        return web.json_response(**PUPPET_DOESNOT_EXIST)

    return web.json_response(data=puppet)


@routes.patch("/v1/set_destionation/{puppet_mxid}")
async def set_destionation(request: web.Request) -> web.Response:
    """
    ---
    summary:    Set puppet destination
    tags:
        - Mis

    requestBody:
        required: true
        description: A json with `destination`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        destination:
                            type: string
                    example:
                        destination: "!foo:foo.com | @agent1:foo.com | @menubot1:foo.com"

    responses:
        '200':
            $ref: '#/components/responses/GetPuppetInfoSuccess'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotFound'
    """

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    puppet_mxid = request.match_info.get("puppet_mxid", "")
    puppet: Puppet = await Puppet.get_puppet_by_mxid(puppet_mxid, create=False)
    if not puppet:
        return web.json_response(**PUPPET_DOESNOT_EXIST)

    puppet.destination = data.get("destination")
    await puppet.save()

    updated_puppet = await Puppet.get_info_by_custom_mxid(puppet_mxid)
    return web.json_response(data=updated_puppet)
