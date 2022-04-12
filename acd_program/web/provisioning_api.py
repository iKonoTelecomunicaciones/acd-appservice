import asyncio
import logging
import re
from datetime import datetime

from aiohttp import web
from aiohttp_swagger3 import SwaggerDocs, SwaggerUiSettings
from mautrix.types.event.message import MessageType
from mautrix.util.logging import TraceLogger

from acd_program.config import Config
from acd_program.user import User
from acd_program.web import SUPPORTED_MESSAGE_TYPES
from acd_program.web.error_responses import (INVALID_EMAIL, INVALID_PHONE,
                                             MESSAGE_NOT_SENT,
                                             MESSAGE_TYPE_NOT_SUPPORTED,
                                             NOT_DATA, NOT_EMAIL,
                                             REQUEST_ALREADY_EXISTS,
                                             REQUIRED_VARIABLES, TIMEOUT_ERROR,
                                             USER_ALREADY_EXISTS,
                                             USER_DOESNOT_EXIST)
from acd_program.web.utils import Utils

from .. import VERSION

LOGIN_PENDING_PROMISES = {}
LOGOUT_PENDING_PROMISES = {}
MESSAGE_PENDING_PROMISES = {}


class ProvisioningAPI:
    """Clase que tiene todos los endpoints de la API"""

    log: TraceLogger = logging.getLogger("mau.web.provisioning")
    app: web.Application
    config: Config

    def __init__(self) -> None:
        self.app = web.Application()
        self.utils = Utils()

        swagger = SwaggerDocs(
            self.app,
            title="WAPI documentation",
            version=VERSION,
            components=f"acd_program/web/components.yaml",
            swagger_ui_settings=SwaggerUiSettings(
                path="/docs",
                layout="BaseLayout",
            ),
        )
        swagger.add_routes(
            [
                # Región de autenticación
                web.post("/create_user", self.create_user),
                web.post("/link_phone", self.link_phone),
                web.post("/unlink_phone", self.unlink_phone),
                # Región de mensajería
                web.post("/send_message", self.send_message),
            ]
        )
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

        if not data.get("user_email"):
            return web.json_response(**NOT_EMAIL)

        email = data.get("user_email").lower()
        if not re.match(self.config["utils.regex_email"], email):
            return web.json_response(**INVALID_EMAIL)
        if await User.user_exists(email):
            return web.json_response(**USER_ALREADY_EXISTS)

        user, pupp = await self.utils.create_puppet_and_user(email=email)
        pupp = await user.get_puppet()
        if not user.room_id:
            room_id = await pupp.intent.create_room(
                invitees=self.config["bridge.invitees_to_rooms"]
            )
            self.log.debug(
                f"user {user.mxid} and his room {room_id} - "
                f"{self.config['bridge.invitees_to_rooms']} have been created and invited"
            )
            user.room_id = room_id
        await user.save()
        response = {
            "message": "User has been created",
        }
        return web.json_response(response, status=201)

    async def link_phone(self, request: web.Request) -> web.Response:
        """
        Given a user_email send a `!wa login` bridge command to stablish Whatsapp communication
        ---
        summary: Generates a QR code for an existing user in order to create a QR image and link the WhatsApp number by scanning the QR code with the cell phone.
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
                $ref: '#/components/responses/QrGenerated'
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

        data = await request.json()

        if not data.get("user_email"):
            return web.json_response(**NOT_EMAIL)

        email = data.get("user_email").lower()
        if not re.match(self.config["utils.regex_email"], email):
            return web.json_response(**INVALID_EMAIL)

        if not await User.user_exists(email):
            return web.json_response(**USER_DOESNOT_EXIST)

        user, _ = await self.utils.create_puppet_and_user(email=email)

        try:
            login_command = self.config["bridge.commands.login"]
            await user.send_command(login_command)
        except Exception as e:
            self.log.error(f"Message not sent: {e}")
            return web.json_response(**MESSAGE_NOT_SENT)

        if user.room_id in LOGIN_PENDING_PROMISES:
            return web.json_response(**REQUEST_ALREADY_EXISTS)

        pending_promise = self.loop.create_future()
        LOGIN_PENDING_PROMISES[user.room_id] = pending_promise

        promise_response = await asyncio.create_task(
            self.check_promise(user.room_id, pending_promise)
        )

        if promise_response.get("msgtype") == "qr_code":
            response = {
                "data": {
                    "qr": promise_response.get("response"),
                    "message": "QR has been generated",
                },
                "status": 201,
            }
        elif promise_response.get("msgtype") == "logged_in":
            response = {
                "data": {
                    "error": promise_response.get("response"),
                },
                "status": 422,
            }
        elif promise_response.get("msgtype") == "error":
            # When an error occurred the 'promise_response.get("response")' has data and status
            # look out this error template in 'error_responses.py'
            response = promise_response.get("response")

        del LOGIN_PENDING_PROMISES[user.room_id]

        return web.json_response(**response)

    async def unlink_phone(self, request: web.Request) -> web.Response:
        """
        Given a user_email send a `!wa logout` bridge command to close Whatsapp communication
        ---
        summary: Disconnects the linked WhatsApp number from the platform in order to link another number.
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
            '200':
                $ref: '#/components/responses/OK'
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

        data = await request.json()

        if not data.get("user_email"):
            return web.json_response(**NOT_EMAIL)

        email = data.get("user_email").lower()
        if not re.match(self.config["utils.regex_email"], email):
            return web.json_response(**INVALID_EMAIL)

        if not await User.user_exists(email):
            return web.json_response(**USER_DOESNOT_EXIST)

        user, _ = await self.utils.create_puppet_and_user(email=email)

        try:
            logout_command = self.config["bridge.commands.logout"]
            await user.send_command(logout_command)
        except Exception as e:
            self.log.error(f"Message not sent: {e}")
            return web.json_response(**MESSAGE_NOT_SENT)

        if user.room_id in LOGOUT_PENDING_PROMISES:
            return web.json_response(**REQUEST_ALREADY_EXISTS)

        pending_promise = self.loop.create_future()
        LOGOUT_PENDING_PROMISES[user.room_id] = pending_promise

        promise_response = await asyncio.create_task(
            self.check_promise(user.room_id, pending_promise)
        )

        if promise_response.get("msgtype") == "logged_out":
            response = {
                "data": {
                    "message": promise_response.get("response"),
                },
                "status": 200,
            }
        elif promise_response.get("msgtype") == "not_logged_in":
            response = {
                "data": {
                    "message": promise_response.get("response"),
                },
                "status": 200,
            }
        elif promise_response.get("msgtype") == "error":
            # When an error occurred the 'promise_response.get("response")' has data and status
            # look out this error template in 'error_responses.py'
            response = promise_response.get("response")

        del LOGOUT_PENDING_PROMISES[user.room_id]

        return web.json_response(**response)

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
            '200':
                $ref: '#/components/responses/OK'
            '400':
                $ref: '#/components/responses/BadRequest'
            '404':
                $ref: '#/components/responses/NotExist'
            '422':
                $ref: '#/components/responses/ErrorData'
            '429':
                $ref: '#/components/responses/TooManyRequests'
        """

        # Región para validar que la información enviada sea completa y correcta
        if not request.body_exists:
            return web.json_response(**NOT_DATA)

        data = await request.json()
        if (
            not data.get("phone")
            or not data.get("message")
            or not data.get("user_email")
            or not data.get("msg_type")
        ):
            return web.json_response(**REQUIRED_VARIABLES)
        if not data.get("msg_type") in SUPPORTED_MESSAGE_TYPES:
            return web.json_response(**MESSAGE_TYPE_NOT_SUPPORTED)

        email = data.get("user_email").lower()
        if not re.match(self.config["utils.regex_email"], email):
            return web.json_response(**INVALID_EMAIL)
        if not await User.user_exists(email):
            return web.json_response(**USER_DOESNOT_EXIST)

        phone = str(data.get("phone"))
        if not (phone.isdigit() and 5 <= len(phone) <= 15):
            return web.json_response(**INVALID_PHONE)

        # Fin región de validación

        msg_type = data.get("msg_type")
        message = data.get("message")
        phone = phone if phone.startswith("+") else f"+{phone}"
        user = await User.get_by_email(email)

        pending_promise = self.loop.create_future()

        # cargamos el diccionario con los datos necesarios para procesar las solicitudes
        # de envió de mensaje
        MESSAGE_PENDING_PROMISES[phone] = {
            "user": user,
            "message": message,
            "msg_type": None,
            "pending_promise": pending_promise,
        }

        # Se agrega la promesa en este diccionario para poder hacer seguimiento
        # al usuario en cuestión y saber si esta logueado
        LOGOUT_PENDING_PROMISES[user.room_id] = pending_promise

        if msg_type == "text":
            MESSAGE_PENDING_PROMISES[phone]["msg_type"] = MessageType.TEXT
        # TODO agregar los diferentes tipos de mensaje en las siguientes lineas
        # if msg_type == "audio":
        #     MESSAGE_PENDING_PROMISES[phone]["msg_type"] = MessageType.AUDIO
        # if msg_type == "image":
        #     MESSAGE_PENDING_PROMISES[phone]["msg_type"] = MessageType.IMAGE

        # Creamos el comando que será enviado a la sala del user para
        pm_command = f"{self.config['bridge.commands.create_room']} {phone}"
        await user.send_command(pm_command)

        # Se crea la tarea que va a supervisar los notices generados por el bridge
        promise_response = await asyncio.create_task(self.check_promise(phone, pending_promise))

        # Cuando el promise_response este lleno, podrá tener diferentes datos
        # promise_response = {
        #     "state": True, # Si llega true es porque todo salió bien, falso trae algún error
        #     "message": "Any message", # Los mensajes capturados cuando se resuelve la promesa
        # }
        if promise_response.get("state"):
            response = {
                "data": {"message": promise_response.get("message")},
                "status": 200,
            }
        elif promise_response.get("msgtype") == "not_logged_in":
            response = {
                "data": {
                    "message": promise_response.get("response"),
                },
                "status": 422,
            }
        else:
            response = {
                "data": {
                    "message": promise_response.get("message")
                    if promise_response.get("message")
                    else "WhatsApp server has not responded"
                },
                "status": 422,
            }

        del MESSAGE_PENDING_PROMISES[phone]
        del LOGOUT_PENDING_PROMISES[user.room_id]

        return web.json_response(**response)

    async def check_promise(self, key_promise: str, pending_response) -> tuple:
        """Verify that QR code was generated.

        Parameters
        ----------
        key_promise
            key for the promise in the respective dictionary of promises
        pendig_response
            promise response request

        Returns
        -------
        tuple
            (response, status)
        """

        end_time = self.loop.time() + float(self.config["utils.wait_promise_time"])

        # In this cycle we wait for the response of message_handler to obtain QR code
        while True:
            self.log.debug(f"[{datetime.now()}] - [{key_promise}] - [{pending_response.done()}]")

            if pending_response.done():
                # when a message event is received, the Future object is resolved
                self.log.info(f"FUTURE {key_promise} IS DONE")
                future_response = pending_response.result()
                break
            if (self.loop.time() + 1.0) >= end_time:
                self.log.info(f"TIMEOUT COMPLETED FOR THE PROMISE {key_promise}")
                pending_response.set_result(
                    {
                        "msgtype": "error",
                        "response": TIMEOUT_ERROR,
                    }
                )
                future_response = pending_response.result()
                break

            await asyncio.sleep(1)

        return future_response
