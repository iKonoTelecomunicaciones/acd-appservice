from typing import Dict

from aiohttp import web

from acd_appservice.portal import Portal
from acd_appservice.user import User
from acd_appservice.util.util import Util

from ...puppet import Puppet
from ..base import _resolve_user_identifier, get_commands, routes
from ..error_responses import (
    NO_PUPPET_IN_PORTAL,
    NOT_DATA,
    PORTAL_DOESNOT_EXIST,
    REQUIRED_VARIABLES,
)


@routes.post("/v2/cmd/transfer")
async def transfer(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that transfers a client to a campaign_room or from one agent to another.
    tags:
        - Commands v2

    parameters:
    - in: header
      name: Authorization
      description: User that makes the request
      required: true
      schema:
        type: string
      example: Mxid @user:example.com

    requestBody:
        required: false
        description: A json with `user_email` or `customer_room_id`, `target_agent_id`, `force`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_room_id:
                            description: "The room that will be transferred"
                            type: string
                        destination:
                            description: "Target queue or the user to execute the transfer"
                            type: string
                        force:
                            description: "Do you want to force the transfer,
                                          no matter that the agent will be logged out?"
                            type: string
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        destination: "!TXMsaIzbeURlKPeCxJ:foo.com"
                        force: "yes"

    responses:
        '200':
            $ref: '#/components/responses/TransferQueueInProcess'
        '202':
            $ref: '#/components/responses/TransferSuccessButAgentUnavailable'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'
        '422':
            $ref: '#/components/responses/PortalIsLocked'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not data.get("customer_room_id"):
        return web.json_response(**REQUIRED_VARIABLES)

    if not Util.is_room_alias(data.get("customer_room_id")):
        return web.json_response(**PORTAL_DOESNOT_EXIST)

    portal: Portal = await Portal.get_by_room_id(room_id=data.get("customer_room_id"))
    current_agent: User = await portal.get_current_agent()

    if not current_agent:
        return web.json_response(
            {
                "data": {"error": "There is no agent in this room."},
                "status": 400,
            }
        )

    if Util.is_room_id(data.get("destination")):
        customer_room_id = data.get("customer_room_id")
        campaign_room_id = data.get("destination")

        # Get puppet from this portal if exists
        puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
        if not puppet:
            return web.json_response(**NO_PUPPET_IN_PORTAL)

        args = ["-p", customer_room_id, "-q", campaign_room_id]

        cmd_response = await get_commands().handle(
            sender=user,
            command="transfer",
            args_list=args,
            intent=puppet.intent,
            is_management=False,
        )

        return web.json_response(**cmd_response)

    elif Util.is_user_id(data.get("destination")):
        customer_room_id = data.get("customer_room_id")
        target_agent_id = data.get("destination")
        force = data.get("force") if data.get("force") else "no"

        # Get puppet from this portal if exists
        puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
        if not puppet:
            return web.json_response(**NO_PUPPET_IN_PORTAL)

        args = ["-p", customer_room_id, "-a", target_agent_id, "-f", force]

        command_response = await get_commands().handle(
            sender=user,
            command="transfer_user",
            args_list=args,
            intent=puppet.intent,
            is_management=False,
        )
        return web.json_response(**command_response)

    else:
        return web.json_response(**REQUIRED_VARIABLES)
