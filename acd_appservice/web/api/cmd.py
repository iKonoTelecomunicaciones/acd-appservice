from __future__ import annotations

import asyncio
import json
from typing import Dict, List

from aiohttp import web
from mautrix.types import RoomID, UserID

from ...portal import Portal
from ...puppet import Puppet
from ...queue import Queue
from ...queue_membership import QueueMembership
from ...user import User
from ...util import Util
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
    INVALID_USER_ID,
    NOT_DATA,
    QUEUE_DOESNOT_EXIST,
    QUEUE_MEMBERSHIP_DOESNOT_EXIST,
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
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=room_id)
    portal: Portal = await Portal.get_by_room_id(
        room_id=room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )

    if not puppet or not portal:
        return web.json_response(**USER_DOESNOT_EXIST)

    bridge = portal.bridge

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
    content = data.get("content")

    if not (room_id and event_type):
        return web.json_response(**REQUIRED_VARIABLES)

    # Obtenemos el puppet de este email si existe
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [room_id, event_type, json.dumps(content)]

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

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=room_id)
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
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
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
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [customer_room_id, target_agent_id]
    if data.get("force"):
        args.append(data.get("force"))

    command_response = await get_commands().handle(
        sender=user,
        command="transfer_user",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
    )
    return web.json_response(**command_response)


@routes.post("/v1/cmd/queue/create")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that create a queue. A queue is a matrix room containing agents that will
                be used for chat distribution. `invitees` is a comma-separated list of user_ids.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `name`, `invitees` and optional `description`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        name:
                            type: string
                        invitees:
                            type: array
                            items:
                                type: string
                        description:
                            type: string
                    example:
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

    args = ["create", data.get("name", ""), data.get("invitees", ""), data.get("description", "")]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(**result)


@routes.patch("/v1/cmd/queue/update_members")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Add or remove members from a queue
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `room_id`and `members`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            type: string
                        members:
                            type: array
                            items:
                                type: string
                    example:
                        room_id: "!foo:foo.com"
                        members: ["@agent1:foo.com", "@agent2:foo.com", "@agent3:foo.com"]

    responses:
        '200':
            $ref: '#/components/responses/QueueAddRemoveSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    queue: Queue = await Queue.get_by_room_id(data.get("room_id"))

    if not queue:
        return web.json_response(**QUEUE_DOESNOT_EXIST)

    members: List = set(data.get("members"))

    memberships = await QueueMembership.get_by_queue(queue.id)

    if not memberships:
        return web.json_response(**QUEUE_MEMBERSHIP_DOESNOT_EXIST)

    old_members = set()

    for membership in memberships:
        member: User = await User.get_by_id(membership.fk_user)
        if not member or member.is_admin:
            continue
        old_members.add(member.mxid)

    members_to_add = members - old_members
    members_to_remove = old_members - members

    results = []

    async def add_remove_members(action: str, _members: set):
        for new_member in _members:
            args = [action, new_member, queue.room_id]
            result: Dict = await get_commands().handle(
                sender=user,
                command="queue",
                args_list=args,
                intent=user.az.intent,
                is_management=True,
            )
            results.append(result)

    await add_remove_members("add", members_to_add)
    await add_remove_members("remove", members_to_remove)

    return web.json_response(data={"resuls": results})


@routes.patch("/v1/cmd/queue/add")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Add a member in particular queue.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `member`and `queue_id`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        member:
                            type: string
                        queue_id:
                            type: string
                    example:
                        member: "@foo:foo.com"
                        queue_id: "!foo:foo.com"

    responses:
        '200':
            $ref: '#/components/responses/QueueAddSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    args = ["add", data.get("member", ""), data.get("queue_id", "")]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(**result)


@routes.patch("/v1/cmd/queue/remove")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Remove a member in particular queue.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `member`and `queue_id`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        member:
                            type: string
                        queue_id:
                            type: string
                    example:
                        member: "@foo:foo.com"
                        queue_id: "!foo:foo.com"
    responses:
        '200':
            $ref: '#/components/responses/QueueRemoveSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    args = ["remove", data.get("member", ""), data.get("queue_id", "")]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(**result)


@routes.get("/v1/cmd/queue/info/{room_id}", allow_head=False)
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that shows the queue information, its name and memberships.

    tags:
        - Commands

    responses:
        '200':
            $ref: '#/components/responses/QueueInfoSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    room_id = request.match_info.get("room_id", "")

    args = ["info", room_id]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(**result)


@routes.get("/v1/cmd/queue/list", allow_head=False)
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that shows the all queues.
    tags:
        - Commands

    responses:
        '200':
            $ref: '#/components/responses/QueueListSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    args = ["list"]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(**result)


@routes.patch("/v1/cmd/queue/update")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that update a queue.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `room_id`, `name` and optional `description`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            type: string
                        name:
                            type: string
                        description:
                            type: string
                    example:
                        room_id: "!foo:foo.com"
                        name: "My favourite queue"
                        description: "It is a queue to distribute chats"

    responses:
        '200':
            $ref: '#/components/responses/QueueUpdateSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    args = ["update", data.get("room_id", ""), data.get("name", ""), data.get("description", "")]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(**result)


@routes.delete("/v1/cmd/queue/delete")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that delete a queue.
    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `room_id`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            type: string
                        force:
                            type: boolean
                    example:
                        room_id: "!foo:foo.com"
                        force: true

    responses:
        '200':
            $ref: '#/components/responses/QueueDeleteSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '422':
            $ref: '#/components/responses/NotExist'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    args = ["delete", data.get("room_id", ""), data.get("force", "")]

    result: Dict = await get_commands().handle(
        sender=user, command="queue", args_list=args, intent=user.az.intent, is_management=True
    )

    return web.json_response(**result)


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
                        put_enqueued_portal:
                            type: string
                    required:
                        - customer_room_id
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:example.com"
                        campaign_room_id: "!TXMsaIzbeURlKPeCxJ:example.com"
                        joined_message: "{agentname} has joined the chat."
                        put_enqueued_portal: "`yes` | `no`"

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
    put_enqueued_portal = data.get("put_enqueued_portal") or True

    # Get the puppet from customer_room_id if exists
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    args = [customer_room_id, campaign_room_id, joined_message, put_enqueued_portal]

    response = await get_commands().handle(
        sender=user, command="acd", args_list=args, intent=puppet.intent, is_management=False
    )

    return web.json_response(**response)


@routes.post("/v1/cmd/member")
async def member(request: web.Request) -> web.Response:
    """
    ---
    summary: Agent operations like login, logout, pause, unpause

    tags:
        - Commands

    requestBody:
        required: false
        description: A json with `action`, `agent`, `pause_reason` and optional `list of queues`
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
                        pause_reason:
                            type: string
                    example:
                        action: login | logout | pause | unpause
                        agent: "@agent1:localhost"
                        queues: ["@sdkjfkyasdvbcnnskf:localhost", "@sdkjfkyasdvbcnnskf:localhost"]
                        pause_reason: "LUNCH"

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

    if (
        not data.get("action")
        or not data.get("agent")
        or (data.get("action") == "pause" and not data.get("pause_reason"))
    ):
        return web.json_response(**REQUIRED_VARIABLES)

    actions = ["login", "logout", "pause", "unpause"]
    if not data.get("action") in actions:
        return web.json_response(**INVALID_ACTION)

    action: str = data.get("action")
    agent: UserID = data.get("agent")
    agent_user: User = await User.get_by_mxid(mxid=agent, create=False)
    if not agent_user:
        return web.json_response(**USER_DOESNOT_EXIST)
    queues: List[RoomID] = data.get("queues")
    pause_reason: str = data.get("pause_reason")

    # If queues are None get all rooms where agent is assigning
    if not queues:
        queue_memberships = await QueueMembership.get_user_memberships(agent_user.id)
        if queue_memberships:
            queues = [membership.get("room_id") for membership in queue_memberships]

    if not queues:
        return web.json_response(**AGENT_DOESNOT_HAVE_QUEUES)

    args = [action, agent]
    if action == "pause":
        args = [action, agent, pause_reason]
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


@routes.get("/v1/cmd/member/memberships", allow_head=False)
async def get_memberships(request: web.Request) -> web.Response:
    """
    ---
    summary: Get agent queues memberships

    description: Get agent queues memberships, by user_id or all users

    tags:
        - Commands

    parameters:
    - in: query
      name: user_id
      schema:
          type: string
      examples:
        Filter by user:
            value: "@userid:example.com"
        All users:
            value: ""
      required: false
      description: user_id to get memberships by user, leave empty to filter all users

    responses:
        '200':
            $ref: '#/components/responses/GetUserMembershipsSuccess'
        '404':
            $ref: '#/components/responses/NotFound'
    """

    query_params = request.query
    user_id: str = query_params.get("user_id")

    if user_id and not Util.is_user_id(user_id):
        return web.json_response(**INVALID_USER_ID)

    if user_id:
        target_user = await User.get_by_mxid(user_id, create=False)
        if not target_user:
            return web.json_response(**USER_DOESNOT_EXIST)
        user_memberships = await QueueMembership.get_serialized_memberships(fk_user=target_user.id)
        if not user_memberships:
            return web.json_response(data={"detail": "Agent has no queue memberships"}, status=404)
    else:
        users = await QueueMembership.get_members()
        if not users:
            return web.json_response(
                data={"detail": "Queues do not have member users."}, status=404
            )
        user_memberships = {}
        for user in users:
            member: User = await User.get_by_id(user.get("id"))
            memberships = await QueueMembership.get_serialized_memberships(fk_user=user.get("id"))
            user_memberships[user.get("user_id")] = {
                "is_admin": member.is_admin,
                "memberships": memberships,
            }

    return web.json_response(data={"data": user_memberships}, status=200)
