import asyncio
import re
from typing import TYPE_CHECKING

from mautrix.bridge import BaseMatrixHandler
from mautrix.errors import IntentError
from mautrix.types import (EventID, MessageEventContent, MessageType, RoomID,
                           UserID)

from acd_program.message_handler import MessageHandler
from acd_program.puppet import Puppet
from acd_program.user import User

if TYPE_CHECKING:
    from .__main__ import ACDAppService


class MatrixHandler(BaseMatrixHandler):
    """Esta clase permite recibir diferentes tipo de eventos que el synapse
    ha generado para este appservice
    """

    def __init__(self, bridge: "ACDAppService") -> None:
        super().__init__(bridge=bridge)
        self.message_handler = MessageHandler(config=self.config)

    async def send_welcome_message(self, room_id: RoomID, inviter: User) -> None:
        await super().send_welcome_message(room_id, inviter)
        if not inviter.notice_room:
            inviter.notice_room = room_id
            await inviter.update()
            await self.az.intent.send_notice(
                room_id, "This room has been marked as your Instagram bridge notice room."
            )

    async def handle_message(
        self, room_id: RoomID, user_id: UserID, message: MessageEventContent, event_id: EventID
    ) -> None:
        self.log.debug(f"### {message}")
        is_command, text = self.is_command(message)
        self.log.debug(f"### {is_command} ---- {text}")
        if user_id == self.config["bridge.bot_user_id"]:
            if message.msgtype == MessageType.NOTICE:
                self.log.info(f"Notice message received [{room_id}] - {message.body}")
                await self.message_handler.handle_notice_message(message=message, room_id=room_id)
            elif message.msgtype == MessageType.IMAGE:
                self.log.info(f"Image message received [{room_id}] - {message.body}")
                await self.message_handler.handle_image_message(message=message, room_id=room_id)
            elif message.msgtype == MessageType.TEXT:
                self.log.info(f"Text message received [{room_id}] - {message.body}")
                await self.message_handler.handle_text_message(message=message, room_id=room_id)

    async def handle_puppet_invite(
        self, room_id: RoomID, puppet: Puppet, invited_by: User, event_id: EventID
    ) -> None:
        # En este caso ocuerre cuando se crea una sala nueva y se le envia la invitación al puppet
        # Nos unimos a la sala nueva y configuramos los permisos de los demas usuarios que
        # invitaremos
        await puppet.intent.join_room_by_id(room_id=room_id)
        user = await User.get_by_mxid(puppet.mxid)
        await user.set_power_level_by_user_id(user_id=puppet.mxid, room_id=room_id, power_level=99)

        # Se invitan a los usuarios que tengamos en la lista de invitados y ademas les damos
        # el permiso de ser administradores de la sala
        for user_invite in self.config["bridge.invitees_to_rooms"]:
            for attempt in range(0, 10):
                self.log.error(f"attempt {attempt} to {room_id}")
                try:
                    await puppet.intent.invite_user(room_id=room_id, user_id=user_invite)
                    await user.set_power_level_by_user_id(
                        user_id=user_invite, room_id=room_id, power_level=100
                    )
                    break
                except IntentError as e:
                    self.log.error(e)
                    await asyncio.sleep(1)

        user_match = re.match(self.config["utils.username_regex"], invited_by.mxid)
        if user_match:
            phone = user_match.group("number")
            await self.message_handler.check_pending_messages(phone=phone, room_id=room_id)

    # Tiene mas handles:
    # async def handle_join(self, room_id: RoomID, user_id: UserID, event_id: EventID) -> None:
