from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from aiohttp import web
from markdown import markdown
from mautrix.types import Format, MessageType, TextMessageEventContent

from ...http_client import ProvisionBridge
from ...message import Message
from ...puppet import Puppet
from .. import SUPPORTED_MESSAGE_TYPES
from ..base import _resolve_puppet_identifier, _resolve_user_identifier, routes
from ..error_responses import (
    BRIDGE_INVALID,
    INVALID_PHONE,
    MESSAGE_NOT_FOUND,
    MESSAGE_TYPE_NOT_SUPPORTED,
    NOT_DATA,
    REQUIRED_VARIABLES,
    SERVER_ERROR,
    USER_DOESNOT_EXIST,
)


@routes.get("/v1/mautrix/ws_link_phone", allow_head=False)
async def ws_link_phone(request: web.Request) -> web.Response:
    """
    A QR code is requested to WhatsApp in order to login an email account with a phone number.
    ---
    summary:        Generates a QR code for an existing user in order to create a QR image and
                    link the WhatsApp number by scanning the QR code with the cell phone.
    description:    This creates a `WebSocket` to which you must connect, you will be sent the
                    `qrcode` that you must scan to make a successful connection to `WhatsApp`, if
                    you do not login in time, the connection will be terminated by `timeout`.
    tags:
        - Bridge

    parameters:
    - in: query
      name: user_email
      schema:
          type: string
      required: false
      description: user_email address previously created

    responses:
        '200':
            $ref: '#/components/responses/QrGenerated'
        '201':
            $ref: '#/components/responses/LoginSuccessful'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '422':
            $ref: '#/components/responses/QrNoGenerated'
    """

    ws_customer = web.WebSocketResponse()

    await ws_customer.prepare(request)

    puppet = await _resolve_puppet_identifier(request=request)

    # We create a connector with the bridge
    bridge_connector = ProvisionBridge(session=puppet.intent.api.session, config=puppet.config)
    # We create a WebSocket to connect to the bridge.
    await bridge_connector.mautrix_ws_connect(puppet=puppet, ws_customer=ws_customer)

    return ws_customer


@routes.post("/v1/mautrix/send_message")
@routes.post("/v1/gupshup/send_message")
async def send_message(request: web.Request) -> web.Response:
    """
    Send a message to the given whatsapp number (create a room or send to the existing room)
    ---
    summary: Send a message from the user account to a WhatsApp phone number.
    tags:
        - Bridge

    requestBody:
      required: false
      description: A json with `phone`, `message`, `msg_type` (only supports [`text`]), `user_email`
      content:
        application/json:
          schema:
            type: object
            properties:
              phone:
                type: string
              message:
                type: string
              msg_type:
                type: string
              user_email:
                type: string
              user_id:
                type: string
            example:
                phone: "573123456789"
                message: Hello World!
                msg_type: text
                user_email: nobody@somewhere.com

    responses:
        '201':
            $ref: '#/components/responses/SendMessage'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '422':
            $ref: '#/components/responses/ErrorData'
        '429':
            $ref: '#/components/responses/TooManyRequests'
    """
    await _resolve_user_identifier(request=request)

    url_sections: List[str] = request.path.split("/")
    bridge = url_sections[3]

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data: Dict = await request.json()
    data = await request.json()

    if not (
        data.get("phone")
        and data.get("message")
        and data.get("msg_type")
        and (data.get("user_email") or data.get("user_id"))
    ):
        return web.json_response(**REQUIRED_VARIABLES)

    if not data.get("msg_type") in SUPPORTED_MESSAGE_TYPES:
        return web.json_response(**MESSAGE_TYPE_NOT_SUPPORTED)

    puppet = await _resolve_puppet_identifier(request=request)

    if puppet.bridge != bridge:
        return web.json_response(**BRIDGE_INVALID)

    phone = str(data.get("phone"))
    if not (phone.isdigit() and 5 <= len(phone) <= 15):
        return web.json_response(**INVALID_PHONE)

    msg_type = data.get("msg_type")
    message = data.get("message")
    phone = phone if phone.startswith("+") else f"+{phone}"

    # We create a connector with the bridge
    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=bridge
    )

    status, response = await bridge_connector.pm(user_id=puppet.custom_mxid, phone=phone)

    if response.get("error") or not response.get("room_id"):
        return web.json_response(data=response, status=status)

    customer_room_id = response.get("room_id")

    if msg_type == "text":
        content = TextMessageEventContent(
            msgtype=MessageType.TEXT,
            body=message,
            format=Format.HTML,
            formatted_body=markdown(message),
        )

    # Here you can have the other message types when you think about implementing them
    # if msg_type == "image":
    #     content = MediaMessageEventContent(
    #         msgtype=MessageType.IMAGE,
    #         body=message,
    #         format=Format.HTML,
    #         formatted_body=message,
    #     )

    try:
        if puppet.config[f"bridges.{bridge}.send_template_command"]:

            # If another bridge must send templates, make this method (gupshup_template) generic.
            status, data = await bridge_connector.gupshup_template(
                room_id=customer_room_id, user_id=puppet.custom_mxid, template=message
            )
            if not status in [200, 201]:
                return web.json_response(status=status, data=data)

            event_id = data.get("event_id")
        else:
            event_id = await puppet.intent.send_message(room_id=customer_room_id, content=content)
    except Exception as e:
        puppet.log.exception(e)
        return web.json_response(**SERVER_ERROR)

    try:
        # We register the message in the db
        await Message.insert_msg(
            event_id=event_id,
            room_id=customer_room_id,
            sender=puppet.custom_mxid,
            receiver=phone,
            timestamp_send=datetime.timestamp(datetime.utcnow()),
        )
    except Exception as e:
        puppet.log.exception(e)

    return web.json_response(
        data={
            "detail": "The message has been sent (probably)",
            "event_id": event_id,
            "room_id": customer_room_id,
        },
        status=201,
    )


@routes.get("/v1/mautrix/link_phone")
async def link_phone(request: web.Request) -> web.Response:
    """
    A QR code is requested to WhatsApp in order to login an email account with a phone number.
    ---
    summary:        Generates a QR code for an existing user in order to create a QR image and
                    link the WhatsApp number by scanning the QR code with the cell phone.
    tags:
        - Bridge

    parameters:
    - in: query
      name: user_email
      schema:
          type: string
      required: false
      description: user_email address previously created

    responses:
        '200':
            $ref: '#/components/responses/QrGenerated'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '422':
            $ref: '#/components/responses/QrNoGenerated'
    """
    await _resolve_user_identifier(request=request)

    puppet = await _resolve_puppet_identifier(request=request)

    # We create a connector with the bridge
    bridge_connector = ProvisionBridge(session=puppet.intent.api.session, config=puppet.config)
    # We create a WebSocket to connect to the bridge.
    return web.json_response(
        **await bridge_connector.mautrix_ws_connect(puppet=puppet, easy_mode=True)
    )


@routes.post("/v1/instagram/login")
async def instagram_login(request: web.Request) -> web.Response:
    """
    Login to Instagram Bridge.
    ---
    summary:        Sign in with your instagram account to start receiving messages.
    tags:
        - Bridge
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
              username:
                type: string
              password:
                type: string
            example:
                user_email: nobody@somewhere.com
                username: instagram_user
                password: secretfoo

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    puppet = await _resolve_puppet_identifier(request=request)

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    response = await bridge_connector.instagram_login(
        user_id=puppet.custom_mxid, username=username, password=password
    )

    return web.json_response(data=response)


@routes.post("/v1/instagram/challenge")
async def instagram_challenge(request: web.Request) -> web.Response:
    """
    Solve the instagram login challenge.
    ---
    summary:        By sending the code that instagram sent you, you can finish the login process.

    tags:
        - Bridge

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
                code:
                    type: string
            example:
                user_email: nobody@somewhere.com
                code: 54862

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data = await request.json()
    code = data.get("code")

    puppet = await _resolve_puppet_identifier(request=request)

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    response = await bridge_connector.instagram_challenge(user_id=puppet.custom_mxid, code=code)

    return web.json_response(data=response)


@routes.post("/v1/gupshup/register")
async def gupshup_register(request: web.Request) -> web.Response:
    """
    Register a gupshup app
    ---
    summary:        Sending information you can register a new gupshup line.

    tags:
        - Bridge

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
                    gs_app_name:
                        type: string
                    gs_app_phone:
                        type: string
                    api_key:
                        type: string
                    app_id:
                        type: string
                example:
                    user_email: nobody@somewhere.com
                    gs_app_name: AppName
                    gs_app_phone: 573123456789
                    api_key: your_api_key
                    app_id: AppID

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    gupshup_data = await request.json()

    gs_app_data = {
        "gs_app_name": gupshup_data.get("gs_app_name"),
        "gs_app_phone": gupshup_data.get("gs_app_phone"),
        "api_key": gupshup_data.get("api_key"),
        "app_id": gupshup_data.get("app_id"),
    }

    puppet = await _resolve_puppet_identifier(request=request)

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    status, data = await bridge_connector.gupshup_register_app(
        user_id=puppet.custom_mxid, data=gs_app_data
    )

    if status in [200, 201]:
        puppet.phone = gupshup_data.get("gs_app_phone")
        await puppet.save()

    return web.json_response(status=status, data=data)


@routes.get("/v1/read_check", allow_head=False)
async def read_check(request: web.Request) -> web.Response:
    """
    ---
    summary:        Check if a message has been read
    tags:
        - Bridge

    parameters:
    - in: query
      name: event_id
      schema:
          type: string
      required: false
      description: message sent

    responses:
        '200':
            $ref: '#/components/responses/MessageFound'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
    """

    event_id = request.rel_url.query["event_id"]
    if not event_id:
        return web.json_response(**REQUIRED_VARIABLES)

    message: Message = await Message.get_by_event_id(event_id=event_id)

    if not message:
        return web.json_response(**MESSAGE_NOT_FOUND)

    return web.json_response(data=message.__dict__)


@routes.post("/v1/get_bridges_status")
async def get_bridges_status(request: web.Request) -> web.Response:

    # """
    # ---
    # summary:        Given a list of puppets, get his bridges status.
    # tags:
    #     - Bridge

    # requestBody:
    #     required: false
    #     description: A json with `puppet_list`
    #     content:
    #         application/json:
    #             schema:
    #                 type: object
    #                 properties:
    #                     puppet_list:
    #                         type: array
    #                         items:
    #                             type: string
    #                 example:
    #                     puppet_list: ["@acd1:localhost", "@acd2:localhost"]

    # responses:
    #     '200':
    #         $ref: '#/components/responses/BridgesStatus'
    # """

    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data = await request.json()

    bridges_status = []

    for puppet_mxid in data.get("puppet_list"):
        puppet: Puppet = await Puppet.get_by_custom_mxid(puppet_mxid)

        if not puppet or puppet.bridge == "gupshup":
            continue

        bridge_conector = ProvisionBridge(
            config=puppet.config, session=puppet.intent.api.session, bridge=puppet.bridge
        )
        status = await bridge_conector.ping(puppet.mxid)
        bridges_status.append(status)

    return web.json_response(data={"bridges_status": bridges_status})


@routes.post("/v1/logout")
async def logout(request: web.Request) -> web.Response:

    """
    ---
    summary:        Close connection of a previously logged-in bridge
    tags:
        - Bridge

    requestBody:
        required: true
        description: A json with user to unlog
        content:
            application/json:
                schema:
                    type: object
                    properties:
                        user_id:
                            type: string
                    example:
                        user_id: "@acd1:example.com"

    responses:
        '200':
            $ref: '#/components/responses/Logout'
        '404':
            $ref: '#/components/responses/LogoutFail'
    """

    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    puppet = await _resolve_puppet_identifier(request=request)

    if not puppet:
        return web.json_response(**USER_DOESNOT_EXIST)

    bridge_conector = ProvisionBridge(
        config=puppet.config, session=puppet.intent.api.session, bridge=puppet.bridge
    )
    status, response = await bridge_conector.logout(user_id=puppet.mxid)
    return web.json_response(data=response, status=status)
