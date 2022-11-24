from __future__ import annotations

import asyncio
import json
from typing import Dict, List

from aiohttp import web
from mautrix.types import RoomID, UserID

from ...commands import acd as cmd_acd
from ...commands import create as cmd_create
from ...commands import pm as cmd_pm
from ...commands import resolve as cmd_resolve
from ...commands import state_event as cmd_state_event
from ...commands import template as cmd_template
from ...commands import transfer as cmd_transfer
from ...commands import transfer_user as cmd_transfer_user
from ...commands.typehint import CommandEvent
from ...puppet import Puppet
from ...queue_membership import QueueMembership
from ...user import User
from ..base import (
    _resolve_puppet_identifier,
    _resolve_user_identifier,
    get_bulk_resolve,
    get_commands,
    get_config,
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

    fake_cmd_event = CommandEvent(
        sender=user, config=get_config(), command="create", is_management=True, args_list=args
    )

    puppet = await cmd_create(fake_cmd_event)

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
                        template_message:
                            type: string
                        template_name:
                            type: string
                        agent_id:
                            type: string
                    example:
                        customer_phone: "573123456789"
                        company_phone: "57398765432"
                        template_message: "Hola iKono!!"
                        template_name: "text"
                        agent_id: "@agente1:somewhere.com"

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

    if not (
        data.get("customer_phone")
        and data.get("template_message")
        and data.get("template_name")
        and (data.get("user_email") or data.get("company_phone") or data.get("user_id"))
        and data.get("agent_id")
    ):
        return web.json_response(**REQUIRED_VARIABLES)

    puppet = None

    if data.get("company_phone"):
        company_phone = data.get("company_phone").replace("+", "")
        puppet: Puppet = await Puppet.get_by_phone(company_phone)

    puppet = puppet or await _resolve_puppet_identifier(request=request)

    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    incoming_params = {
        "phone_number": data.get("customer_phone"),
        "template_message": data.get("template_message"),
        "template_name": data.get("template_name"),
    }

    data_cmd = f"{json.dumps(incoming_params)}"

    # Creating a fake command event and passing it to the command processor.

    try:

        fake_cmd_event = CommandEvent(
            sender=user,
            config=get_config(),
            command="pm",
            is_management=False,
            intent=puppet.intent,
            text=data_cmd,
            args_list=data_cmd.split(),
        )

        result = await cmd_pm(fake_cmd_event)

        return web.json_response(**result)
    except Exception as e:
        return web.json_response(status=500, data={"error": str(e)})


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
                        room_id: "!gKEsOPrixwrrMFCQCJ:foo.com"
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

    # Creating a fake command event and passing it to the command processor.

    fake_cmd_event = CommandEvent(
        sender=user,
        config=get_config(),
        command="resolve",
        is_management=False,
        intent=puppet.intent,
        args_list=args,
    )

    await cmd_resolve(fake_cmd_event)
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
                        room_id: "!gKEsOPrixwrrMFCQCJ:foo.com"
                        event_type: "ik.chat.tag"
                        tags: [
                                {
                                    "id":"soporte",
                                    "text":"soporte"
                                },
                                {
                                    "id":"ventas",
                                    "text":"ventas"
                                }
                            ]


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

    if not (data.get("room_id") and data.get("event_type")):
        return web.json_response(**REQUIRED_VARIABLES)

    incoming_params = {
        "room_id": data.get("room_id"),
        "event_type": data.get("event_type"),
    }

    # Si llega vacia la lista tags es porque se quieren limpiar los tags
    if data.get("tags") is not None:
        incoming_params["tags"] = data.get("tags")
    else:
        incoming_params["content"] = data.get("content")

    # Obtenemos el puppet de este email si existe
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=data.get("room_id"))
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    # Creating a fake command event and passing it to the command processor.

    text_incoming_params = f"{json.dumps(incoming_params)}"

    fake_cmd_event = CommandEvent(
        sender=user,
        config=get_config(),
        command="state_event",
        is_management=False,
        intent=puppet.intent,
        args_list=text_incoming_params.split(),
        text=text_incoming_params,
    )

    await cmd_state_event(fake_cmd_event)

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
                        template_name:
                            type: string
                        template_message:
                            type: string
                    example:
                        room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        template_name: "hola"
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

    if not (data.get("room_id") and data.get("template_name") and data.get("template_message")):
        return web.json_response(**REQUIRED_VARIABLES)

    incoming_params = {
        "room_id": data.get("room_id"),
        "template_name": data.get("template_name"),
        "template_message": data.get("template_message"),
    }

    # Obtenemos el puppet de este email si existe
    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=data.get("room_id"))
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    # Creating a fake command event and passing it to the command processor.

    text_incoming_params = f"{json.dumps(incoming_params)}"

    fake_cmd_event = CommandEvent(
        sender=user,
        config=get_config(),
        command="template",
        is_management=False,
        intent=puppet.intent,
        args_list=text_incoming_params.split(),
        text=text_incoming_params,
    )

    await cmd_template(fake_cmd_event)
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

    # Creating a fake command event and passing it to the command processor.
    fake_cmd_event = CommandEvent(
        sender=user,
        config=get_config(),
        command="transfer",
        is_management=False,
        intent=puppet.intent,
        args_list=args,
    )

    await cmd_transfer(fake_cmd_event)
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

    # Creating a fake command event and passing it to the command processor.
    fake_cmd_event = CommandEvent(
        sender=user,
        config=get_config(),
        command="transfer_user",
        is_management=False,
        intent=puppet.intent,
        args_list=args,
    )

    await cmd_transfer_user(fake_cmd_event)
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
        description: A json with `user_email`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        action:
                            type: string
                        name:
                            type: string
                    example:
                        action: "create"
                        name: "My favourite queue"
                        invitees: ["@agent1:foo.com", "@agent2:foo.com"]

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
        invitees: List = data.get("invitees")
        invitees: str = ",".join(invitees)

    args = [action, name, invitees]

    # Creating a fake command event and passing it to the command processor.
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

    # Creating a fake command event and passing it to the command processor.
    fake_cmd_event = CommandEvent(
        sender=user,
        config=get_config(),
        command="acd",
        is_management=False,
        intent=puppet.intent,
        args_list=args,
    )

    await cmd_acd(fake_cmd_event)
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
