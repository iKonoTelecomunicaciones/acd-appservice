from __future__ import annotations

from datetime import datetime
from logging import Logger, getLogger
from typing import Dict, List

from aiohttp import web
from markdown import markdown
from mautrix.types import Format, MessageType, TextMessageEventContent

from ...client import ProvisionBridge
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
    NOT_EMAIL,
    NOT_USERNAME,
    REQUIRED_VARIABLES,
    SERVER_ERROR,
    USER_DOESNOT_EXIST,
)

log: Logger = getLogger()


@routes.get("/v1/mautrix/ws_link_phone", allow_head=False)
async def ws_link_phone(request: web.Request) -> web.Response:
    """
    A QR code is requested to WhatsApp in order to join an email or MxID with a WhatsApp account.
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
      description: Email address of the user previously created
    - in: query
      name: user_id
      schema:
          type: string
      required: false
      description: MxID of the user previously created

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
      description: A json with `phone`, `message`, `msg_type`,
                   `user_email` or `user_id` (You must use one of them)
      content:
        application/json:
          schema:
            type: object
            properties:
              phone:
                description: "Target phone number to send message, (use country code)"
                type: string
              message:
                description: "Message that will be sent"
                type: string
              msg_type:
                description: "Message type, (only supports [`text`])"
                type: string
              user_email:
                description: "Puppet email"
                type: string
              user_id:
                description: "Puppet user_id"
                type: string
            required:
              - phone
              - message
              - msg_type
            example:
                phone: "573123456789"
                message: Hello World!
                msg_type: text
                user_email: nobody@somewhere.com
                user_id: '@acd1:somewhere.com'

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

    # TODO WORKAROUND FOR NOT LINKING TO THE MENU IN A BIC
    user_prefix = puppet.config[f"bridges.{puppet.bridge}.user_prefix"]
    user_domain = puppet.config["homeserver.domain"]
    portal_creator = f"@{user_prefix}_{phone.replace('+', '')}:{user_domain}"

    log.debug(f"Putting portal with creator {portal_creator} in BIC rooms")
    puppet.BIC_ROOMS.add(portal_creator)

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
    A QR code is requested to WhatsApp in order to join an email or MxID with a WhatsApp account.
    ---
    summary:        Generates a QR code for an existing user in order to create a QR image and
                    link the WhatsApp number by scanning the QR code with the cell phone.
    tags:
        - Bridge

    parameters:
    - in: header
      name: Authorization
      description: User that makes the request
      required: true
      schema:
        type: string
      example: Mxid @user:example.com
    - in: query
      name: user_email
      schema:
          type: string
      required: false
      description: Email address of the user previously created
    - in: query
      name: user_id
      schema:
          type: string
      required: false
      description: MxID of the user previously created

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


@routes.patch("/v1/{bridge_meta}/login")
async def metainc_login(request: web.Request) -> web.Response:
    """
    Login to Facebook or Instagram bridge.
    ---
    summary: Login to Facebook or Instagram bridge.

    description: Sign in with your Instagram or Facebook account to start receiving messages.

    tags:
        - Bridge

    parameters:
    - in: header
      name: Authorization
      description: User that makes the request
      required: true
      schema:
        type: string
      example: Mxid @user:example.com
    - name: bridge_meta
      description: 'The Facebook or Instagram bridge'
      in: path
      required: true
      schema:
        type: string
        enum:
          - instagram
          - facebook

    requestBody:
      required: true
      description: A JSON with `user_id` or `user_email` of the puppet bridge and `email`
                   (or `username`) and `password` to sign in with Meta account.
      content:
        application/json:
          schema:
            type: object
            properties:
              user_email:
                description: "The puppet user email"
                type: string
                format: email
              user_id:
                description: "The puppet user id"
                type: string
              auth:
                description: "The Meta account credentials"
                type: object
                properties:
                    email:
                        description: "To login with Facebook account"
                        type: string
                    username:
                        description: "To login with Instagram account"
                        type: string
                    password:
                        type: string
                        format: password
                required:
                    - password
          examples:
            Instagram:
                value:
                    user_id: "@puppet:somewhere.com"
                    auth:
                        username: johndoe123
                        password: secretfoo
            Facebook:
                value:
                    user_id: "@puppet:somewhere.com"
                    auth:
                        email: "johndoe@email.com"
                        password: secretfoo

    responses:
        '202':
            $ref: '#/components/responses/Login2faRequired'
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '422':
            $ref: '#/components/responses/RequiredVariables'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data = await request.json()
    auth = data.get("auth")
    email = auth.get("email")
    username = auth.get("username")
    password = auth.get("password")

    puppet = await _resolve_puppet_identifier(request=request)

    bridge_meta = request.match_info.get("bridge_meta", "")
    if bridge_meta != puppet.bridge:
        return web.json_response(**BRIDGE_INVALID)
    elif bridge_meta == "instagram" and not username:
        return web.json_response(**NOT_USERNAME)
    elif bridge_meta == "facebook" and not email:
        return web.json_response(**NOT_EMAIL)
    elif not password:
        return web.json_response(**REQUIRED_VARIABLES)

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    status, response = await bridge_connector.metainc_login(
        user_id=puppet.custom_mxid, email=email, username=username, password=password
    )

    if response.get("status") == "two-factor":
        data = {"status": response.get("status")}
        if bridge_meta == "instagram":
            _two_factor_info = response.get("response").get("two_factor_info")
            data["two_factor_info"] = {
                "sms_two_factor_on": _two_factor_info.get("sms_two_factor_on"),
                "totp_two_factor_on": _two_factor_info.get("totp_two_factor_on"),
                "obfuscated_phone_number": _two_factor_info.get("obfuscated_phone_number"),
                "two_factor_identifier": _two_factor_info.get("two_factor_identifier"),
            }
        elif bridge_meta == "facebook":
            _error = response.get("error")
            data["error"] = {
                "message": _error.get("message"),
                "type": _error.get("type"),
                "error_user_title": _error.get("error_user_title"),
                "error_user_msg": _error.get("error_user_msg"),
            }
        puppet.log.info(f"Login with ({email or username}) in {bridge_meta} bridge requires 2FA")
        return web.json_response(data=data, status=202)

    if status not in [200, 201]:
        puppet.log.error(f"Login with ({email or username}) in {bridge_meta} bridge has failed")

    return web.json_response(data=response, status=status)


@routes.patch("/v1/{bridge_meta}/challenge")
async def metainc_challenge(request: web.Request) -> web.Response:
    """
    Solve the Facebook or Instagram login challenge.
    ---
    summary: Solve the Facebook or Instagram login challenge.

    description: By sending the code that Facebook or Instagram sent you, you can finish the login process.

    tags:
        - Bridge

    parameters:
    - in: header
      name: Authorization
      description: User that makes the request
      required: true
      schema:
        type: string
      example: Mxid @user:example.com
    - name: bridge_meta
      description: 'The Facebook or Instagram bridge'
      in: path
      required: true
      schema:
        type: string
        enum:
        - instagram
        - facebook

    requestBody:
      required: true
      description: A JSON with `user_id` or `user_email` of the puppet bridge, `email`
                   and `code` to finish the login process.
      content:
        application/json:
          schema:
            type: object
            properties:
                user_email:
                    description: "The puppet user email"
                    type: string
                    format: email
                user_id:
                    description: "The puppet user id"
                    type: string
                challenge:
                    description: "The login data for two factor authentication (2FA)"
                    type: object
                    properties:
                        username:
                            description: "To login with Instagram account"
                            type: string
                        email:
                            description: "To login with Facebook account"
                            type: string
                        code:
                            description: "The code number to challenge (TOTP, SMS or checkpoint)"
                            type: string
                        type_2fa:
                            type: string
                            enum:
                              - sms_2fa
                              - totp_2fa
                              - checkpoint
                        id_2fa:
                            description: "Two factor authentication identifier"
                            type: string
                        resend_2fa_sms:
                            type: boolean
                    required:
                        - code
          examples:
            Instagram:
                value:
                    user_id: "@puppet:somewhere.com"
                    challenge:
                        username: johndoe987
                        code: 54862
                        type_2fa: sms_2fa
                        id_2fa: abcdEju9yATxCPs3TzgvjEFR1234abcd9bRjbeQGznHf6JoBo6xvd3W1234
                        resend_2fa_sms: false
            Facebook:
                value:
                    user_id: "@puppet:somewhere.com"
                    challenge:
                        email: "johndoe@email.com"
                        code: 54862

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '422':
            $ref: '#/components/responses/RequiredVariables'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    data = await request.json()
    challenge = data.get("challenge")
    username = challenge.get("username")
    email = challenge.get("email")
    code = challenge.get("code")
    type_2fa = challenge.get("type_2fa")
    id_2fa = challenge.get("id_2fa")
    resend_2fa_sms = challenge.get("resend_2fa_sms")

    puppet = await _resolve_puppet_identifier(request=request)

    bridge_meta = request.match_info.get("bridge_meta", "")
    if bridge_meta != puppet.bridge:
        return web.json_response(**BRIDGE_INVALID)
    elif bridge_meta == "instagram":
        if not username:
            return web.json_response(**NOT_USERNAME)
        elif type_2fa in ["sms_2fa", "totp_2fa"] and not id_2fa:
            return web.json_response(
                data={"error": "Two factor authentication ID is required"}, status=422
            )
    elif bridge_meta == "facebook" and not email:
        return web.json_response(**NOT_EMAIL)
    elif not code:
        return web.json_response(**REQUIRED_VARIABLES)

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    status, response = await bridge_connector.metainc_challenge(
        user_id=puppet.custom_mxid,
        username=username,
        email=email,
        code=code,
        type_2fa=type_2fa,
        id_2fa=id_2fa,
        resend_2fa_sms=resend_2fa_sms,
    )

    if status not in [200, 201]:
        puppet.log.error(
            f"Challenge ({type_2fa}) with ({email or username}) to {bridge_meta} bridge has failed."
        )

    return web.json_response(data=response, status=status)


@routes.post("/v1/gupshup/register")
async def gupshup_register(request: web.Request) -> web.Response:
    """
    Register a gupshup app
    ---
    summary:        Sending information you can register a new gupshup line.

    tags:
        - Bridge

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
        description: A json with `user_email` or `user_id` of the puppet
                     (You must use one of them), `gs_app_name`, `gs_app_phone`, `api_key`, `app_id`
        content:
          application/json:
              schema:
                type: object
                properties:
                    user_email:
                        description: "Puppet email"
                        type: string
                    user_id:
                        description: "Puppet user_id"
                        type: string
                    gs_app_name:
                        description: "Name of the application in gupshup platform"
                        type: string
                    gs_app_phone:
                        description: "Phone of the guspshup application"
                        type: string
                    api_key:
                        description: "Api key provided by gupshup partner"
                        type: string
                    app_id:
                        description: "Gupshup application id registered in gupshup platform"
                        type: string
                required:
                    - gs_app_name
                    - gs_app_phone
                    - api_key
                    - app_id
                example:
                    user_email: nobody@somewhere.com
                    user_id: '@acd1:somewhere.com'
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


@routes.patch("/v1/gupshup/update")
async def gupshup_update(request: web.Request) -> web.Response:
    """
    Update a gupshup app
    ---
    summary: Sending information you can update a gupshup line.

    tags:
        - Bridge

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
        description: A json with `user_email` or `user_id` of the puppet
                     (You must use one of them), `app_name`, `api_key`
        content:
          application/json:
              schema:
                type: object
                properties:
                    user_email:
                        description: "Puppet email"
                        type: string
                    user_id:
                        description: "Puppet user_id"
                        type: string
                    app_name:
                        description: "Name of the application in gupshup platform"
                        type: string
                    api_key:
                        description: "Api key provided by gupshup partner"
                        type: string
                example:
                    user_email: nobody@somewhere.com
                    user_id: '@acd1:somewhere.com'
                    app_name: AppName
                    api_key: your_api_key

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/Conflict'
        '422':
            $ref: '#/components/responses/RequiredVariables'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response({"detail": {"data": None, "message": "Please provide some data"}})

    puppet = await _resolve_puppet_identifier(request=request)
    if puppet.bridge != "gupshup":
        return web.json_response({"detail": {"data": None, "message": "Bridge invalid"}})

    gupshup_data = await request.json()

    if not gupshup_data.get("api_key"):
        return web.json_response(
            {"detail": {"data": None, "message": "Please provide required variables"}}
        )

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    status, data = await bridge_connector.gupshup_update_app(
        user_id=puppet.custom_mxid, data={"api_key": gupshup_data.get("api_key")}
    )

    if status in [200, 201]:
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
    """
    ---
    summary:        Given a list of puppets, get his bridges status.
    tags:
        - Bridge

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
        status, response = await bridge_conector.ping(puppet.mxid)
        bridges_status.append(response)

    return web.json_response(data={"bridges_status": bridges_status})


@routes.post("/v1/logout")
async def logout(request: web.Request) -> web.Response:
    """
    ---
    summary:        Close connection of a previously logged-in bridge
    tags:
        - Bridge

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
        description: A json with `user_id`or `user_email` to unlog
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
                        user_email: "acd1@example.com"
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


@routes.post("/v1/meta/register")
async def meta_register(request: web.Request) -> web.Response:
    """
    Register an application in the Meta bridge.
    ---
    summary: Send information to register a new facebook or instagram Meta bridge.

    tags:
        - Bridge

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
        description: A json with `admin_user`, `meta_app_page_id`, `meta_outgoing_page_id`,
                    `meta_app_name`, `meta_page_access_token`
        content:
          application/json:
              schema:
                type: object
                properties:
                    meta_app_page_id:
                        description: "Id of the meta app"
                        type: string
                    meta_outgoing_page_id:
                        description: "Meta page id that will be use by send messages"
                        type: string
                    meta_app_name:
                        description: "Name of the application in Meta platform"
                        type: string
                    user_id:
                        description: "Puppet user_id"
                        type: string
                    user_email:
                        description: "Puppet email"
                        type: string
                    meta_page_access_token:
                        description: "Token of the meta app"
                        type: string
                required:
                    - meta_app_page_id
                    - meta_outgoing_page_id
                    - meta_app_name
                    - meta_page_access_token
                example:
                    meta_app_page_id: 123456789
                    meta_outgoing_page_id: 456789123
                    meta_app_name: AppName
                    user_id: '@acd1:somewhere.com'
                    user_email: nobody@somewhere.com
                    meta_page_access_token: 7a4QUR5UvYvZAfAQPO1Cwr3ZC

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '404':
            $ref: '#/components/responses/NotExist'
        '406':
            $ref: '#/components/responses/EmailError'
        '409':
            $ref: '#/components/responses/NoPuppetInPortal'

    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response(**NOT_DATA)

    meta_data = await request.json()

    meta_app_data = {
        "meta_app_name": meta_data.get("meta_app_name"),
        "meta_app_page_id": meta_data.get("meta_app_page_id"),
        "meta_outgoing_page_id": meta_data.get("meta_outgoing_page_id"),
        "admin_user": meta_data.get("user_id"),
        "meta_page_access_token": meta_data.get("meta_page_access_token"),
    }

    puppet = await _resolve_puppet_identifier(request=request)
    meta_app_data["notice_room"] = puppet.control_room_id

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    status, data = await bridge_connector.meta_register_app(
        user_id=puppet.custom_mxid, data=meta_app_data
    )

    return web.json_response(status=status, data=data)


@routes.patch("/v1/meta/update")
async def meta_update(request: web.Request) -> web.Response:
    """
    Update a meta app
    ---
    summary: Sending information you can update a meta line.

    tags:
        - Bridge

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
        description: A json with `user_email` or `user_id` of the puppet
                     (You must use one of them), `app_name`, `page_access_token`
        content:
          application/json:
              schema:
                type: object
                properties:
                    user_email:
                        description: "Puppet email"
                        type: string
                    user_id:
                        description: "Puppet user_id"
                        type: string
                    app_name:
                        description: "Name of the application in meta platform"
                        type: string
                    page_access_token:
                        description: "Token provided by meta partner"
                        type: string
                example:
                    user_email: nobody@somewhere.com
                    user_id: '@acd1:somewhere.com'
                    app_name: AppName
                    page_access_token: your_token

    responses:
        '400':
            $ref: '#/components/responses/BadRequest'
        '409':
            $ref: '#/components/responses/Conflict'
        '422':
            $ref: '#/components/responses/RequiredVariables'
    """
    await _resolve_user_identifier(request=request)

    if not request.body_exists:
        return web.json_response({"detail": {"data": None, "message": "Please provide some data"}})

    puppet = await _resolve_puppet_identifier(request=request)
    if puppet.bridge != "meta":
        return web.json_response({"detail": {"data": None, "message": "Bridge invalid"}})

    meta_data = await request.json()

    if not meta_data.get("app_name") and not meta_data.get("page_access_token"):
        return web.json_response(
            {"detail": {"data": None, "message": "Please provide required variables"}}
        )

    bridge_connector = ProvisionBridge(
        session=puppet.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )

    meta_app_data = {
        "app_name": meta_data.get("app_name"),
        "page_access_token": meta_data.get("page_access_token"),
    }

    status, data = await bridge_connector.meta_update_app(
        user_id=puppet.custom_mxid, data=meta_app_data
    )

    if status in [200, 201]:
        await puppet.save()

    return web.json_response(status=status, data=data)
