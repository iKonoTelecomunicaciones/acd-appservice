from __future__ import annotations

import asyncio
import json
from typing import Dict, List

from aiohttp import web
from mautrix.types import RoomID

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
from ..base import _resolve_puppet_identifier, _resolve_user_identifier, get_config, routes
from ..error_responses import (
    BRIDGE_INVALID,
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
                  menubot_id: "nobody@somewhere.com"
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
        sender=user, config=get_config(), command="create", is_management=True, args=args
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
            args=data_cmd.split(),
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
                        room_id: "!gKEsOPrixwrrMFCQCJ:darknet"
                        user_id: "@acd_1:darknet"
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
        args=args,
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
                            "!GmkrVrscIseYrhpTSz:darknet",
                            "!dsardsfasddcshpTSz:darknet",
                            "!GmkrVrssetrhtrsdfz:darknet",
                            "!GnjyuikfdvdfrhpTSz:darknet"
                            ]
                        "user_id": "@supervisor:darknet"
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

    # Creamos una lista de tareas vacías que vamos a llenar con cada uno de los comandos
    # de resolución y luego los ejecutaremos al mismo tiempo
    # de esta manera podremos resolver muchas salas a la vez y poder tener un buen rendimiento

    # Debemos definir de a cuantas salas vamos a resolver
    room_block = get_config()["utils.room_blocks"]

    # Dividimos las salas en sublistas y cada sublista de longitud room_block
    list_room_ids = [room_ids[i : i + room_block] for i in range(0, len(room_ids), room_block)]
    for room_ids in list_room_ids:
        tasks = []
        user.log.info(f"Rooms to be resolved: {room_ids}")
        for room_id in room_ids:
            # Obtenemos el puppet de este email si existe
            puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
            if not puppet:
                # Si esta sala no tiene puppet entonces pasamos a la siguiente
                # la sala sin puppet no será resuelta.
                user.log.warning(
                    f"The room {room_id} has not been resolved because the puppet was not found"
                )
                continue

            # Obtenemos el bridge de la sala dado el room_id
            bridge = await puppet.room_manager.get_room_bridge(room_id=room_id)

            if not bridge:
                # Si esta sala no tiene bridge entonces pasamos a la siguiente
                # la sala sin bridge no será resuelta.
                user.log.warning(
                    f"The room {room_id} has not been resolved because I didn't found the bridge"
                )
                continue

            # Con el bridge obtenido, podremos sacar su prefijo y así luego en el comando
            # resolve podremos enviar un template si así lo queremos
            bridge_prefix = puppet.config[f"bridges.{bridge}.prefix"]

            args = [room_id, user_id, send_message, bridge_prefix]

            # Creating a fake command event and passing it to the command processor.

            fake_cmd_event = CommandEvent(
                sender=user,
                config=get_config(),
                command="resolve",
                is_management=False,
                intent=puppet.intent,
                args=args,
            )

            task = asyncio.create_task(cmd_resolve(fake_cmd_event))
            tasks.append(task)
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            user.log.error(e)
            continue

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
                        room_id: "!gKEsOPrixwrrMFCQCJ:darknet"
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
        args=text_incoming_params.split(),
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
                        room_id: "!duOWDQQCshKjQvbyoh:darknet"
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
        args=text_incoming_params.split(),
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
                        customer_room_id: "!duOWDQQCshKjQvbyoh:darknet"
                        campaign_room_id: "!TXMsaIzbeURlKPeCxJ:darknet"

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
        args=args,
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
                        customer_room_id: "!duOWDQQCshKjQvbyoh:darknet"
                        target_agent_id: "@agente1:darknet"
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
        args=args,
    )

    await cmd_transfer_user(fake_cmd_event)
    return web.json_response()


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
        args=args,
    )

    await cmd_acd(fake_cmd_event)
    return web.json_response()
