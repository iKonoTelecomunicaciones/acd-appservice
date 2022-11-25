from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from shlex import split

from markdown import markdown
from mautrix.appservice import AppService
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
    PresenceState,
    ReceiptEvent,
    ReceiptType,
    RoomID,
    SingleReceiptEventContent,
    StateEvent,
    StateUnsigned,
    UserID,
)
from mautrix.util.logging import TraceLogger

from acd_appservice import acd_program

from .client import ProvisionBridge
from .commands.handler import CommandProcessor
from .message import Message
from .puppet import Puppet
from .queue import Queue
from .queue_membership import QueueMembership
from .signaling import Signaling
from .user import User
from .util import Util


class MatrixHandler:
    log: TraceLogger = logging.getLogger("acd.matrix_handler")
    az: AppService
    config: config.BaseBridgeConfig
    acd_appservice: acd_program.ACD
    commands: CommandProcessor = None

    def __init__(
        self,
        acd_appservice: acd_program.ACD | None = None,
    ) -> None:
        self.acd_appservice = acd_appservice
        self.az = self.acd_appservice.az
        self.config = self.acd_appservice.config
        self.az.matrix_event_handler(self.init_handle_event)

    async def wait_for_connection(self) -> None:
        """It tries to connect to the homeserver, and if it fails,
        it waits 10 seconds and tries again. If it fails 6 times, it gives up
        """
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
            except Exception as e:
                errors += 1
                if errors <= 6:
                    self.log.error(
                        f"Connection to homeserver failed, retrying in 10 seconds :: error: {e}"
                    )
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

    async def init_handle_event(self, evt: Event) -> None:
        """If the event is a room member event, then handle it

        Parameters
        ----------
        evt : Event
            Event has arrived

        """
        self.log.debug(f"Received event: {evt}")

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
                elif prev_membership == Membership.INVITE:
                    pass
            elif evt.content.membership == Membership.JOIN:
                if prev_membership != Membership.JOIN:
                    await self.handle_join(evt.room_id, UserID(evt.state_key), evt.event_id)
                else:
                    # Setting the room name to the customer's name.
                    puppet: Puppet = await Puppet.get_customer_room_puppet(evt.room_id)
                    if not puppet:
                        return
                    if await puppet.room_manager.is_customer_room(room_id=evt.room_id):
                        self.log.debug(f"The room name for the room {evt.room_id} will be changed")
                        unsigned: StateUnsigned = evt.unsigned
                        await puppet.room_manager.put_name_customer_room(room_id=evt.room_id)

                    # Cuando el cliente cambia su perfil, ya sea que se quiera conservar el viejo
                    # nombre o no, este código, se encarga de actualizar el nombre
                    # en la caché de salas, si y solo si, la sala está cacheada en el
                    # diccionario puppet.room_manager.ROOMS
                    try:
                        content: MemberStateEventContent = evt.content
                        puppet.room_manager.ROOMS[evt.room_id]["name"] = content.displayname
                    except KeyError:
                        pass
        elif evt.type in (EventType.ROOM_MESSAGE, EventType.STICKER):
            evt: MessageEvent = evt
            if evt.content.msgtype == MessageType.NOTICE:
                self.log.debug(f"Ignoring the notice message: {evt}")
                await self.handle_notice(evt.room_id, evt.sender, evt.content, evt.event_id)
                return

            await self.handle_message(evt.room_id, evt.sender, evt.content, evt.event_id)

        elif evt.type.is_ephemeral and isinstance(evt, (ReceiptEvent)):
            await self.handle_ephemeral_event(evt)

    async def send_welcome_message(self, room_id: RoomID, inviter: User) -> None:
        """If the user who invited the bot to the room doesn't have a management room set,
        set it to the current room and send a notice to the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room the user is in.
        inviter : User
            The user who invited the bot to the room.

        """
        if not inviter.management_room:
            inviter.management_room = room_id
            await inviter.update()
            await self.az.intent.send_notice(
                room_id=room_id, html="This room has been marked as your ACD management room."
            )
        else:
            await self.az.intent.send_notice(
                room_id=room_id,
                html=markdown(
                    f"The room `{inviter.management_room}` "
                    "has already been configured as ACD management room, "
                    "if you want to change admin room, "
                    f"send `{self.config['bridge.command_prefix']} set-admin-room` command."
                ),
            )

    async def send_goodbye_message(self, room_id: RoomID) -> None:
        """This function is called when a user is not an admin and tries to join the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to send the message to.

        """
        detail = markdown(
            "You are not a `ACD admin` check the `bridge.permissionsin` the config file."
        )
        await self.az.intent.send_notice(room_id=room_id, html=detail)
        await self.az.intent.leave_room(room_id=room_id)

    async def handle_ephemeral_event(self, evt: ReceiptEvent) -> None:
        """It takes a receipt event, checks if it's a read receipt,
        and if it is, it updates the message in the database to reflect that it was read

        Parameters
        ----------
        evt : ReceiptEvent
            ReceiptEvent

        Returns
        -------
        """

        if not evt.content:
            return

        for event_id in evt.content:
            for user_id in evt.content.get(event_id).get(ReceiptType.READ) or evt.content.get(
                event_id
            ).get(ReceiptType.READ_PRIVATE):
                username_regex = self.config["utils.username_regex"]
                user_prefix = re.search(username_regex, user_id)
                message = await Message.get_by_event_id(event_id=event_id)
                if user_prefix and message:
                    timestamp_read: SingleReceiptEventContent = (
                        evt.content.get(event_id).get(ReceiptType.READ).get(user_id).ts
                    )
                    await message.mark_as_read(
                        receiver=f"+{user_prefix.group('number')}",
                        event_id=event_id,
                        room_id=evt.room_id,
                        timestamp_read=round(timestamp_read / 1000),
                        was_read=True,
                    )
                    self.log.debug(f"The message {event_id} has been read at {timestamp_read}")

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

        user: User = await User.get_by_mxid(evt.sender)

        if self.az.bot_mxid == evt.state_key:
            if user and user.is_admin:
                await self.send_welcome_message(room_id=evt.room_id, inviter=user)
            else:
                await self.send_goodbye_message(room_id=evt.room_id)

            return

        # We verify that the user to be joined is an acd*.
        # and that there is no other puppet in the room
        # to do an auto-join
        # NOTE: If there is another puppet in the room, then we will have problems
        # as there can't be two acd* users in the same room, this will affect
        # the performance of the software
        puppet_inside: Puppet = await Puppet.get_customer_room_puppet(room_id=evt.room_id)

        if not Puppet.get_id_from_mxid(mxid=evt.state_key) or puppet_inside:
            detail = (
                f"There is already a puppet {puppet_inside.custom_mxid} in the room {evt.room_id}"
                if puppet_inside
                else f"{evt.state_key} is not a puppet"
            )
            self.log.warning(detail)
            return

        puppet: Puppet = await Puppet.get_puppet_by_mxid(evt.state_key)
        self.log.debug(f"The user {puppet.intent.mxid} is trying join in the room {evt.room_id}")
        await puppet.room_manager.save_room(
            room_id=evt.room_id, selected_option=None, puppet_pk=puppet.pk
        )
        await puppet.intent.join_room(evt.room_id)

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

        user: User = await User.get_by_mxid(user_id)

        # Checking if the user is already in the queue. If they are,
        # it updates their creation_date to the current time.
        is_queue: Queue = await Queue.get_by_room_id(room_id=room_id, create=False)

        if is_queue:

            await QueueMembership.get_by_queue_and_user(user.id, is_queue.id)
            return

        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)

        if not puppet:
            self.log.warning(f"I can't get a puppet for the room {room_id}  in [DB]")

            # Si el usuario que se une es un acd* entonces verificamos si se encuentra en la sala
            if Puppet.get_id_from_mxid(user_id):
                self.log.debug(
                    f"Checking in matrix if the puppet {user_id} has already in the room {room_id}"
                )
                puppet: Puppet = await Puppet.get_puppet_by_mxid(user_id)
                if puppet:
                    result = None
                    try:
                        # Este endpoint verifica que el usuario acd* este en la sala
                        # Si es así, entonces result tendrá contenido
                        # Si no, entonces genera una excepción
                        result = await puppet.intent.get_room_member_info(
                            room_id=room_id, user_id=user_id, ignore_cache=True
                        )
                    except Exception as e:
                        self.log.warning(
                            f"I can't get a puppet for the room {room_id} in [MATRIX] :: {e}"
                        )
                        return

                    if result:
                        # Como se encontró el acd* dentro de la sala, entonces la guardamos
                        # en la tabla rooms
                        self.log.debug(f"The puppet {user_id} has already in the room {room_id}")
                        await puppet.room_manager.save_room(
                            room_id=room_id, selected_option=None, puppet_pk=puppet.pk
                        )
            else:
                return

        # If the joined user is main bot or a puppet then saving the room_id and the user_id to the database.
        if user_id == self.az.bot_mxid or Puppet.get_id_from_mxid(user_id):
            await puppet.room_manager.save_room(
                room_id=room_id, selected_option=None, puppet_pk=puppet.pk
            )

        if puppet.intent and puppet.intent.bot and puppet.intent.bot.mxid == user_id:
            # Si el que se unió es el bot principal, debemos sacarlo para que no dañe
            # el comportamiento del puppet
            await puppet.intent.kick_user(room_id=room_id, user_id=user_id)

        # Generamos llaves para buscar en PENDING_INVITES (acd, transfer)
        future_key = puppet.room_manager.get_future_key(room_id=room_id, agent_id=user_id)
        transfer_future_key = puppet.room_manager.get_future_key(
            room_id=room_id, agent_id=user_id, transfer=True
        )

        # Buscamos promesas pendientes relacionadas con el comando acd
        if (
            future_key in puppet.agent_manager.PENDING_INVITES
            and not puppet.agent_manager.PENDING_INVITES[future_key].done()
        ):
            # when the agent accepts the invite, the Future is resolved and the waiting
            # timer stops
            self.log.debug(f"Resolving to True the promise [{future_key}]")
            puppet.agent_manager.PENDING_INVITES[future_key].set_result(True)

        # Buscamos promesas pendientes relacionadas con las transferencia
        if (
            transfer_future_key in puppet.agent_manager.PENDING_INVITES
            and not puppet.agent_manager.PENDING_INVITES[transfer_future_key].done()
        ):
            # when the agent accepts the invite, the Future is resolved and the waiting
            # timer stops
            puppet.agent_manager.PENDING_INVITES[transfer_future_key].set_result(True)

        # If the joined user is a supervisor and the room is a customer room,
        # then send set-pl in the room
        if user_id.startswith(self.config["acd.supervisor_prefix"]):
            if not await puppet.room_manager.is_customer_room(room_id=room_id):
                return

            bridge = await puppet.room_manager.get_room_bridge(room_id=room_id)
            if bridge and bridge in self.config["bridges"] and bridge != "plugin":
                await puppet.room_manager.send_cmd_set_pl(
                    room_id=room_id,
                    bridge=bridge,
                    user_id=user_id,
                    power_level=self.config["acd.supervisors_to_invite.power_level"],
                )

        if not puppet.intent:
            self.log.debug(f"The user who has joined is neither a puppet nor the appservice_bot")
            return

        # Solo se inicializa la sala si el que se une es el usuario acd*
        if Puppet.get_id_from_mxid(user_id):
            if not await puppet.room_manager.initialize_room(room_id=room_id):
                self.log.debug(f"Room {room_id} initialization has failed")

    async def handle_notice(
        self, room_id: RoomID, sender: UserID, message: MessageEventContent, event_id: EventID
    ) -> None:
        """If the puppet doesn't have a phone number,
        we ask the bridge for it, and if the bridge says the puppet is connected,
        we update the puppet's phone number

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room the message was sent in.
        sender : UserID
            The user ID of the user who sent the message.
        message : MessageEventContent
            The message that was sent.
        event_id : EventID
            The ID of the event that triggered the call.

        """
        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
        if puppet and not puppet.phone:
            bridge_conector = ProvisionBridge(session=self.az.http_session, config=self.config)
            response = await bridge_conector.ping(user_id=puppet.custom_mxid)
            if (
                not response.get("error")
                and response.get("whatsapp").get("conn")
                and response.get("whatsapp").get("conn").get("is_connected")
            ):
                # Actualizamos el numero registrado para este puppet
                # sin el +
                puppet.phone = response.get("whatsapp").get("phone").replace("+", "")
                await puppet.save()

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

        # Discard reply blocks
        if message.body.startswith(" * "):
            # This is likely an edit, ignore
            return

        message.body = message.body.strip()

        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)
        user: User = await User.get_by_mxid(sender)

        # Checking if the message is a command, and if it is,
        # it is sending the command to the command processor.
        is_command, text = self.is_command(message=message)

        if is_command:

            try:
                command, arguments = text.split(" ", 1)
                args = split(arguments)
            except ValueError:
                # Not enough values to unpack, i.e. no arguments
                command = text
                args = []

            await self.commands.handle(
                room_id=room_id,
                sender=user,
                command=command,
                args_list=args,
                content=message,
                intent=puppet.intent if puppet else self.az.intent,
                is_management=room_id == user.management_room,
            )

        if not puppet:
            self.log.warning(f"I can't get an puppet for the room {room_id}")
            return

        # Se ignoran todas las salas que hayan sido agregadas a la lista negra
        if puppet.room_manager.in_blacklist_rooms(room_id=room_id):
            return

        # Dado un user_id obtenemos el número y buscamos que el número no sea uno de los ya
        # registrados en el ACD - AZ, si es así lo agregamos a la lista negra
        # luego se envía un mensaje indicando personalizado.
        customer_match = re.match(self.config["utils.username_regex"], sender)
        if customer_match:
            customer_phone = customer_match.group("number")
            if await puppet.is_another_puppet(phone=customer_phone):
                self.log.error(self.config["utils.message_bot_war"])
                await puppet.intent.send_text(
                    room_id=room_id, text=self.config["utils.message_bot_war"]
                )
                puppet.room_manager.put_in_blacklist_rooms(room_id=room_id)
                return

        # Ignore messages from whatsapp bots
        bridge = await puppet.room_manager.get_room_bridge(room_id=room_id)
        if bridge and sender == self.config[f"bridges.{bridge}.mxid"]:
            return

        # Checking if the room is a control room.
        if await puppet.is_a_control_room(room_id=room_id):
            return

        # ignore messages other than commands from menu bot
        if sender.startswith(self.config["acd.menubot_prefix"]):
            return

        # ignore messages other than commands from supervisor
        if sender.startswith(self.config["acd.supervisor_prefix"]):
            return

        # if it is a voice call, let the customer know that the company doesn't receive calls
        if self.config["acd.voice_call"]:
            if message.body == self.config["acd.voice_call.call_message"]:
                no_call_message = self.config["acd.voice_call.no_voice_call"]
                await puppet.intent.send_text(room_id=room_id, text=no_call_message)
                return

        # Ignorar la sala de status broadcast
        if await puppet.room_manager.is_mx_whatsapp_status_broadcast(room_id=room_id):
            self.log.debug(f"Ignoring the room {room_id} because it is whatsapp_status_broadcast")
            return

        is_agent = puppet.agent_manager.is_agent(agent_id=sender)

        # Ignore messages from ourselves or agents if not a command
        if is_agent:
            await puppet.agent_manager.signaling.set_chat_status(
                room_id=room_id, status=Signaling.FOLLOWUP, agent=sender
            )
            return

        # The below code is checking if the room is a customer room, if it is,
        # it is getting the room name, and the creator of the room.
        # If the room name is empty, it is setting the room name to the new room name.
        user_prefix_guest = re.search(self.config[f"acd.username_regex_guest"], sender)
        if await puppet.room_manager.is_customer_room(room_id=room_id) or user_prefix_guest:

            room_name = await puppet.room_manager.get_room_name(room_id=room_id)
            if not room_name:
                await puppet.room_manager.put_name_customer_room(room_id=room_id)
                self.log.info(
                    f"User {room_id} has changed the name of the room {puppet.intent.mxid}"
                )

            if puppet.intent.mxid == sender:
                self.log.debug(f"Ignoring {sender} messages, is acd*")
                return

            # the user entered the offline agent menu and selected some option
            if puppet.room_manager.in_offline_menu(room_id):
                puppet.room_manager.pull_from_offline_menu(room_id)
                valid_option = await puppet.agent_manager.process_offline_selection(
                    room_id=room_id, msg=message.body
                )
                if valid_option:
                    return

            room_agent = await puppet.agent_manager.get_room_agent(room_id=room_id)
            if room_agent:
                # if message is not from agents, bots or ourselves, it is from the customer
                await puppet.agent_manager.signaling.set_chat_status(
                    room_id=room_id, status=Signaling.PENDING, agent=room_agent
                )

                if await puppet.agent_manager.business_hours.is_not_business_hour():
                    await puppet.agent_manager.business_hours.send_business_hours_message(
                        room_id=room_id
                    )
                    return

                presence = await puppet.agent_manager.get_agent_presence(agent_id=room_agent)
                if presence and presence.presence != PresenceState.ONLINE:
                    await puppet.agent_manager.process_offline_agent(
                        room_id=room_id,
                        room_agent=room_agent,
                        last_active_ago=presence.last_active_ago,
                    )
                return

            if await puppet.room_manager.has_menubot(room_id=room_id):
                self.log.debug("Menu bot is here...")
                return

            if await puppet.room_manager.is_group_room(room_id=room_id):
                self.log.debug(f"{room_id} is a group room, ignoring message")
                return

            # Send an informative message if the conversation started no within the business hour
            if await puppet.agent_manager.business_hours.is_not_business_hour():
                await puppet.agent_manager.business_hours.send_business_hours_message(
                    room_id=room_id
                )
                if not self.config["utils.business_hours.show_menu"]:
                    return

            if not puppet.room_manager.is_room_locked(room_id=room_id):

                await puppet.agent_manager.signaling.set_chat_status(
                    room_id=room_id, status=Signaling.OPEN
                )

                if self.config["acd.supervisors_to_invite.invite"]:
                    asyncio.create_task(puppet.room_manager.invite_supervisors(room_id=room_id))

                # clear campaign in the ik.chat.campaign_selection state event
                await puppet.agent_manager.signaling.set_selected_campaign(
                    room_id=room_id, campaign_room_id=None
                )

            if puppet.destination:
                if await self.process_destination(customer_room_id=room_id):
                    return

            # invite menubot to show menu
            # this is done with create_task because with no official API set-pl can take
            # a while so several invite attempts are made without blocking
            menubot_id = await puppet.room_manager.get_menubot_id()
            if menubot_id:
                asyncio.create_task(
                    puppet.room_manager.invite_menu_bot(room_id=room_id, menubot_id=menubot_id)
                )

    async def process_destination(self, customer_room_id: RoomID) -> bool:
        """Distribute the chat using puppet destination, destination can be a user_id or room_id

        Parameters
        ----------
        customer_room_id : RoomID
            The room ID of the room that the user is in.

        Returns
        -------
            A boolean value.

        """
        puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=customer_room_id)

        if not puppet:
            return False

        user: User = await User.get_by_mxid(puppet.custom_mxid)

        # If destination exists, distribute chat using it.
        # Destination can be user_id or room_id.
        if not Util.is_room_id(puppet.destination) and not Util.is_user_id(puppet.destination):
            self.log.debug(f"Wrong destination for room id {customer_room_id}")
            return False

        args = [customer_room_id, puppet.destination]
        command = "acd" if Util.is_room_id(puppet.destination) else "transfer_user"
        await self.commands.handle(
            sender=user, command=command, args_list=args, is_management=False, intent=puppet.intent
        )

        return True
