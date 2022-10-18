from __future__ import annotations

from aiohttp import web

from acd_appservice.http_client import ProvisionBridge

from ...puppet import Puppet
from ..base import routes
from ..error_responses import NOT_DATA, REQUIRED_VARIABLES, USER_DOESNOT_EXIST


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
            $ref: '#/components/responses/NotExist'
    """

    control_room_ids = await Puppet.get_control_room_ids()

    if not control_room_ids:
        return web.json_response(**NOT_DATA)

    return web.json_response(data={"control_room_ids": control_room_ids})


@routes.post("/v1/get_bridges_status")
async def get_bridges_status(request: web.Request) -> web.Response:

    """
    ---
    summary:        Given a list of puppets, get his bridges status.
    tags:
        - Mis

    requestBody:
        required: true
        description: A json with `puppet_list`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        puppet_list:
                            type: array
                            items:
                                type: string
                    example:
                        puppet_list: ["@acd1:localhost", "@acd2:localhost"]


    responses:
        '200':
            $ref: '#/components/responses/BridgesStatus'
    """

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data = await request.json()

    bridges_status = []

    for puppet in data.get("puppet_list"):
        puppet: Puppet = await Puppet.get_puppet_by_mxid(customer_mxid=puppet, create=False)

        if not puppet:
            continue

        bridge_conector = ProvisionBridge(
            config=puppet.config, session=puppet.intent.api.session, bridge=puppet.bridge
        )
        status = await bridge_conector.mautrix_ping(puppet.mxid)
        bridges_status.append(status)

    return web.json_response(data={"bridges_status": bridges_status})
