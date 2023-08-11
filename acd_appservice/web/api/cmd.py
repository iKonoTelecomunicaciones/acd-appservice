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
    NO_PUPPET_IN_PORTAL,
    NOT_DATA,
    QUEUE_DOESNOT_EXIST,
    QUEUE_MEMBERSHIP_DOESNOT_EXIST,
    REQUIRED_VARIABLES,
    SERVER_ERROR,
    UNABLE_TO_FIND_PUPPET,
    USER_DOESNOT_EXIST,
)


@routes.post("/v1/cmd/create")
async def create(request: web.Request) -> web.Response:
    """
    Creates a user in the User table and its respective puppet
    ---
    summary: Creates a user in the platform to be able to scan the WhatsApp QR code
             and send messages later using the API endpoints.
    tags:
        - Commands

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
        description: A json with all optional parameter,
                     `user_email`, `destination`, `bridge`
        content:
          application/json:
            schema:
              type: object
              properties:
                user_email:
                  description: "User email"
                  type: string
                destination:
                  description: "It can be a queue, an user or a menu"
                  type: string
                bridge:
                  description: "What kind of bridge you will be used with him?"
                  type: string
                  enum:
                    - mautrix
                    - gupshup
                    - instagram
                    - facebook
              example:
                  user_email: "@acd1:somewhere.com"
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
            args = args + ["-b", data.get("bridge")]

        if data.get("destination"):
            args = args + ["-d", data.get("destination")]

        if data.get("user_email"):
            args = args + ["-e", data.get("user_email")]

    puppet: Puppet = await get_commands().handle(
        sender=user,
        command="create",
        args_list=args,
        is_management=True,
        mute_reply=True,
    )

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
                and sends the message to the phone number and join the sender to the conversation.
    tags:
        - Commands

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
        description: A json with `customer_phone`, `company_phone`, `template_message`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_phone:
                            description: "Target phone number to send message, (use country code)"
                            type: string
                        company_phone:
                            description: "Phone number that will be used to send the message,
                                         (use country code)"
                            type: string
                        template_message:
                            description: "Message that will be sent"
                            type: string
                    required:
                        - customer_phone
                        - company_phone
                        - template_message
                    example:
                        customer_phone: "573123456789"
                        company_phone: "57398765432"
                        template_message: "Hola iKono!!"

    responses:
        '200':
            $ref: '#/components/responses/PmSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/UnableToFindPuppet'
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
        return web.json_response(**UNABLE_TO_FIND_PUPPET)

    args = ["-p", phone, "-m", message]

    result = await get_commands().handle(
        sender=user,
        command="pm",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.post("/v1/cmd/resolve")
async def resolve(request: web.Request) -> web.Response:
    """
    ---
    summary: Command resolving a chat, ejecting the supervisor and the agent.
    tags:
        - Commands

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
        description: A json with `room_id`, `user_id`, `send_message`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            description: "The portal that will be resolved"
                            type: string
                        user_id:
                            description: "The user that makes the action"
                            type: string
                        send_message:
                            description: "Do you want to notify the customer that his room was resolved?"
                            type: string
                    required:
                        - room_id
                        - user_id
                        - send_message
                    example:
                        room_id: "!foo:foo.com"
                        user_id: "@acd_1:foo.com"
                        send_message: "yes"

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("room_id") and data.get("user_id")):
        return web.json_response(**REQUIRED_VARIABLES)

    room_id = data.get("room_id")
    user_id = data.get("user_id")
    send_message = data.get("send_message") if data.get("send_message") else "no"

    # Get puppet from this portal if exists
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=room_id)
    portal: Portal = await Portal.get_by_room_id(
        room_id=room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )

    if not puppet:
        return web.json_response(**NO_PUPPET_IN_PORTAL)

    if not portal.bridge:
        return web.json_response(**BRIDGE_INVALID)

    args = ["-p", room_id, "-a", user_id, "-sm", send_message]

    await get_commands().handle(
        sender=user,
        command="resolve",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
        mute_reply=True,
    )
    return web.json_response()


@routes.post("/v1/cmd/bulk_resolve")
async def bulk_resolve(request: web.Request) -> web.Response:
    """
    ---
    summary: Command to bulk resolve chats, kicking the supervisor and the agent.
    tags:
        - Commands

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
        description: A json with `room_ids`, `send_message`, `user_id`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_ids:
                            description: "The list of rooms to be resolved"
                            type: array
                            items:
                                type: string
                        user_id:
                            description: "The user that makes the action"
                            type: string
                        send_message:
                            description: "You want to notify the customer that his room was resolved?"
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
        description: A json with `room_id`, `event_type`, `content`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            description: "The room where will be sent the event"
                            type: string
                        event_type:
                            description: "The event type"
                            type: string
                        content:
                            description: "The content of the event that will be sent"
                            type: object
                    example:
                        room_id: "!foo:foo.com"
                        event_type: "m.custom.event"
                        content: {
                                    "tags": ["tag1", "tag2", "tag3"]
                                }

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'
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

    # Get puppet from this portal if exists
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=room_id)
    if not puppet:
        return web.json_response(**NO_PUPPET_IN_PORTAL)

    args = ["-r", room_id, "-e", event_type, "-c", json.dumps(content)]

    await get_commands().handle(
        sender=user,
        command="state_event",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
        mute_reply=True,
    )

    return web.json_response()


@routes.post("/v1/cmd/template")
async def template(request: web.Request) -> web.Response:
    """
    ---
    summary: This command is used to send templates
    tags:
        - Commands

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
        description: A json with `room_id` and `template`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            description: "The room where will be sent the template"
                            type: string
                        template_message:
                            description: "The message template that will be sent to room"
                            type: string
                    example:
                        room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        template_message: "Hola iKono!!"

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'
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
        return web.json_response(**NO_PUPPET_IN_PORTAL)

    args = ["-p", room_id, "-m", template_message]

    await get_commands().handle(
        sender=user,
        command="template",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
        mute_reply=True,
    )
    return web.json_response()


@routes.post("/v1/cmd/transfer")
async def transfer(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that transfers a client to an campaign_room.
    tags:
        - Commands

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
        description: A json with `customer_room_id`, `campaign_room_id` and `enqueue_chat`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_room_id:
                            description: "Customer room to transfer"
                            type: string
                        campaign_room_id:
                            description: "Target queue to execute the transfer"
                            type: string
                        enqueue_chat:
                            description: "If there are no agents available, enqueue the chat"
                            type: string
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        campaign_room_id: "!TXMsaIzbeURlKPeCxJ:foo.com"
                        enqueue_chat: "no | yes"

    responses:
        '200':
            $ref: '#/components/responses/TransferQueueInProcess'
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'
        '423':
            $ref: '#/components/responses/PortalIsLocked'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("customer_room_id") and data.get("campaign_room_id")):
        return web.json_response(**REQUIRED_VARIABLES)

    customer_room_id = data.get("customer_room_id")
    campaign_room_id = data.get("campaign_room_id")
    enqueue_chat = data.get("enqueue_chat", "no")

    # Get puppet from this portal if exists
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    if not puppet:
        return web.json_response(**NO_PUPPET_IN_PORTAL)

    args = ["-p", customer_room_id, "-q", campaign_room_id, "-e", enqueue_chat]

    cmd_response = await get_commands().handle(
        sender=user,
        command="transfer",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
        mute_reply=True,
    )

    return web.json_response(**cmd_response)


@routes.post("/v1/cmd/transfer_user")
async def transfer_user(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that transfers a client from one agent to another.
    tags:
        - Commands

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
        description: A json with `customer_room_id`, `target_agent_id`, `force`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_room_id:
                            description: "The room that will be transferred"
                            type: string
                        target_agent_id:
                            description: "Target user that will be joined to customer room"
                            type: string
                        force:
                            description: "Do you want to force the transfer,
                                          no matter that the agent will be logged out?"
                            type: string
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:foo.com"
                        target_agent_id: "@agente1:foo.com"
                        force: "yes"

    responses:
        '200':
            $ref: '#/components/responses/OK'
        '202':
            $ref: '#/components/responses/TransferSuccessButAgentUnavailable'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'
        '423':
            $ref: '#/components/responses/PortalIsLocked'

    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not (data.get("customer_room_id") and data.get("target_agent_id")):
        return web.json_response(**REQUIRED_VARIABLES)

    customer_room_id = data.get("customer_room_id")
    target_agent_id = data.get("target_agent_id")
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
        mute_reply=True,
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
        description: A json with `name`, `invitees` and optional `description`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        name:
                            description: "Name of the queue"
                            type: string
                        invitees:
                            description: "Agents to be joining the queue"
                            type: array
                            items:
                                type: string
                        description:
                            description: "A brief overview of the queue"
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
        '409':
            $ref: '#/components/responses/QueueExists'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()
    invitees = ",".join(data.get("invitees", "")) if data.get("invitees", "") else ""

    args = [
        "create",
        "-n",
        data.get("name", ""),
        "-i",
        invitees,
        "-d",
        data.get("description", ""),
    ]

    result: Dict = await get_commands().handle(
        sender=user,
        command="queue",
        args_list=args,
        intent=user.az.intent,
        is_management=True,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.patch("/v1/cmd/queue/update_members")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Add or remove members from a queue
    tags:
        - Commands

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
        description: A json with `room_id`and `members`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            description: "Queue room id"
                            type: string
                        members:
                            description: "Updates members, a list of UserIDs"
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

    queue: Queue = await Queue.get_by_room_id(data.get("room_id"), create=False)

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
            args = [action, "-m", new_member, "-q", queue.room_id]
            result: Dict = await get_commands().handle(
                sender=user,
                command="queue",
                args_list=args,
                intent=user.az.intent,
                is_management=True,
                mute_reply=True,
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
        description: A json with `member`and `queue_id`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        member:
                            description: "New member"
                            type: string
                        queue_id:
                            description: "Queue room id"
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

    args = ["add", "-m", data.get("member", ""), "-q", data.get("queue_id", "")]

    result: Dict = await get_commands().handle(
        sender=user,
        command="queue",
        args_list=args,
        intent=user.az.intent,
        is_management=True,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.patch("/v1/cmd/queue/remove")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Remove a member in particular queue.
    tags:
        - Commands

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
        description: A json with `member`and `queue_id`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        member:
                            description: "Member to remove"
                            type: string
                        queue_id:
                            description: "Queue room id"
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

    args = ["remove", "-m", data.get("member", ""), "-q", data.get("queue_id", "")]

    result: Dict = await get_commands().handle(
        sender=user,
        command="queue",
        args_list=args,
        intent=user.az.intent,
        is_management=True,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.get("/v1/cmd/queue/info/{room_id}", allow_head=False)
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that shows the queue information, its name and memberships.

    tags:
        - Commands

    parameters:
        - in: header
          name: Authorization
          description: User that makes the request
          required: true
          schema:
              type: string
          example: Mxid @user:example.com

        - in: path
          name: room_id
          description: Queue room id
          required: true
          schema:
            type: string

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

    args = ["info", "-q", room_id]

    result: Dict = await get_commands().handle(
        sender=user,
        command="queue",
        args_list=args,
        intent=user.az.intent,
        is_management=True,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.get("/v1/cmd/queue/list", allow_head=False)
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that shows the all queues.
    tags:
        - Commands

    parameters:
    - in: header
      name: Authorization
      description: User that makes the request
      required: true
      schema:
        type: string
      example: Mxid @user:example.com

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
        sender=user,
        command="queue",
        args_list=args,
        intent=user.az.intent,
        is_management=True,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.patch("/v1/cmd/queue/update")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that update a queue.
    tags:
        - Commands

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
        description: A json with `room_id`, `name` and optional `description`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            description: "Queue room id"
                            type: string
                        name:
                            description: "Queue name"
                            type: string
                        description:
                            description: "A brief overview of the queue"
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
        '409':
            $ref: '#/components/responses/QueueExists'
    """
    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    args = [
        "update",
        "-q",
        data.get("room_id", ""),
        "-n",
        data.get("name", ""),
        "-d",
        data.get("description", ""),
    ]

    result: Dict = await get_commands().handle(
        sender=user,
        command="queue",
        args_list=args,
        intent=user.az.intent,
        is_management=True,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.delete("/v1/cmd/queue/delete")
async def queue(request: web.Request) -> web.Response:
    """
    ---
    summary:    Command that delete a queue.
    tags:
        - Commands

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
        description: A json with `room_id` and `force`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        room_id:
                            description: "Queue room id"
                            type: string
                        force:
                            description: "This queue has assigned agents.
                                          Are you sure you want to force delete the queue?"
                            type: string
                    example:
                        room_id: "!foo:foo.com"
                        force: "yes | no"

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

    args = ["delete", "-q", data.get("room_id", ""), "-f", data.get("force", "")]

    result: Dict = await get_commands().handle(
        sender=user,
        command="queue",
        args_list=args,
        intent=user.az.intent,
        is_management=True,
        mute_reply=True,
    )

    return web.json_response(**result)


@routes.post("/v1/cmd/acd")
async def acd(request: web.Request) -> web.Response:
    """
    ---
    summary: Command that allows to distribute the chat of a client.

    description: Command that allows to distribute the chat of a client,
                 optionally a campaign room and a joining message can be given.

    tags:
        - Commands

    parameters:
    - in: header
      name: Authorization
      description: User that makes the request
      required: true
      schema:
        type: string
      example: Mxid @user:example.com

    requestBody:
        required: true
        description: A JSON with `customer_room_id`, `destination`,
                     `joined_message` and `put_enqueued_portal`. The customer_room_id is required.
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_room_id:
                            description: "Portal room id to be distributed"
                            type: string
                        destination:
                            description: "Queue room id or agent mxid where chat will be distributed"
                            type: string
                        joined_message:
                            description: "Message to show client when agent will enter the room"
                            type: string
                        put_enqueued_portal:
                            description: "If the distribution process was not successful,
                                          do you want to put portal enqueued?\n
                                          Note: This parameter is only using when destination is a queue"
                            type: string
                        force_distribute:
                            description: "You want to force the agent distribution?\n
                                         Note: This parameter is only using when destination is an agent"
                            type: string
                    required:
                        - customer_room_id
                    example:
                        customer_room_id: "!duOWDQQCshKjQvbyoh:example.com"
                        destination: "!TXMsaIzbeURlKPeCxJ:example.com | @agent1:example.com"
                        joined_message: "{agentname} has joined the chat."
                        put_enqueued_portal: "`yes` | `no`"
                        force_distribution: "`yes` | `no`"

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'
        '422':
            $ref: '#/components/responses/RequiredVariables'
        '423':
            $ref: '#/components/responses/PortalIsLocked'
    """

    user = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not data.get("customer_room_id"):
        return web.json_response(**REQUIRED_VARIABLES)

    customer_room_id = data.get("customer_room_id")
    # TODO change name to destination when menu will be updated
    # TODO put required destination
    campaign_room_id = data.get("campaign_room_id") or ""
    joined_message = data.get("joined_message") or ""
    put_enqueued_portal = data.get("put_enqueued_portal") or "yes"
    force_distribution = data.get("force_distribution") or "no"

    # Get the puppet from customer_room_id if exists
    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    if not puppet:
        return web.json_response(**NO_PUPPET_IN_PORTAL)

    args = ["-c", customer_room_id, "-j", joined_message]
    if Util.is_room_id(campaign_room_id):
        args = args + ["-q", campaign_room_id, "-e", put_enqueued_portal]
    elif Util.is_user_id(campaign_room_id):
        args = args + ["-a", campaign_room_id, "-f", force_distribution]

    response = await get_commands().handle(
        sender=user,
        command="acd",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
        mute_reply=True,
    )

    return web.json_response(**response)


@routes.post("/v1/cmd/member")
async def member(request: web.Request) -> web.Response:
    """
    ---
    summary: Agent operations like login, logout, pause, unpause

    tags:
        - Commands

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
        description: A json with `action`, `agent`, `pause_reason` and optional `list of queues`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        action:
                            description: "Action that will be applied to queue member"
                            type: string
                        agent:
                            description: "Agent mxid of the queue memeber"
                            type: string
                        queues:
                            description: "Queue where action will applied"
                            type: array
                            items:
                                type: string
                        pause_reason:
                            description: "Only if you are pausing an agent, send this parameter"
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

    args = ["-a", action, "--agent", agent]
    if action == "pause":
        args = args + ["-p", pause_reason]

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
            mute_reply=True,
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
    - in: header
      name: Authorization
      description: User that makes the request
      required: true
      schema:
        type: string
      example: Mxid @user:example.com

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


@routes.post("/v1/cmd/bic")
async def bic(request: web.Request) -> web.Response:
    """
    ---
    summary: Initiate a conversation by the bussiness

    description: Initiate a conversation by the bussiness

    tags:
        - Commands

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
        description: A json with `customer_phone`, `company_phone`, `message`, `on_transit`
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        customer_phone:
                            description: "Target phone number to send message, (use country code)"
                            type: string
                        company_phone:
                            description: "Phone number that will be used to send the message,
                                         (use country code)"
                            type: string
                        destination:
                            description: "Queue room id, agent or menu mxid where chat will be distributed"
                            type: string
                        message:
                            description: "Message that will be sent"
                            type: string
                        on_transit:
                            description: "Do not process destination inmediatly, wait for a customer message"
                            type: string
                        force:
                            description: "If an agent is in the room, do you want to start a new conversation?"
                            type: string
                        enqueue_chat:
                            description: "If the distribution process was not successful,
                                          do you want to put portal enqueued?\n
                                          Note: This parameter is only using when destination is a queue"
                            type: string
                    required:
                        - customer_phone
                        - company_phone
                        - message
                    example:
                        customer_phone: "573123456789"
                        company_phone: "57398765432"
                        destination: "@agent1:example.com | !TXMsaIzbeURlKPeCxJ:example.com | @menu:example.com"
                        message: "Hola iKono!!"
                        enqueue_chat: "yes"
                        on_transit: "no"
                        force: "no"

    responses:
        '200':
            $ref: '#/components/responses/PmSuccessful'
        '404':
            $ref: '#/components/responses/NotFound'
        '422':
            $ref: '#/components/responses/NotSendMessage'
    """

    user: User = await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()

    if not data.get("customer_phone") or not data.get("company_phone"):
        return web.json_response(**REQUIRED_VARIABLES)

    puppet: Puppet = await _resolve_puppet_identifier(request=request)

    phone: str = data.get("customer_phone")
    message: str = data.get("message")
    on_transit: str = data.get("on_transit")
    destination: str = data.get("destination") if data.get("destination") else ""
    force: str = data.get("force")
    enqueue_chat: str = data.get("enqueue_chat")

    args = [
        "-p",
        phone,
        "-m",
        message,
        "-d",
        destination,
        "-t",
        on_transit,
        "-f",
        force,
        "-e",
        enqueue_chat,
    ]

    result = await get_commands().handle(
        sender=user,
        command="bic",
        args_list=args,
        intent=puppet.intent,
        is_management=False,
        mute_reply=True,
    )

    return web.json_response(**result)
