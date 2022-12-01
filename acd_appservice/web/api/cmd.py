from __future__ import annotations

import asyncio
from typing import Dict, List

from aiohttp import web
from mautrix.types import RoomID, UserID

from ...puppet import Puppet
from ...queue_membership import QueueMembership
from ...user import User
from ..base import (
    _resolve_puppet_identifier,
    _resolve_user_identifier,
    get_bulk_resolve,
    get_commands,
    routes,
)
from ..error_responses import (
    AGENT_DOESNOT_HAVE_QUEUES,
    BRIDGE_INVALID,
    INVALID_ACTION,
    NOT_DATA,
    REQUIRED_VARIABLES,
    SERVER_ERROR,
    USER_DOESNOT_EXIST,
)


@routes.post("/v1/cmd/create")
async def create(request: web.Request) -> web.Response:
    """
    Receives a user_email and creates a user in the User table and its respective puppet
    ---
    summary: Creates a user in the platform to be able to scan the WhatsApp QR code and send messages later using the API endpoints.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
          application/json:
            schema:
              type: object
              properties:
                user_email:
                  type: string
                user_id:
                  type: string
              example:
                  user_email: "@acd1:somewhere.com"
                  control_room_id: "!foo:somewhere.com"
                  destination: "nobody@somewhere.com"
                  bridge: "mautrix"
    responses:
        '201':
            $ref: '#/components/responses/UserCreated'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/ErrorData'
    """

    user = await _resolve_user_identifier(request=request)

    args = []
    email = ""

    if request.body_exists:
        data = await request.json()
        if data.get("bridge"):
            args.append(data.get("bridge"))

        if data.get("destination"):
            args.append(data.get("destination"))

        if data.get("control_room_id"):
            args.append(data.get("control_room_id"))

        email = data.get("user_email")

    puppet = await get_commands().handle(
        sender=user,
        command="create",
        args_list=args,
        is_management=True,
    )

    if email:
        puppet.email = email
        await puppet.save()

    if puppet:
        response = {
            "user_id": puppet.custom_mxid,
            "control_room_id": puppet.control_room_id,
            "email": puppet.email,
        }

        return web.json_response(response, status=201)
    else:
        return web.json_response(**SERVER_ERROR)


@routes.post("/v1/cmd/pm")
async def pm(request: web.Request) -> web.Response:
    """
    Command that allows send a message to a customer.
    ---
    summary:    It takes a phone number and a message,
                and sends the message to the phone number.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_phone:
                            type: string
                        company_phone:
                            type: string
                        template_message:
                            type: string
                    example:
                        customer_phone: "573123456789"
                        company_phone: "57398765432"
                        template_message: "Hola iKono!!"

    responses:
        '200':
            $ref: '#/components/responses/PmSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '422':
            $ref: '#/components/responses/NotSendMessage'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    phone = data.get("customer_phone")
    message = data.get("template_message")

    if not (phone and message):
        return web.json_response(**REQUIRED_VARIABLES)

    puppet = await _resolve_puppet_identifier(request=request)

    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [phone, message]

    result = await get_commands().handle(
        sender=user,
        command="pm",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
    )

    return web.json_response(**result)


@routes.post("/v1/cmd/resolve")
async def resolve(request: web.Request) -> web.Response:
    """
    ---
    summary: Command resolving a chat, ejecting the supervisor and the agent.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            type: string
                        user_id:
                            type: string
                        send_message:
                            type: string
                    example:
                        room_id: "!foo:foo.com"
                        user_id: "@acd_1:foo.com"
                        send_message: "yes"

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("room_id") and data.get("user_id")):
        return web.json_response(**REQUIRED_VARIABLES)

    room_id = data.get("room_id")
    user_id = data.get("user_id")
    send_message = data.get("send_message") if data.get("send_message") else None

    # Obtenemos el puppet de este email si existe
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)

    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    bridge = await puppet.room_manager.get_room_bridge(room_id=room_id)

    if not bridge:
        return web.json_response(**BRIDGE_INVALID)

    args = [room_id, user_id, send_message, puppet.config[f"bridges.{bridge}.prefix"]]

    await get_commands().handle(
        sender=user,
        command="resolve",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
    )
    return web.json_response()


@routes.post("/v1/cmd/bulk_resolve")
async def bulk_resolve(request: web.Request) -> web.Response:
    """
    ---
    summary: Command to resolve chats en bloc, expelling the supervisor and the agent.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                        user_id:
                            type: string
                        send_message:
                            type: string
                    example:
                        "room_ids": [
                            "!GmkrVrscIseYrhpTSz:foo.com",
                            "!dsardsfasddcshpTSz:foo.com",
                            "!GmkrVrssetrhtrsdfz:foo.com",
                            "!GnjyuikfdvdfrhpTSz:foo.com"
                            ]
                        "user_id": "@supervisor:foo.com"
                        "send_message": "no"


    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("room_ids") and data.get("user_id")):
        return web.json_response(**REQUIRED_VARIABLES)

    room_ids: List[RoomID] = data.get("room_ids")
    user_id = data.get("user_id")
    send_message = data.get("send_message")

    asyncio.create_task(
        get_bulk_resolve().resolve(
            new_room_ids=room_ids, user=user, user_id=user_id, send_message=send_message
        )
    )

    return web.json_response(text="ok")


@routes.post("/v1/cmd/state_event")
async def state_event(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that sends a state event to matrix.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            type: string
                        event_type:
                            type: string
                    example:
                        room_id: "!foo:foo.com"
                        event_type: "m.custom.event"
                        content: {
                                    "tags": ["tag1", "tag2", "tag3"]
                                }

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    room_id = data.get("room_id")
    event_type = data.get("event_type")
    content = data.get("room_id")

    if not (room_id and event_type):
        return web.json_response(**REQUIRED_VARIABLES)

    # Obtenemos el puppet de este email si existe
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [room_id, event_type, content]

    await get_commands().handle(
        sender=user,
        command="state_event",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
    )

    return web.json_response()


@routes.post("/v1/cmd/template")
async def template(request: web.Request) -> web.Response:
    """
    ---
    summary: This command is used to send templates
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            type: string
                        template_message:
                            type: string
                    example:
                        room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        template_message: "Hola iKono!!"

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()
    room_id = data.get("room_id")
    template_message = data.get("template_message")

    if not (room_id and template_message):
        return web.json_response(**REQUIRED_VARIABLES)

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [room_id, template_message]

    await get_commands().handle(
        sender=user, command="template", args_list=args, intent=puppet.intent, is_management=False
    )
    return web.json_response()


@routes.post("/v1/cmd/transfer")
async def transfer(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that transfers a client to an campaign_room.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_room_id:
                            type: string
                        campaign_room_id:
                            type: string
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        campaign_room_id: "!TXMsaIzbeURlKPeCxJ:foo.com"

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("customer_room_id") and data.get("campaign_room_id")):
        return web.json_response(**REQUIRED_VARIABLES)

    customer_room_id = data.get("customer_room_id")
    campaign_room_id = data.get("campaign_room_id")

    # Obtenemos el puppet de este email si existe
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=customer_room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [customer_room_id, campaign_room_id]

    await get_commands().handle(
        sender=user, command="transfer", args_list=args, intent=puppet.intent, is_management=False
    )

    return web.json_response()


@routes.post("/v1/cmd/transfer_user")
async def transfer_user(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that transfers a client from one agent to another.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_room_id:
                            type: string
                        target_agent_id:
                            type: string
                        force:
                            type: string
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        target_agent_id: "@agente1:foo.com"
                        force: "yes"

    responses:
        '200':
            $ref: '#/components/responses/PmSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("customer_room_id") and data.get("target_agent_id")):
        return web.json_response(**REQUIRED_VARIABLES)

    customer_room_id = data.get("customer_room_id")
    target_agent_id = data.get("target_agent_id")

    # Obtenemos el puppet de este email si existe
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=customer_room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [customer_room_id, target_agent_id]
    if data.get("force"):
        args.append(data.get("force"))

    await get_commands().handle(
        sender=user,
        command="transfer_user",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
    )
    return web.json_response()


@routes.post("/v1/cmd/queue")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that create a queue. A queue is a matrix room containing agents that will
                be used for chat distribution. `invitees` is a comma-separated list of user_ids.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `action`, `name`, `invitees` and optional `description`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        action:
                            type: string
                        name:
                            type: string
                        invitees:
                            type: array
                            items:
                                type: string
                        description:
                            type: string
                    example:
                        action: "create"
                        name: "My favourite queue"
                        invitees: ["@agent1:foo.com", "@agent2:foo.com"]
                        description: "It is a queue to distribute chats"

    responses:
        '200':
            $ref: '#/components/responses/QueueSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("name") and data.get("action")):
        return web.json_response(**REQUIRED_VARIABLES)

    action = data.get("action")
    name = data.get("name")

    invitees = None

    if data.get("invitees"):
        invitees: str = ",".join(data.get("invitees"))

    description: str = data.get("description") if data.get("description") else ""

    args = [action, name, invitees, description]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(
        data=result, status=result.get("status") if result.get("status") == 500 else 200
    )


@routes.post("/v1/cmd/acd")
async def acd(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that allows to distribute the chat of a client.

    description: Command that allows to distribute the chat of a client, optionally a campaign room and a joining message can be given.

    tags:
        - Commands

    requestBody:
        required: true
        description: A JSON with `customer_room_id`, `campaign_room_id` and `joined_message`. The customer_room_id is required.
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_room_id:
                            type: string
                        campaign_room_id:
                            type: string
                        joined_message:
                            type: string
                    required:
                        - customer_room_id
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:example.com"
                        campaign_room_id: "!TXMsaIzbeURlKPeCxJ:example.com"
                        joined_message: "{agentname} has joined the chat."

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '422':
            $ref: '#/components/responses/RequiredVariables'
    """

    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not data.get("customer_room_id"):
        return web.json_response(**REQUIRED_VARIABLES)

    customer_room_id = data.get("customer_room_id")
    campaign_room_id = data.get("campaign_room_id") or ""
    joined_message = data.get("joined_message") or ""

    # Get the puppet from customer_room_id if exists
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=customer_room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [customer_room_id, campaign_room_id, joined_message]

    await get_commands().handle(
        sender=user, command="acd", args_list=args, intent=puppet.intent, is_management=False
    )

    return web.json_response()


@routes.post("/v1/cmd/member")
async def member(request: web.Request) -> web.Response:
    """
    ---
    summary: Agent operations like login, logout, pause, unpause

    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `action`, `agent` and optional `list of queues`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        action:
                            type: string
                        agent:
                            type: string
                        queues:
                            type: array
                            items:
                                type: string
                    example:
                        action: login | logout | pause | unpuase
                        agent: "@agent1:localhost"
                        queues: ["@sdkjfkyasdvbcnnskf:localhost", "@sdkjfkyasdvbcnnskf:localhost"]

    responses:
        '200':
            $ref: '#/components/responses/AgentOperationSuccess'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/RequiredVariables'
    """

    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not data.get("action") or not data.get("agent"):
        return web.json_response(**REQUIRED_VARIABLES)

    actions = ["login", "logout", "pause", "unpause"]
    if not data.get("action") in actions:
        return web.json_response(**INVALID_ACTION)

    action: str = data.get("action")
    agent: UserID = data.get("agent")
    agent_user: User = await User.get_by_mxid(mxid=agent, create=False)
    queues: List[RoomID] = data.get("queues")

    # If queues are None get all rooms where agent is assigning
    if not data.get("queues"):
        queues = [
            membership.get("room_id")
            for membership in await QueueMembership.get_user_memberships(agent_user.id)
        ]

    if not queues:
        return web.json_response(**AGENT_DOESNOT_HAVE_QUEUES)

    args = [action, agent]
    action_responses = []
    status = 200
    for queue in queues:
        # Creating a fake command event and passing it to the command processor.
        response = await get_commands().handle(
            sender=user,
            command="member",
            args_list=args,
            intent=user.az.intent,
            is_management=False,
            room_id=queue,
        )
        # If the operation fails in at least one of the queues,
        # the endpoint returns the last error code
        if response.get("status") != 200:
            status = response.get("status")
        action_responses.append(response)

    return web.json_response(data={"agent_operation_responses": action_responses}, status=status)
