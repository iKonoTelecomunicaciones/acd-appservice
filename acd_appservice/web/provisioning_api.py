from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Dict, List

import aiohttp_cors
from aiohttp import web
from aiohttp_swagger3 import SwaggerDocs, SwaggerUiSettings
from markdown import markdown
from mautrix.types import (
    Format,
    MessageType,
    PowerLevelStateEventContent,
    RoomID,
    TextMessageEventContent,
    UserID,
)
from mautrix.util.logging import TraceLogger

from .. import VERSION
from ..commands.handler import command_processor
from ..commands.typehint import CommandEvent
from ..config import Config
from ..http_client import HTTPClient, ProvisionBridge
from ..message import Message
from ..puppet import Puppet
from . import SUPPORTED_MESSAGE_TYPES
from .error_responses import (
    BRIDGE_INVALID,
    INVALID_EMAIL,
    INVALID_PHONE,
    MESSAGE_NOT_FOUND,
    MESSAGE_TYPE_NOT_SUPPORTED,
    NOT_DATA,
    NOT_EMAIL,
    REQUIRED_VARIABLES,
    SERVER_ERROR,
    USER_ALREADY_EXISTS,
    USER_DOESNOT_EXIST,
)

LOGOUT_PENDING_PROMISES = {}


class ProvisioningAPI:
    """Clase que tiene todos los endpoints de la API"""

    log: TraceLogger = logging.getLogger("acd.provisioning")
    app: web.Application
    config: Config
    client: HTTPClient

    def __init__(self) -> None:
        self.app = web.Application()
        swagger = SwaggerDocs(
            self.app,
            title="ACD AppService documentation",
            version=VERSION,
            components=f"acd_appservice/web/components.yaml",
            swagger_ui_settings=SwaggerUiSettings(
                path="/docs",
                layout="BaseLayout",
            ),
        )

        swagger.add_post(path="/v1/create_user", handler=self.create_user)

        # Mautrix WhatsApp endpoints
        swagger.add_post(path="/v1/mautrix/send_message", handler=self.send_message)
        swagger.add_get(path="/v1/mautrix/link_phone", handler=self.link_phone, allow_head=False)
        swagger.add_get(
            path="/v1/mautrix/ws_link_phone", handler=self.ws_link_phone, allow_head=False
        )

        # Mautrix Gupshup endpoints
        swagger.add_post(path="/v1/gupshup/send_message", handler=self.send_message)
        swagger.add_post(path="/v1/gupshup/register", handler=self.gupshup_register)

        # Mautrix Instagram endpoints
        swagger.add_post(path="/v1/instagram/login", handler=self.instagram_login)
        swagger.add_post(path="/v1/instagram/challenge", handler=self.instagram_challenge)

        # General
        swagger.add_get(path="/v1/read_check", handler=self.read_check, allow_head=False)
        swagger.add_get(
            path="/v1/get_control_room", handler=self.get_control_room, allow_head=False
        )
        swagger.add_get(
            path="/v1/get_control_rooms", handler=self.get_control_rooms, allow_head=False
        )

        # Commads endpoint
        swagger.add_post(path="/v1/cmd/pm", handler=self.pm)
        swagger.add_post(path="/v1/cmd/resolve", handler=self.resolve)
        swagger.add_post(path="/v1/cmd/bulk_resolve", handler=self.bulk_resolve)
        swagger.add_post(path="/v1/cmd/state_event", handler=self.state_event)
        swagger.add_post(path="/v1/cmd/template", handler=self.template)
        swagger.add_post(path="/v1/cmd/transfer", handler=self.transfer)
        swagger.add_post(path="/v1/cmd/transfer_user", handler=self.transfer_user)

        # Configure default CORS settings.
        cors = aiohttp_cors.setup(
            self.app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                )
            },
        )

        for route in list(self.app.router.routes()):
            cors.add(route)

        # Options
        # Aqui se agregan todos los los endpoints de metodo POST
        swagger.add_options(path="/v1/cmd/pm", handler=self.options)
        swagger.add_options(path="/v1/cmd/resolve", handler=self.options)
        swagger.add_options(path="/v1/cmd/bulk_resolve", handler=self.options)
        swagger.add_options(path="/v1/cmd/state_event", handler=self.options)
        swagger.add_options(path="/v1/cmd/template", handler=self.options)
        swagger.add_options(path="/v1/cmd/transfer", handler=self.options)
        swagger.add_options(path="/v1/cmd/transfer_user", handler=self.options)
        swagger.add_options(path="/v1/mautrix/send_message", handler=self.options)
        swagger.add_options(path="/v1/gupshup/send_message", handler=self.options)
        swagger.add_options(path="/v1/gupshup/register", handler=self.options)
        swagger.add_options(path="/v1/instagram/login", handler=self.options)
        swagger.add_options(path="/v1/instagram/challenge", handler=self.options)

        self.loop = asyncio.get_running_loop()

    @property
    def _acao_headers(self) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Authorization, Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }

    @property
    def _headers(self) -> dict[str, str]:
        return {
            **self._acao_headers,
            "Content-Type": "application/json",
        }

    async def options(self, _: web.Request):
        return web.Response(status=200, headers=self._headers)

    async def create_user(self, request: web.Request) -> web.Response:
        """
        Receives a user_email and creates a user in the User table and its respective puppet
        ---
        summary: Creates a user in the platform to be able to scan the WhatsApp QR code and send messages later using the API endpoints.
        tags:
            - ACD API

        requestBody:
          required: true
          description: A json with `user_email`
          content:
            application/json:
              schema:
                type: object
                properties:
                  user_email:
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

        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data = await request.json()

        error_result = await self.validate_email(user_email=data.get("user_email"))

        if error_result:
            return web.json_response(**error_result)

        email = data.get("user_email").lower()

        # Si llega sala de control es porque estamos haciendo la migración de un acd viejo
        control_room_id: RoomID = data.get("control_room_id")
        menubot_id: UserID = data.get("menubot_id")
        # Los bridge posibles a enviar son:
        # mautrix
        # instagram
        # gupshup
        bridge: str = data.get("bridge") or "mautrix"

        # Obtenemos el puppet de este email si existe
        puppet = await Puppet.get_by_email(email)

        if email != self.config["appservice.email"] and not puppet:
            # Si no existe creamos un puppet para este email

            # Primero obtenemos el siguiente puppet
            next_puppet = await Puppet.get_next_puppet()
            if next_puppet is None:
                return web.json_response(**SERVER_ERROR)
            try:
                # Creamos el puppet con el siguiente pk
                puppet: Puppet = await Puppet.get_by_pk(pk=next_puppet, email=email)
                puppet.email = email
                # Obtenemos el mxid correspondiente para este puppet @acd*:localhost
                puppet.custom_mxid = Puppet.get_mxid_from_id(puppet.pk)
                await puppet.save()
                # Inicializamos el intent de este puppet
                puppet.intent = puppet._fresh_intent()
                # Guardamos el puppet para poder utilizarlo en otras partes del código
                # Sincronizamos las salas del puppet, si es que ya existía en Matrix
                # sin que nosotros nos diéramos cuenta
                await puppet.sync_joined_rooms_in_db()

                # Si no se envio sala de control, entonces creamos una
                if not control_room_id:
                    # NOTA: primero debe estar registrado el puppet en la db antes de crear la sala,
                    # ya que para crear una sala se necesita la pk del puppet (para usarla como fk)
                    invitees = [
                        self.config[f"bridges.{bridge}.mxid"],
                        self.config["bridge.provisioning.admin"],
                    ]
                    if menubot_id:
                        invitees.append(menubot_id)

                    control_room_id = await puppet.intent.create_room(
                        name=f"CONTROL ROOM ({puppet.email})",
                        topic="Control room",
                        invitees=invitees,
                    )
                    power_level_content = PowerLevelStateEventContent(
                        users={
                            puppet.custom_mxid: 100,
                            self.config["bridge.provisioning.admin"]: 100,
                        }
                    )
                    await puppet.intent.set_power_levels(
                        room_id=control_room_id, content=power_level_content
                    )

                puppet.control_room_id = control_room_id
                await puppet.room_manager.save_room(
                    room_id=control_room_id, selected_option=None, puppet_mxid=puppet.mxid
                )
                # Registramos el bridge al que pertence el puppet
                puppet.bridge = bridge
                # Ahora si guardamos la sala de control en el puppet.control_room_id
                await puppet.save()
                # Si quieres configurar el estado inicial de los puppets, puedes hacerlo en esta
                # funcion
                await puppet.sync_puppet_account()
            except Exception as e:
                self.log.exception(e)
                return web.json_response(**SERVER_ERROR)
        else:
            # Si el correo pertenece bot principal, entonces decimos que ya existe registrado
            return web.json_response(**USER_ALREADY_EXISTS)

        response = {
            "user_id": puppet.custom_mxid,
            "control_room_id": puppet.control_room_id,
            "email": puppet.email,
        }

        return web.json_response(response, status=201)

    async def ws_link_phone(self, request: web.Request) -> web.Response:
        """
        A QR code is requested to WhatsApp in order to login an email account with a phone number.
        ---
        summary:        Generates a QR code for an existing user in order to create a QR image and
                        link the WhatsApp number by scanning the QR code with the cell phone.
        description:    This creates a `WebSocket` to which you must connect, you will be sent the
                        `qrcode` that you must scan to make a successful connection to `WhatsApp`, if
                        you do not login in time, the connection will be terminated by `timeout`.
        tags:
            - ACD API

        parameters:
        - in: query
          name: user_email
          schema:
            type: string
          required: true
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

        user_email = request.rel_url.query.get("user_email")

        error_result = await self.validate_email(user_email=user_email)

        if error_result:
            return web.json_response(**error_result)

        puppet: Puppet = await Puppet.get_by_email(user_email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        # Creamos una conector con el bridge
        bridge_connector = ProvisionBridge(session=self.client.session, config=self.config)
        # Creamos un WebSocket para conectarnos con el bridge
        await bridge_connector.mautrix_ws_connect(puppet=puppet, ws_customer=ws_customer)

        return ws_customer

    async def link_phone(self, request: web.Request) -> web.Response:
        """
        A QR code is requested to WhatsApp in order to login an email account with a phone number.
        ---
        summary:        Generates a QR code for an existing user in order to create a QR image and
                        link the WhatsApp number by scanning the QR code with the cell phone.
        tags:
            - ACD API

        parameters:
        - in: query
          name: user_email
          schema:
            type: string
          required: true
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

        user_email = request.rel_url.query.get("user_email")

        error_result = await self.validate_email(user_email=user_email)

        if error_result:
            return web.json_response(**error_result)

        puppet: Puppet = await Puppet.get_by_email(user_email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        # Creamos una conector con el bridge
        bridge_connector = ProvisionBridge(session=self.client.session, config=self.config)
        # Creamos un WebSocket para conectarnos con el bridge
        return web.json_response(
            **await bridge_connector.mautrix_ws_connect(puppet=puppet, easy_mode=True)
        )

    async def instagram_login(self, request: web.Request) -> web.Response:
        """
        Login to Instagram Bridge.
        ---
        summary:        Sign in with your instagram account to start receiving messages.

        tags:
            - Instagram

        requestBody:
          required: true
          description: A json with `user_email`
          content:
            application/json:
              schema:
                type: object
                properties:
                  user_email:
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

        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data = await request.json()
        user_email = data.get("user_email")
        username = data.get("username")
        password = data.get("password")

        error_result = await self.validate_email(user_email=user_email)

        if error_result:
            return web.json_response(**error_result)

        puppet: Puppet = await Puppet.get_by_email(user_email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        bridge_connector = ProvisionBridge(
            session=self.client.session, config=self.config, bridge=puppet.bridge
        )

        response = await bridge_connector.instagram_login(
            user_id=puppet.custom_mxid, username=username, password=password
        )

        return web.json_response(data=response)

    async def gupshup_register(self, request: web.Request) -> web.Response:
        """
        Register a gupshup app
        ---
        summary:        Sending information you can register a new gupshup line.

        tags:
            - Gupshup

        requestBody:
          required: true
          description: A json with `user_email`
          content:
            application/json:
              schema:
                type: object
                properties:
                  user_email:
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

        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data = await request.json()
        user_email = data.get("user_email")

        gs_app_data = {
            "gs_app_name": data.get("gs_app_name"),
            "gs_app_phone": data.get("gs_app_phone"),
            "api_key": data.get("api_key"),
            "app_id": data.get("app_id"),
        }

        error_result = await self.validate_email(user_email=user_email)

        if error_result:
            return web.json_response(**error_result)

        puppet: Puppet = await Puppet.get_by_email(user_email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        bridge_connector = ProvisionBridge(
            session=self.client.session, config=self.config, bridge=puppet.bridge
        )

        status, data = await bridge_connector.gupshup_register_app(
            user_id=puppet.custom_mxid, data=gs_app_data
        )

        if status in [200, 201]:
            puppet.phone = data.get("gs_app_phone")
            await puppet.save()

        return web.json_response(status=status, data=data)

    async def instagram_challenge(self, request: web.Request) -> web.Response:
        """
        Solve the instagram login challenge.
        ---
        summary:        By sending the code that instagram sent you, you can finish the login process.

        tags:
            - Instagram

        requestBody:
          required: true
          description: A json with `user_email`
          content:
            application/json:
              schema:
                type: object
                properties:
                  user_email:
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

        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data = await request.json()
        user_email = data.get("user_email")
        code = data.get("code")

        error_result = await self.validate_email(user_email=user_email)

        if error_result:
            return web.json_response(**error_result)

        puppet: Puppet = await Puppet.get_by_email(user_email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        bridge_connector = ProvisionBridge(
            session=self.client.session, config=self.config, bridge=puppet.bridge
        )

        response = await bridge_connector.instagram_challenge(
            user_id=puppet.custom_mxid, code=code
        )

        return web.json_response(data=response)

    async def read_check(self, request: web.Request) -> web.Response:
        """
        ---
        summary:        Check if a message has been read
        tags:
            - ACD API

        parameters:
        - in: query
          name: event_id
          schema:
            type: string
          required: true
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

    async def get_control_room(self, request: web.Request) -> web.Response:
        """
        ---
        summary:        Given a room obtains the acd control room*.
        tags:
            - Puppet utils

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

    async def get_control_rooms(self, request: web.Request) -> web.Response:
        """
        ---
        summary:        Get the acd control rooms.
        tags:
            - Puppet utils

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

    async def pm(self, request: web.Request) -> web.Response:
        """
        Command that allows send a message to a customer.
        ---
        summary:    It takes a phone number and a message,
                    and sends the message to the phone number.
        tags:
            - Commands

        requestBody:
          required: true
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
                    bridge: "!wa"

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
        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data: Dict = await request.json()

        if not (
            data.get("customer_phone")
            and data.get("template_message")
            and data.get("template_name")
            and (data.get("user_email") or data.get("company_phone"))
            and data.get("agent_id")
        ):
            return web.json_response(**REQUIRED_VARIABLES)

        if data.get("user_email"):
            email = data.get("user_email").lower()
            error_result = await self.validate_email(user_email=email)
            if error_result:
                return web.json_response(**error_result)

            puppet: Puppet = await Puppet.get_by_email(email)
            if not puppet:
                return web.json_response(**USER_DOESNOT_EXIST)

        if data.get("company_phone"):
            company_phone = data.get("company_phone").replace("+", "")
            puppet: Puppet = await Puppet.get_by_phone(company_phone)
            if not puppet:
                return web.json_response(**USER_DOESNOT_EXIST)

        incoming_params = {
            "phone_number": data.get("customer_phone"),
            "template_message": data.get("template_message"),
            "template_name": data.get("template_name"),
            "bridge": data.get("bridge")
            or self.config[
                "bridges.mautrix.prefix"
            ],  # TODO eliminar  `or self.config["bridges.mautrix.prefix"]` cuando todos los clientes tengan el front actualizado
        }

        # Creating a fake command event and passing it to the command processor.
        fake_command = f"pm {json.dumps(incoming_params)}"
        cmd_evt = CommandEvent(
            cmd="pm",
            agent_manager=puppet.agent_manager,
            sender=data.get("agent_id"),
            room_id=None,
            text=fake_command,
        )
        cmd_evt.intent = puppet.intent

        try:
            result = await command_processor(cmd_evt=cmd_evt)
        except Exception as e:
            return web.json_response(status=500, data={"error": str(e)})

        return web.json_response(**result)

    async def resolve(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command resolving a chat, ejecting the supervisor and the agent.
        tags:
            - Commands

        requestBody:
          required: true
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

        args = ["resolve", room_id, user_id, send_message, self.config[f"bridges.{bridge}.prefix"]]

        # Creating a fake command event and passing it to the command processor.
        cmd_evt = CommandEvent(
            cmd="resolve",
            agent_manager=puppet.agent_manager,
            sender=user_id,
            room_id=room_id,
            args=args,
        )
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def bulk_resolve(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command to resolve chats en bloc, expelling the supervisor and the agent.
        tags:
            - Commands

        requestBody:
          required: true
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
        room_block = self.config["utils.room_blocks"]

        # Dividimos las salas en sublistas y cada sublista de longitud room_block
        list_room_ids = [room_ids[i : i + room_block] for i in range(0, len(room_ids), room_block)]
        for room_ids in list_room_ids:
            tasks = []
            for room_id in room_ids:
                # Obtenemos el puppet de este email si existe
                puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
                if not puppet:
                    # Si esta sala no tiene puppet entonces pasamos a la siguiente
                    # la sala sin puppet no será resuelta.
                    self.log.warning(
                        f"The room {room_id} has not been resolved because the puppet was not found"
                    )
                    continue

                # Obtenemos el bridge de la sala dado el room_id
                bridge = await puppet.room_manager.get_room_bridge(room_id=room_id)

                if not bridge:
                    # Si esta sala no tiene bridge entonces pasamos a la siguiente
                    # la sala sin bridge no será resuelta.
                    self.log.warning(
                        f"The room {room_id} has not been resolved because I didn't found the bridge"
                    )
                    continue

                # Con el bridge obtenido, podremos sacar su prefijo y así luego en el comando
                # resolve podremos enviar un template si así lo queremos
                bridge_prefix = self.config[f"bridges.{bridge}.prefix"]

                args = ["resolve", room_id, user_id, send_message, bridge_prefix]

                self.log.debug(args)
                # Creating a fake command event and passing it to the command processor.
                cmd_evt = CommandEvent(
                    cmd="resolve",
                    agent_manager=puppet.agent_manager,
                    sender=user_id,
                    room_id=room_id,
                    args=args,
                )

                # Debemos actualizar el intent del agent_manager y el intent para que lo que se ejecute
                # dentro de estas tareas sean cotextos correctos independientes de cada puppet
                # ósea, el puppet que corresponde a la sala que se va a resolver ;)
                cmd_evt.intent = puppet.intent
                task = asyncio.create_task(command_processor(cmd_evt=cmd_evt))
                tasks.append(task)

            await asyncio.gather(*tasks)

        return web.json_response(text="ok")

    async def state_event(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command that sends a state event to matrix.
        tags:
            - Commands

        requestBody:
          required: true
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
        fake_command = f"state_event {json.dumps(incoming_params)}"
        cmd_evt = CommandEvent(
            cmd="state_event",
            agent_manager=puppet.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            text=fake_command,
        )
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def template(self, request: web.Request) -> web.Response:
        """
        ---
        summary: This command is used to send templates
        tags:
            - Commands

        requestBody:
          required: true
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
        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data: Dict = await request.json()

        if not (
            data.get("room_id") and data.get("template_name") and data.get("template_message")
        ):
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
        fake_command = f"template {json.dumps(incoming_params)}"
        cmd_evt = CommandEvent(
            cmd="template",
            agent_manager=puppet.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            text=fake_command,
        )
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def transfer(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command that transfers a client to an campaign_room.
        tags:
            - Commands

        requestBody:
          required: true
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

        args = ["transfer", customer_room_id, campaign_room_id]

        # Creating a fake command event and passing it to the command processor.
        cmd_evt = CommandEvent(
            cmd="transfer",
            agent_manager=puppet.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            args=args,
        )
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def transfer_user(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command that transfers a client from one agent to another.
        tags:
            - Commands

        requestBody:
          required: true
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
                example:
                    customer_room_id: "!duOWDQQCshKjQvbyoh:darknet"
                    target_agent_id: "@agente1:darknet"

        responses:
            '200':
                $ref: '#/components/responses/PmSuccessful'
            '400':
                $ref: '#/components/responses/BadRequest'
            '404':
                $ref: '#/components/responses/NotExist'
        """
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

        args = ["transfer_user", customer_room_id, target_agent_id]

        # Creating a fake command event and passing it to the command processor.
        cmd_evt = CommandEvent(
            cmd="transfer_user",
            agent_manager=puppet.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            args=args,
        )
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def send_message(self, request: web.Request) -> web.Response:
        """
        Send a message to the given whatsapp number (create a room or send to the existing room)
        ---
        summary: Send a message from the user account to a WhatsApp phone number.
        tags:
            - ACD API

        requestBody:
          required: true
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
            and data.get("user_email")
        ):
            return web.json_response(**REQUIRED_VARIABLES)

        if not data.get("msg_type") in SUPPORTED_MESSAGE_TYPES:
            return web.json_response(**MESSAGE_TYPE_NOT_SUPPORTED)

        email = data.get("user_email").lower()

        error_result = await self.validate_email(user_email=email)

        if error_result:
            return web.json_response(**error_result)

        # Obtenemos el puppet de este email si existe
        puppet: Puppet = await Puppet.get_by_email(email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        if puppet.bridge != bridge:
            return web.json_response(**BRIDGE_INVALID)

        phone = str(data.get("phone"))
        if not (phone.isdigit() and 5 <= len(phone) <= 15):
            return web.json_response(**INVALID_PHONE)

        msg_type = data.get("msg_type")
        message = data.get("message")
        phone = phone if phone.startswith("+") else f"+{phone}"

        # Creamos una conector con el bridge
        bridge_connector = ProvisionBridge(
            session=self.client.session, config=self.config, bridge=bridge
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

        # Aqui se pueden tener los demas tipos de mensaje cuando se piensen implementar
        # if msg_type == "image":
        #     content = MediaMessageEventContent(
        #         msgtype=MessageType.IMAGE,
        #         body=message,
        #         format=Format.HTML,
        #         formatted_body=message,
        #     )

        try:
            if self.config[f"bridges.{bridge}.send_template_command"]:

                # TODO Si otro bridge debe enviar templates, hacer generico este metodo (gupshup_template)
                status, data = await bridge_connector.gupshup_template(
                    room_id=customer_room_id, user_id=puppet.custom_mxid, template=message
                )
                if not status in [200, 201]:
                    return web.json_response(status=status, data=data)

                event_id = data.get("event_id")
            else:
                event_id = await puppet.intent.send_message(
                    room_id=customer_room_id, content=content
                )
        except Exception as e:
            self.log.exception(e)
            return web.json_response(**SERVER_ERROR)

        try:
            # Registramos el mensaje en la db
            await Message.insert_msg(
                event_id=event_id,
                room_id=customer_room_id,
                sender=puppet.custom_mxid,
                receiver=phone,
                timestamp_send=datetime.timestamp(datetime.utcnow()),
            )
        except Exception as e:
            self.log.exception(e)

        return web.json_response(
            data={
                "detail": "The message has been sent (probably)",
                "event_id": event_id,
                "room_id": customer_room_id,
            },
            status=201,
        )

    async def validate_email(self, user_email: str) -> Dict:
        """It checks if the email is valid

        Parameters
        ----------
        user_email : str
            The email address to validate.

        Returns
        -------
            A dictionary with a key of "error" "

        """
        if not user_email:
            return NOT_EMAIL

        email = user_email.lower()
        if not re.match(self.config["utils.regex_email"], email):
            return INVALID_EMAIL

    # async def unlink_phone(self, request: web.Request) -> web.Response:
    #     """
    #     Given a user_email send a `!wa logout` bridge command to close Whatsapp communication
    #     ---
    #     summary: Disconnects the linked WhatsApp number from the platform in order to link another number.
    #     tags:
    #         - users

    #     requestBody:
    #       required: true
    #       description: A json with `user_email`
    #       content:
    #         application/json:
    #           schema:
    #             type: object
    #             properties:
    #               user_email:
    #                 type: string
    #             example:
    #                 user_email: nobody@somewhere.com

    #     responses:
    #         '200':
    #             $ref: '#/components/responses/OK'
    #         '400':
    #             $ref: '#/components/responses/BadRequest'
    #         '404':
    #             $ref: '#/components/responses/NotExist'
    #         '422':
    #             $ref: '#/components/responses/ErrorData'
    #         '429':
    #             $ref: '#/components/responses/TooManyRequests'
    #     """

    #     if not request.body_exists:
    #         return web.json_response(**NOT_DATA)

    #     data = await request.json()

    #     if not data.get("user_email"):
    #         return web.json_response(**NOT_EMAIL)

    #     email = data.get("user_email").lower()
    #     if not re.match(self.config["utils.regex_email"], email):
    #         return web.json_response(**INVALID_EMAIL)

    #     if not await User.user_exists(email):
    #         return web.json_response(**USER_DOESNOT_EXIST)

    #     user, _ = await self.utils.create_puppet_and_user(email=email)

    #     try:
    #         logout_command = self.config["bridge.commands.logout"]
    #         await user.send_command(logout_command)
    #     except Exception as e:
    #         self.log.error(f"Message not sent: {e}")
    #         return web.json_response(**MESSAGE_NOT_SENT)

    #     if user.room_id in LOGOUT_PENDING_PROMISES:
    #         return web.json_response(**REQUEST_ALREADY_EXISTS)

    #     pending_promise = self.loop.create_future()
    #     LOGOUT_PENDING_PROMISES[user.room_id] = pending_promise

    #     promise_response = await asyncio.create_task(
    #         self.check_promise(user.room_id, pending_promise)
    #     )

    #     if promise_response.get("msgtype") == "logged_out":
    #         response = {
    #             "data": {
    #                 "message": promise_response.get("response"),
    #             },
    #             "status": 200,
    #         }
    #     elif promise_response.get("msgtype") == "not_logged_in":
    #         response = {
    #             "data": {
    #                 "message": promise_response.get("response"),
    #             },
    #             "status": 200,
    #         }
    #     elif promise_response.get("msgtype") == "error":
    #         # When an error occurred the 'promise_response.get("response")' has data and status
    #         # look out this error template in 'error_responses.py'
    #         response = promise_response.get("response")

    #     del LOGOUT_PENDING_PROMISES[user.room_id]

    #     return web.json_response(**response)
