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
    RoomNameStateEventContent,
    StateEvent,
    StateUnsigned,
    UserID,
)
from mautrix.util.logging import TraceLogger

from acd_appservice import acd_program
from acd_appservice.agent_manager import AgentManager
from acd_appservice.room_manager import RoomManager

from .commands.handler import command_processor
from .commands.typehint import CommandEvent
from .puppet import Puppet


class MatrixHandler:
    log: TraceLogger = logging.getLogger("acd.matrix_handler")
    az: AppService
    config: config.BaseBridgeConfig
    acd_appservice: acd_program.ACD

    agent_manager: AgentManager
    room_manager: RoomManager

    def __init__(
        self,
        acd_appservice: acd_program.ACD | None = None,
    ) -> None:
        self.acd_appservice = acd_appservice
        self.az = self.acd_appservice.az
        self.config = self.acd_appservice.config
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

    async def int_handle_event(self, evt: Event) -> None:
        """If the event is a room member event, then handle it

        Parameters
        ----------
        evt : Event
            Event has arrived

        """

        self.log.debug(f"Received event: {evt.event_id} - {evt.type} in the room {evt.room_id}")

        if evt.type == EventType.ROOM_MEMBER:
            evt: StateEvent
            unsigned = evt.unsigned or StateUnsigned()
            prev_content = unsigned.prev_content or MemberStateEventContent()
            prev_membership = prev_content.membership if prev_content else Membership.JOIN
            if evt.content.membership == Membership.INVITE:
                await self.handle_invite(evt)

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
            evt: MessageEvent = evt
            if evt.type == EventType.ROOM_MESSAGE:
                evt.content.msgtype = MessageType(str(evt.type))
                await self.handle_message(evt.room_id, evt.sender, evt.content, evt.event_id)
        elif evt.type == EventType.ROOM_NAME:
            # Setting the room name to the customer's name.
            if evt.sender.startswith(f"@{self.config['bridges.mautrix.user_prefix']}"):
                unsigned: StateUnsigned = evt.unsigned
                await self.room_manager.put_name_customer_room(
                    room_id=evt.room_id, intent=self.az.intent, old_name=unsigned.prev_content.name
                )

            # Cuando el cliente cambia su perfil, ya sea que se quiera conservar el viejo
            # nombre o no, este código, se encarga de actualizar el nombre
            # en la caché de salas, si y solo si, la sala está cacheada en el
            # diccionario RoomManager.ROOMS
            try:
                content: RoomNameStateEventContent = evt.content
                RoomManager.ROOMS[evt.room_id]["name"] = content.name
            except KeyError:
                pass

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

    async def handle_invite(self, evt: Event):
        """If the user who was invited is a acd*, then join the room

        Parameters
        ----------
        evt : Event
            Incoming event

        Returns
        -------

        """

        self.log.debug(f"{evt.sender} invited {evt.state_key} to {evt.room_id}")

        # Verificamos que el usuario que se va a unir sea un acd*
        # para hacerle un auto-join
        if not Puppet.get_id_from_mxid(mxid=evt.state_key):
            return

        # Obtenemos el intent del puppet
        intent = await self.get_intent(user_id=UserID(evt.state_key))

        if not intent:
            return None

        self.log.debug(f"The user {intent.mxid} is trying join in the room {evt.room_id}")
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
        """If the user who has joined the room is the bot, then the room is initialized

        Parameters
        ----------
        room_id : RoomID
            The ID of the room the user has joined.
        user_id : UserID
            The user who has joined the room
        event_id : EventID
            The ID of the event that triggered this call.

        Returns
        -------
            The intent of the user who has joined the room

        """
        self.log.debug(f"{user_id} HAS JOINED THE ROOM {room_id}")

        future_key = RoomManager.get_future_key(room_id=room_id, agent_id=user_id)
        if (
            future_key in AgentManager.PENDING_INVITES
            and not AgentManager.PENDING_INVITES[future_key].done()
        ):
            # when the agent accepts the invite, the Future is resolved and the waiting
            # timer stops
            self.log.debug(f"Resolving to True the promise [{future_key}]")
            AgentManager.PENDING_INVITES[future_key].set_result(True)

        # If the joined user is main bot or a puppet then saving the room_id and the user_id to the database.
        if user_id == self.az.bot_mxid or Puppet.get_id_from_mxid(user_id):
            await RoomManager.save_room(room_id=room_id, selected_option=None, puppet_mxid=user_id)

        intent = await self.get_intent(user_id=user_id)
        if not intent:
            self.log.debug(f"The user who has joined is neither a puppet nor the appservice_bot")
            return

        # Solo se inicializa la sala si el que se une es el usuario acd*
        if not await self.room_manager.initialize_room(room_id=room_id, intent=intent):
            self.log.debug(f"Room {room_id} initialization has failed")

    def is_command(self, message: MessageEventContent) -> tuple[bool, str]:
        """It checks if a message starts with the command prefix, and if it does,
        it removes the prefix and returns the message without the prefix

        Parameters
        ----------
        message : MessageEventContent
            The message that was sent.

        Returns
        -------
            A tuple of a boolean and a string.

        """
        text = message.body
        prefix = self.config["bridge.command_prefix"]
        is_command = text.startswith(prefix)
        if is_command:
            text = text[len(prefix) + 1 :].lstrip()
        return is_command, text

    async def handle_message(
        self, room_id: RoomID, sender: UserID, message: MessageEventContent, event_id: EventID
    ) -> None:
        """If the message is a command, process it. If not, ignore it

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room the message was sent in.
        sender : UserID
            The user ID of the user who sent the message.
        message : MessageEventContent
            The message that was sent.
        event_id : EventID
            The ID of the event that triggered this call.

        Returns
        -------

        """

        intent = await self.get_intent(room_id=room_id)
        if not intent:
            self.log.warning(f"I can't get an intent for the room {room_id}")
            return

        # Actualizamos el intent del agent_manager, dado el nuevo intent encontrado
        self.agent_manager.intent = intent

        # Ignore messages from whatsapp bots
        if sender == self.config["bridges.mautrix.mxid"]:
            return

        # Checking if the message is a command, and if it is,
        # it is sending the command to the command processor.
        is_command, text = self.is_command(message=message)
        if is_command and not await self.room_manager.is_customer_room(
            room_id=room_id, intent=intent
        ):
            args = text.split()
            command_event = CommandEvent(
                agent_manager=self.agent_manager,
                cmd=args[0],
                args=args,
                sender=sender,
                room_id=room_id,
                text=text,
            )
            await command_processor(cmd_evt=command_event)
            return

        # Checking if the room is a control room.
        if (
            await RoomManager.is_a_control_room(room_id=room_id)
            or room_id == self.config["acd.control_room_id"]
        ):
            return

        # ignore messages other than commands from menu bot
        if self.config["acd.menubot"] and sender == self.config["acd.menubot.user_id"]:
            return

        if self.config["acd.menubots"] and sender in self.config["acd.menubots"]:
            return

        # ignore messages other than commands from supervisor
        if sender.startswith(self.config["acd.supervisor_prefix"]):
            return

        # Ignorar la sala de status broadcast
        if await self.room_manager.is_mx_whatsapp_status_broadcast(room_id=room_id, intent=intent):
            self.log.debug(f"Ignoring the room {room_id} because it is whatsapp_status_broadcast")
            return

        # The below code is checking if the room is a customer room, if it is,
        # it is getting the room name, and the creator of the room.
        # If the room name is empty, it is setting the room name to the new room name.
        if await self.room_manager.is_customer_room(room_id=room_id, intent=intent):
            room_name = await self.room_manager.get_room_name(room_id=room_id, intent=intent)
            if not room_name:
                creator = await self.room_manager.get_room_creator(room_id=room_id, intent=intent)
                new_room_name = await self.room_manager.get_update_name(
                    creator=creator, intent=intent
                )
                if new_room_name:
                    await intent.set_room_name(room_id=room_id, name=new_room_name)
                    self.log.info(f"User {room_id} has changed the name of the room {intent.mxid}")

    async def get_intent(self, user_id: UserID = None, room_id: RoomID = None) -> IntentAPI:
        """If the user_id is not the bot's mxid, and the user_id is a custom mxid,
        then return the intent of the puppet that has the custom mxid

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to get the intent of.
        room_id : RoomID
            The room ID of the room you want to send the message to.

        Returns
        -------
            Puppet's intent

        """
        # Coloco el intent del bot principal siempre para que cuando no pueda obtener uno
        # dado un user o un room_id, entonces regrese al acd principal
        intent: IntentAPI = None
        if user_id:
            # Checking if the user_id is not the bot_mxid and if the user_id is a puppet.
            if user_id != self.az.bot_mxid and Puppet.get_id_from_mxid(user_id):
                puppet: Puppet = await Puppet.get_by_custom_mxid(user_id)
                if puppet:
                    intent = puppet.intent

            # Checking if the user_id is the same as the bot_mxid.
            elif user_id == self.az.bot_mxid:
                intent = self.az.intent
        elif room_id:
            # Getting the puppet from a customer room.
            puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
            if puppet:
                intent = puppet.intent

        return intent
