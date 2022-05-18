import asyncio
import logging
import re
from email import header

from aiohttp import ClientSession, WSMsgType, web
from aiohttp_swagger3 import SwaggerDocs, SwaggerUiSettings
from mautrix.types.event.message import MessageType
from mautrix.util.logging import TraceLogger

from .. import VERSION
from ..config import Config
from ..http_client import HTTPClient, ProvisionBridge
from ..puppet import Puppet
from . import SUPPORTED_MESSAGE_TYPES
from .error_responses import (
    INVALID_EMAIL,
    INVALID_PHONE,
    MESSAGE_NOT_SENT,
    MESSAGE_TYPE_NOT_SUPPORTED,
    NOT_DATA,
    NOT_EMAIL,
    REQUEST_ALREADY_EXISTS,
    REQUIRED_VARIABLES,
    SERVER_ERROR,
    TIMEOUT_ERROR,
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

    def __init__(self) -> None:
        self.app = web.Application()

        # swagger = SwaggerDocs(
        #     self.app,
        #     title="WAPI documentation",
        #     version=VERSION,
        #     components=f"acd_appservice/web/components.yaml",
        #     swagger_ui_settings=SwaggerUiSettings(
        #         path="/docs",
        #         layout="BaseLayout",
        #     ),
        # )
        # swagger.add_routes(
        #     [
        #         # Región de autenticación
        #         web.post("/create_user", self.create_user),
        #         web.post("/link_phone", self.link_phone),
        #         web.post("/unlink_phone", self.unlink_phone),
        #         # Región de mensajería
        #         web.post("/send_message", self.send_message),
        #     ]
        # )
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
        swagger.add_routes(
            [
                # Región de autenticación
                web.post("/create_user", self.create_user),
                web.get("/link_phone", self.link_phone),
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

    async def link_phone(self, request: web.Request) -> web.Response:
        """
        Given a user_email send a `!wa login` bridge command to stablish Whatsapp communication
        ---
        summary: Generates a QR code for an existing user in order to create a QR image and link the WhatsApp number by scanning the QR code with the cell phone.
        tags:
            - users

        # requestBody:
        #   required: true
        #   description: A json with `user_email`
        #   content:
        #     application/json:
        #       schema:
        #         type: object
        #         properties:
        #           user_email:
        #             type: string
        #         example:
        #             user_email: nobody@somewhere.com

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

        ws = web.WebSocketResponse()

        await ws.prepare(request)

        user_email = request.rel_url.query.get("user_email")

        if not user_email:
            return web.json_response(**NOT_EMAIL)

        email = user_email.lower()
        if not re.match(self.config["utils.regex_email"], email):
            return web.json_response(**INVALID_EMAIL)

        puppet: Puppet = await Puppet.get_by_email(email)
        if not puppet:
            return web.json_response(**USER_DOESNOT_EXIST)

        # Creamos una conector con el bridge
        bridge_connector = ProvisionBridge(session=self.client.session, config=self.config)
        # Creamos un WebSocket para conectarnos con el bridge
        await bridge_connector.ws_connect(user_id=puppet.custom_mxid, ws_customer=ws)

        return ws

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

    # async def send_message(self, request: web.Request) -> web.Response:
    #     """
    #     Send a message to the given whatsapp number (create a room or send to the existing room)
    #     ---
    #     summary: Send a message from the user account to a WhatsApp phone number.
    #     tags:
    #         - users

    #     requestBody:
    #       required: true
    #       description: A json with `phone`, `message`, `msg_type` (only supports [`text`]), `user_email`
    #       content:
    #         application/json:
    #           schema:
    #             type: object
    #             properties:
    #               phone:
    #                 type: string
    #               message:
    #                 type: string
    #               msg_type:
    #                 type: string
    #               user_email:
    #                 type: string
    #             example:
    #                 phone: "573123456789"
    #                 message: Hello World!
    #                 msg_type: text
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

    #     # Región para validar que la información enviada sea completa y correcta
    #     if not request.body_exists:
    #         return web.json_response(**NOT_DATA)

    #     data = await request.json()
    #     if (
    #         not data.get("phone")
    #         or not data.get("message")
    #         or not data.get("user_email")
    #         or not data.get("msg_type")
    #     ):
    #         return web.json_response(**REQUIRED_VARIABLES)
    #     if not data.get("msg_type") in SUPPORTED_MESSAGE_TYPES:
    #         return web.json_response(**MESSAGE_TYPE_NOT_SUPPORTED)

    #     email = data.get("user_email").lower()
    #     if not re.match(self.config["utils.regex_email"], email):
    #         return web.json_response(**INVALID_EMAIL)
    #     if not await User.user_exists(email):
    #         return web.json_response(**USER_DOESNOT_EXIST)

    #     phone = str(data.get("phone"))
    #     if not (phone.isdigit() and 5 <= len(phone) <= 15):
    #         return web.json_response(**INVALID_PHONE)

    #     # Fin región de validación

    #     msg_type = data.get("msg_type")
    #     message = data.get("message")
    #     phone = phone if phone.startswith("+") else f"+{phone}"
    #     user = await User.get_by_email(email)

    #     pending_promise = self.loop.create_future()

    #     # cargamos el diccionario con los datos necesarios para procesar las solicitudes
    #     # de envió de mensaje
    #     MESSAGE_PENDING_PROMISES[phone] = {
    #         "user": user,
    #         "message": message,
    #         "msg_type": None,
    #         "pending_promise": pending_promise,
    #     }

    #     # Se agrega la promesa en este diccionario para poder hacer seguimiento
    #     # al usuario en cuestión y saber si esta logueado
    #     LOGOUT_PENDING_PROMISES[user.room_id] = pending_promise

    #     if msg_type == "text":
    #         MESSAGE_PENDING_PROMISES[phone]["msg_type"] = MessageType.TEXT
    #     # TODO agregar los diferentes tipos de mensaje en las siguientes lineas
    #     # if msg_type == "audio":
    #     #     MESSAGE_PENDING_PROMISES[phone]["msg_type"] = MessageType.AUDIO
    #     # if msg_type == "image":
    #     #     MESSAGE_PENDING_PROMISES[phone]["msg_type"] = MessageType.IMAGE

    #     # Creamos el comando que será enviado a la sala del user para
    #     pm_command = f"{self.config['bridge.commands.create_room']} {phone}"
    #     await user.send_command(pm_command)

    #     # Se crea la tarea que va a supervisar los notices generados por el bridge
    #     promise_response = await asyncio.create_task(self.check_promise(phone, pending_promise))

    #     # Cuando el promise_response este lleno, podrá tener diferentes datos
    #     # promise_response = {
    #     #     "state": True, # Si llega true es porque todo salió bien, falso trae algún error
    #     #     "message": "Any message", # Los mensajes capturados cuando se resuelve la promesa
    #     # }
    #     if promise_response.get("state"):
    #         response = {
    #             "data": {"message": promise_response.get("message")},
    #             "status": 200,
    #         }
    #     elif promise_response.get("msgtype") == "not_logged_in":
    #         response = {
    #             "data": {
    #                 "message": promise_response.get("response"),
    #             },
    #             "status": 422,
    #         }
    #     else:
    #         response = {
    #             "data": {
    #                 "message": promise_response.get("message")
    #                 if promise_response.get("message")
    #                 else "WhatsApp server has not responded"
    #             },
    #             "status": 422,
    #         }

    #     del MESSAGE_PENDING_PROMISES[phone]
    #     del LOGOUT_PENDING_PROMISES[user.room_id]

    #     return web.json_response(**response)
