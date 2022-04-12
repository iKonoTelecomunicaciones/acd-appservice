import logging
import re

from mautrix.types import MessageEventContent, MessageType, RoomID
from mautrix.util.logging import TraceLogger

from acd_program.config import Config
from acd_program.user import User
from acd_program.web.provisioning_api import (LOGIN_PENDING_PROMISES,
                                              LOGOUT_PENDING_PROMISES,
                                              MESSAGE_PENDING_PROMISES)


class MessageHandler:
    """Clase que le da manejo a los mensajes que llegan de matrix"""

    log: TraceLogger = logging.getLogger("mau.message_handler")

    def __init__(self, config: Config) -> None:
        self.config = config

    async def handle_notice_message(self, message: MessageEventContent, room_id: RoomID) -> None:
        """Receives a notice and processes it.

        Parameters
        ----------
        message
            Notice message arriving
        room_id
            Room where the notice arrived
        """
        # In this if we use startswith() because we have two messages
        # that starts with 'You're already logged in' they are:
        # 'You're already logged in.'
        # 'You're already logged in. Perhaps you wanted to reconnect?'
        if (
            message.body.startswith(self.config["bridge.notices.logged_in"])
            and room_id in LOGIN_PENDING_PROMISES
        ):
            # Verify that promise hasn't solved to avoid
            # that a second request try to solve the same promise
            if not LOGIN_PENDING_PROMISES[room_id].done():
                LOGIN_PENDING_PROMISES[room_id].set_result(
                    {
                        "msgtype": "logged_in",
                        "response": self.config["bridge.notices.logged_in"],
                    }
                )
        elif (
            message.body == self.config["bridge.notices.logged_out"]
            and room_id in LOGOUT_PENDING_PROMISES
        ):
            # Verify that promise hasn't solved to avoid
            # that a second request try to solve the same promise
            if not LOGOUT_PENDING_PROMISES[room_id].done():
                LOGOUT_PENDING_PROMISES[room_id].set_result(
                    {
                        "msgtype": "logged_out",
                        "response": self.config["bridge.notices.logged_out"],
                    }
                )
        elif (
            message.body == self.config["bridge.notices.not_logged_in"]
            or message.body.startswith(self.config["bridge.notices.not_logged_in_2"])
        ) and room_id in LOGOUT_PENDING_PROMISES:
            # Verify that promise hasn't solved to avoid
            # that a second request try to solve the same promise
            if not LOGOUT_PENDING_PROMISES[room_id].done():
                LOGOUT_PENDING_PROMISES[room_id].set_result(
                    {
                        "msgtype": "not_logged_in",
                        "response": self.config["bridge.notices.not_logged_in"],
                    }
                )

        # Notice que llega cuado el bridge notifica que ya se tiene un chat con x número
        existing_portal = re.match(self.config["bridge.notices.existing_portal"], message.body)
        if existing_portal:
            phone = existing_portal.group("phone_number")
            user_room_id = existing_portal.group("room_id")
            await self.check_pending_messages(phone=phone, room_id=user_room_id)

        # Notice que llega cuando un número no existe en WhatsApp
        phone_is_not_on_whatsapp = re.match(
            self.config["bridge.notices.phone_is_not_on_whatsapp"], message.body
        )
        if phone_is_not_on_whatsapp:
            phone = phone_is_not_on_whatsapp.group("phone_number")
            phone = phone if phone.startswith("+") else f"+{phone}"
            if phone in MESSAGE_PENDING_PROMISES:
                promise = MESSAGE_PENDING_PROMISES[phone]["pending_promise"]
                if not promise.done():
                    promise.set_result({"state": False, "message": message.body})

    async def handle_text_message(self, message: MessageEventContent, room_id: RoomID) -> None:
        """Receives a message and processes it.

        Parameters
        ----------
        message
            Text message arriving
        room_id
            Room where the notice arrived
        """
        if message.body == self.config["bridge.notices.external_loggged_out"]:
            # When a user is logged out from another device, the bridge session fail,
            # and  we have to delete the bridge session to login again
            self.log.debug(f"You were logged out from another device {room_id}")
            user = await User.get_by_room_id(room_id)
            try:
                delete_session_command = self.config["bridge.commands.delete-session"]
                await user.send_command(delete_session_command)
            except Exception as e:
                self.log.error(f"delete-session command hasn't been sent: {e}")

    async def handle_image_message(self, message: MessageEventContent, room_id: RoomID) -> None:
        """Receives a message and processes it.

        Parameters
        ----------
        message
            Image message arriving
        room_id
            Room where the notice arrived
        """
        if room_id in LOGIN_PENDING_PROMISES:
            self.log.info(f"QR code: {message.body} for the room {room_id}")
            # Verify that promise hasn't solved to avoid
            # that a second request try to solve the same promise
            if not LOGIN_PENDING_PROMISES[room_id].done():
                LOGIN_PENDING_PROMISES[room_id].set_result(
                    {"msgtype": "qr_code", "response": message.body}
                )

    async def check_pending_messages(self, phone: str, room_id: str) -> None:
        """Verify if must send message.

        Given a phone looks for a pending message to be sent to room room_id

        Parameters
        ----------
        phone
            key for the message in the  MESSAGE_PENDING_PROMISES dictionary.
        room_id
            room to which the message will be sent
        """
        phone = phone if phone.startswith("+") else f"+{phone}"
        if not phone in MESSAGE_PENDING_PROMISES:
            return

        promise = MESSAGE_PENDING_PROMISES[phone]["pending_promise"]
        msg_type = MESSAGE_PENDING_PROMISES[phone]["msg_type"]
        msg = MESSAGE_PENDING_PROMISES[phone]["message"]
        user = MESSAGE_PENDING_PROMISES[phone]["user"]

        self.log.debug(f"{phone} - {msg_type} - {user.mxid} - {msg}")

        # Envía el mensaje a la sala correspondiente
        if msg_type is MessageType.TEXT:
            check_message = await user.send_text_message(room_id=room_id, message=msg)
        # TODO continuar los diferentes tipos de mensajes
        # if msg_type is MessageType.IMAGE:
        # if msg_type is MessageType.AUDIO:
        # if msg_type is MessageType.FILE:

        # Indica que la promesa es resuelta y retorna su contenido
        if not promise.done():
            promise.set_result(check_message)
