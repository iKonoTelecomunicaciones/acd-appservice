from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Dict

from aiohttp import web
from aiohttp_swagger3 import SwaggerDocs, SwaggerUiSettings
from markdown import markdown
from mautrix.types import Format, MessageType, TextMessageEventContent
from mautrix.util.logging import TraceLogger

from .. import VERSION
from ..agent_manager import AgentManager
from ..commands.handler import command_processor
from ..commands.typehint import CommandEvent
from ..config import Config
from ..http_client import HTTPClient, ProvisionBridge
from ..puppet import Puppet
from . import SUPPORTED_MESSAGE_TYPES
from .error_responses import (
    INVALID_EMAIL,
    INVALID_PHONE,
    MESSAGE_TYPE_NOT_SUPPORTED,
    NOT_DATA,
    NOT_EMAIL,
    REQUIRED_VARIABLES,
    SERVER_ERROR,
    USER_ALREADY_EXISTS,
    USER_DOESNOT_EXIST,
)

LOGIN_PENDING_PROMISES = {}
LOGOUT_PENDING_PROMISES = {}
MESSAGE_PENDING_PROMISES = {}


class ProvisioningAPI:
    """Clase que tiene todos los endpoints de la API"""

    log: TraceLogger = logging.getLogger("acd.provisioning")
    app: web.Application
    config: Config
    client: HTTPClient
    agent_manager: AgentManager
    bridge_connector: ProvisionBridge

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
        swagger.add_post(path="/v1/send_message", handler=self.send_message)
        swagger.add_get(path="/v1/link_phone", handler=self.link_phone, allow_head=False)
        swagger.add_get(path="/v1/ws_link_phone", handler=self.ws_link_phone, allow_head=False)

        # Commads endpoint
        swagger.add_post(path="/v1/cmd/pm", handler=self.pm)
        swagger.add_post(path="/v1/cmd/resolve", handler=self.resolve)
        swagger.add_post(path="/v1/cmd/state_event", handler=self.state_event)
        # cmd template sin pruebas
        swagger.add_post(path="/v1/cmd/template", handler=self.template)
        swagger.add_post(path="/v1/cmd/transfer", handler=self.transfer)
        swagger.add_post(path="/v1/cmd/transfer_user", handler=self.transfer_user)

        self.loop = asyncio.get_running_loop()

    async def create_user(self, request: web.Request) -> web.Response:
        """
        Receives a user_email and creates a user in the User table and its respective puppet
        ---
        summary: Creates a user in the platform to be able to scan the WhatsApp QR code and send messages later using the API endpoints.
        tags:
            - users

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
                    user_email: nobody@somewhere.com

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
                # NOTA: primero debe estar registrado el puppet en la db antes de crear la sala,
                # ya que para crear una sala se necesita la pk del puppet (para usarla como fk)
                control_room_id = await puppet.intent.create_room(
                    invitees=[self.config["bridges.mautrix.mxid"]]
                )
                puppet.control_room_id = control_room_id
                # Ahora si guardamos la sala de control en el puppet.control_room_id
                await puppet.save()
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
            - users

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
        await bridge_connector.ws_connect(user_id=puppet.custom_mxid, ws_customer=ws_customer)

        return ws_customer

    async def link_phone(self, request: web.Request) -> web.Response:
        """
        A QR code is requested to WhatsApp in order to login an email account with a phone number.
        ---
        summary:        Generates a QR code for an existing user in order to create a QR image and
                        link the WhatsApp number by scanning the QR code with the cell phone.
        tags:
            - users

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
        # Creamos un WebSocket para conectarnos con el bridge
        return web.json_response(
            **await self.bridge_connector.ws_connect(user_id=puppet.custom_mxid, easy_mode=True)
        )

    async def pm(self, request: web.Request) -> web.Response:
        """
        Command that allows send a message to a customer.
        ---
        summary:    It takes a phone number and a message,
                    and sends the message to the phone number.
        tags:
            - users

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
                  phone_number:
                    type: string
                  template_message:
                    type: string
                  template_name:
                    type: string
                  agent_id:
                    type: string
                example:
                    user_email: "nobody@somewhere.com"
                    phone_number: "573123456789"
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
        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data: Dict = await request.json()

        if not (
            data.get("phone_number")
            and data.get("template_message")
            and data.get("template_name")
            and data.get("user_email")
            and data.get("agent_id")
        ):
            return web.json_response(**REQUIRED_VARIABLES)

        email = data.get("user_email").lower()
        error_result = await self.validate_email(user_email=email)

        if error_result:
            return web.json_response(**error_result)

        # Obtenemos el puppet de este email si existe
        puppet: Puppet = await Puppet.get_by_email(email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        incoming_params = {
            "phone_number": data.get("phone_number"),
            "template_message": data.get("template_message"),
            "template_name": data.get("template_name"),
        }

        # Creating a fake command event and passing it to the command processor.
        fake_command = f"pm {json.dumps(incoming_params)}"
        cmd_evt = CommandEvent(
            cmd="pm",
            agent_manager=self.agent_manager,
            sender=data.get("agent_id"),
            room_id=None,
            text=fake_command,
        )
        cmd_evt.agent_manager.intent = puppet.intent
        cmd_evt.intent = puppet.intent
        result = await command_processor(cmd_evt=cmd_evt)
        return web.json_response(**result)

    async def resolve(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command resolving a chat, ejecting the supervisor and the agent.
        tags:
            - users

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

        if not (data.get("room_id") and data.get("user_id")):
            return web.json_response(**REQUIRED_VARIABLES)

        room_id = data.get("room_id")
        user_id = data.get("user_id")
        send_message = data.get("send_message") if data.get("send_message") else None
        bridge = data.get("bridge") if data.get("bridge") else None

        # Obtenemos el puppet de este email si existe
        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        args = ["resolve", room_id, user_id, send_message, bridge]

        self.log.debug(args)
        # Creating a fake command event and passing it to the command processor.
        cmd_evt = CommandEvent(
            cmd="resolve",
            agent_manager=self.agent_manager,
            sender=user_id,
            room_id=room_id,
            args=args,
        )
        cmd_evt.agent_manager.intent = puppet.intent
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def state_event(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command that sends a state event to matrix.
        tags:
            - users

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

        if not (data.get("room_id") and data.get("event_type")):
            return web.json_response(**REQUIRED_VARIABLES)

        incoming_params = {
            "room_id": data.get("room_id"),
            "event_type": data.get("event_type"),
        }

        # Si llega vacia la lista tags es porque se quieren limpiar los tags
        if data.get("tags") is not None:
            incoming_params["tags"] = data.get("tags")
        if data.get("content"):
            incoming_params["content"] = data.get("content")

        # Obtenemos el puppet de este email si existe
        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=data.get("room_id"))
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        # Creating a fake command event and passing it to the command processor.
        fake_command = f"state_event {json.dumps(incoming_params)}"
        cmd_evt = CommandEvent(
            cmd="state_event",
            agent_manager=self.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            text=fake_command,
        )
        cmd_evt.agent_manager.intent = puppet.intent
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def template(self, request: web.Request) -> web.Response:
        """
        ---
        summary: This command is used to send templates
        tags:
            - users

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
                  bridge:
                    type: string
                example:
                    room_id: "!duOWDQQCshKjQvbyoh:darknet"
                    template_name: "hola"
                    template_message: "Hola iKono!!"
                    bridge: "!wa"

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

        if not (
            data.get("room_id")
            and data.get("template_name")
            and data.get("template_message")
            and data.get("bridge")
        ):
            return web.json_response(**REQUIRED_VARIABLES)

        incoming_params = {
            "room_id": data.get("room_id"),
            "template_name": data.get("template_name"),
            "template_message": data.get("template_message"),
            "bridge": data.get("bridge"),
        }

        # Obtenemos el puppet de este email si existe
        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=data.get("room_id"))
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        # Creating a fake command event and passing it to the command processor.
        fake_command = f"template {json.dumps(incoming_params)}"
        cmd_evt = CommandEvent(
            cmd="template",
            agent_manager=self.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            text=fake_command,
        )
        cmd_evt.agent_manager.intent = puppet.intent
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def transfer(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command that transfers a client to an campaign_room.
        tags:
            - users

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
            agent_manager=self.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            args=args,
        )
        cmd_evt.agent_manager.intent = puppet.intent
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def transfer_user(self, request: web.Request) -> web.Response:
        """
        ---
        summary: Command that transfers a client from one agent to another.
        tags:
            - users

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
            agent_manager=self.agent_manager,
            sender=puppet.custom_mxid,
            room_id=None,
            args=args,
        )
        cmd_evt.agent_manager.intent = puppet.intent
        cmd_evt.intent = puppet.intent
        await command_processor(cmd_evt=cmd_evt)
        return web.json_response()

    async def send_message(self, request: web.Request) -> web.Response:
        """
        Send a message to the given whatsapp number (create a room or send to the existing room)
        ---
        summary: Send a message from the user account to a WhatsApp phone number.
        tags:
            - users

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

        phone = str(data.get("phone"))
        if not (phone.isdigit() and 5 <= len(phone) <= 15):
            return web.json_response(**INVALID_PHONE)

        msg_type = data.get("msg_type")
        message = data.get("message")
        phone = phone if phone.startswith("+") else f"+{phone}"

        status, response = await self.bridge_connector.pm(user_id=puppet.custom_mxid, phone=phone)
        if response.get("error"):
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
            event_id = await puppet.intent.send_message(room_id=customer_room_id, content=content)
        except Exception as e:
            self.log.exception(e)
            return web.json_response(**SERVER_ERROR)

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
