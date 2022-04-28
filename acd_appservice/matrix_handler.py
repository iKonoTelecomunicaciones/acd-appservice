from __future__ import annotations

import asyncio
import logging

from mautrix.appservice import AppService, IntentAPI
from mautrix.bridge import config
from mautrix.errors import MExclusive, MForbidden, MUnknownToken
from mautrix.types import (
    Event,
    EventID,
    EventType,
    Membership,
    MemberStateEventContent,
    MessageEvent,
    MessageEventContent,
    MessageType,
    RoomID,
    StateEvent,
    StateUnsigned,
    UserID,
)
from mautrix.util.logging import TraceLogger

from . import acd_program as acd_pr
from . import room_manager
from .commands.handler import command_processor
from .commands.typehint import CommandEvent
from .puppet import Puppet


class MatrixHandler:
    log: TraceLogger = logging.getLogger("mau.matrix")
    az: AppService
    config: config.BaseBridgeConfig
    acd_appservice: acd_pr.ACD

    room_manager: room_manager.RoomManager

    def __init__(
        self,
        acd_appservice: acd_pr.ACD | None = None,
    ) -> None:
        self.az = acd_appservice.az
        self.acd_appservice = acd_appservice
        self.config = acd_appservice.config
        self.az.matrix_event_handler(self.int_handle_event)

    async def wait_for_connection(self) -> None:
        self.log.info("Ensuring connectivity to homeserver")
        errors = 0
        tried_to_register = False
        while True:
            try:
                self.versions = await self.az.intent.versions()
                await self.az.intent.whoami()
                break
            except (MUnknownToken, MExclusive):
                # These are probably not going to resolve themselves by waiting
                raise
            except MForbidden:
                if not tried_to_register:
                    self.log.debug(
                        "Whoami endpoint returned M_FORBIDDEN, "
                        "trying to register bridge bot before retrying..."
                    )
                    await self.az.intent.ensure_registered()
                    tried_to_register = True
                else:
                    raise
            except Exception:
                errors += 1
                if errors <= 6:
                    self.log.exception("Connection to homeserver failed, retrying in 10 seconds")
                    await asyncio.sleep(10)
                else:
                    raise
        try:
            self.media_config = await self.az.intent.get_media_repo_config()
        except Exception:
            self.log.warning("Failed to fetch media repo config", exc_info=True)

    async def init_as_bot(self) -> None:
        self.log.debug("Initializing appservice bot")
        displayname = self.config["appservice.bot_displayname"]
        if displayname:
            try:
                await self.az.intent.set_displayname(
                    displayname if displayname != "remove" else ""
                )
            except Exception:
                self.log.exception("Failed to set bot displayname")

        avatar = self.config["appservice.bot_avatar"]
        if avatar:
            try:
                await self.az.intent.set_avatar_url(avatar if avatar != "remove" else "")
            except Exception:
                self.log.exception("Failed to set bot avatar")

    async def handle_invide(self, evt: Event):
        self.log.debug(f"{evt.sender} invited {evt.state_key} to {evt.room_id}")

        intent = await self.process_puppet(user_id=UserID(evt.state_key))

        await intent.join_room(evt.room_id)

    async def handle_disinvite(
        self,
        room_id: RoomID,
        user_id: UserID,
        disinvited_by: UserID,
        reason: str,
        event_id: EventID,
    ) -> None:
        pass

    async def handle_join(self, room_id: RoomID, user_id: UserID, event_id: EventID) -> None:
        self.log.debug(f"{user_id} HAS JOINED THE ROOM {room_id}")

        intent = await self.process_puppet(user_id=user_id)

        if not intent:
            self.log(f"The user who has joined is neither a puppet nor the appservice_bot")
            return

        # Solo se inicializa la sala si el que se une es el usuario acd*
        if intent.api.bot_mxid == user_id and not await self.room_manager.initialize_room(
            room_id=room_id, intent=intent
        ):
            self.log.debug(f"Room {room_id} initialization has failed")

    async def int_handle_event(self, evt: Event) -> None:

        self.log.debug(f"Received event: {evt.event_id} - {evt.type} in the room {evt.room_id}")

        if evt.type == EventType.ROOM_MEMBER:
            evt: StateEvent
            unsigned = evt.unsigned or StateUnsigned()
            prev_content = unsigned.prev_content or MemberStateEventContent()
            prev_membership = prev_content.membership if prev_content else Membership.JOIN
            if evt.content.membership == Membership.INVITE:
                await self.handle_invide(evt)

            elif evt.content.membership == Membership.LEAVE:
                if prev_membership == Membership.BAN:
                    pass
                #     await self.handle_unban(
                #         evt.room_id,
                #         UserID(evt.state_key),
                #         evt.sender,
                #         evt.content.reason,
                #         evt.event_id,
                #     )
                elif prev_membership == Membership.INVITE:
                    pass
                    # self.handle_disinvite(room_id=room)
                #     if evt.sender == evt.state_key:
                #         await self.handle_reject(
                #             evt.room_id, UserID(evt.state_key), evt.content.reason, evt.event_id
                #         )
                #     else:
                #         await self.handle_disinvite(
                #             evt.room_id,
                #             UserID(evt.state_key),
                #             evt.sender,
                #             evt.content.reason,
                #             evt.event_id,
                #         )
                # elif evt.sender == evt.state_key:
                #     await self.handle_leave(evt.room_id, UserID(evt.state_key), evt.event_id)
                # else:
                #     await self.handle_kick(
                #         evt.room_id,
                #         UserID(evt.state_key),
                #         evt.sender,
                #         evt.content.reason,
                #         evt.event_id,
                #     )
            # elif evt.content.membership == Membership.BAN:
            #     await self.handle_ban(
            #         evt.room_id,
            #         UserID(evt.state_key),
            #         evt.sender,
            #         evt.content.reason,
            #         evt.event_id,
            #     )
            elif evt.content.membership == Membership.JOIN:
                if prev_membership != Membership.JOIN:
                    await self.handle_join(evt.room_id, UserID(evt.state_key), evt.event_id)
                # else:
                #     await self.handle_member_info_change(
                #         evt.room_id, UserID(evt.state_key), evt.content, prev_content, evt.event_id
                #     )
        elif evt.type in (EventType.ROOM_MESSAGE, EventType.STICKER):
            evt: MessageEvent
            if evt.type != EventType.ROOM_MESSAGE:
                evt.content.msgtype = MessageType(str(evt.type))
            await self.handle_message(evt.room_id, evt.sender, evt.content, evt.event_id)
        # elif evt.type == EventType.ROOM_ENCRYPTED:
        #     await self.handle_encrypted(evt)
        # elif evt.type == EventType.ROOM_ENCRYPTION:
        #     await self.handle_encryption(evt)
        # else:
        #     if evt.type.is_state and isinstance(evt, StateEvent):
        #         await self.handle_state_event(evt)
        #     elif evt.type.is_ephemeral and isinstance(
        #         evt, (PresenceEvent, TypingEvent, ReceiptEvent)
        #     ):
        #         await self.handle_ephemeral_event(evt)
        #     else:
        #         await self.handle_event(evt)

    def is_command(self, message: MessageEventContent) -> tuple[bool, str]:
        text = message.body
        prefix = self.config["bridge.command_prefix"]
        is_command = text.startswith(prefix)
        if is_command:
            text = text[len(prefix) + 1 :].lstrip()
        return is_command, text

    async def handle_message(
        self,
        room_id: RoomID,
        user_id: UserID,
        message: MessageEventContent,
        event_id: EventID,
    ) -> None:

        intent = await self.process_puppet(user_id=user_id)
        if not intent:
            return

        is_command, text = self.is_command(message=message)
        if is_command and not await self.room_manager.is_customer_room(
            room_id=room_id, intent=intent
        ):
            command_event = CommandEvent(
                acd_appservice=self.acd_appservice,
                sender_user_id=intent.mxid,
                room_id=room_id,
                text=text,
            )
            result = await command_processor(command_event=command_event)
            if result:
                await intent.send_notice(room_id=room_id, text=result, html=result)

        # Ignorar la sala de status broadcast
        if await self.room_manager.is_mx_whatsapp_status_broadcast(room_id=room_id, intent=intent):
            self.log.debug(f"Ignoring the room {room_id} because it is whatsapp_status_broadcast")
            return

        # Intentamos cambiarle el nombre a la sala
        if not await self.room_manager.put_name_customer_room(room_id=room_id, intent=intent):
            self.log.debug(f"Room {room_id} name has not been changed")

    async def process_puppet(self, user_id: UserID) -> IntentAPI:

        if not (user_id == self.az.bot_mxid) and Puppet.get_id_from_mxid(user_id):
            puppet: Puppet = await Puppet.get_by_custom_mxid(user_id)
            return puppet.intent
        else:
            return self.az.intent
