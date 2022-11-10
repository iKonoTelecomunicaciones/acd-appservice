import asyncio
import json
import logging
from datetime import datetime
from time import time
from typing import Dict, List

from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..puppet import Puppet
from ..signaling import Signaling
from ..user import User
from .handler import command_handler
from .template import template
from .typehint import CommandEvent


@command_handler(
    name="resolve",
    help_text=("Command resolving a chat, ejecting the supervisor and the agent"),
    help_args="<_room_id_> <_user_id_> <_send_message_> <_bridge_>",
)
async def resolve(evt: CommandEvent) -> Dict:
    """It kicks the agent and menubot from the chat,
    sets the chat status to resolved, and sends a notice to the user

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        A dictionary with the following keys:

    """
    # Checking if the command has arguments.

    if len(evt.args) < 3:
        detail = "Incomplete arguments for <code>resolve_chat</code> command"
        evt.log.error(detail)
        await evt.reply(text=detail)
        return

    room_id = evt.args[0]
    user_id = evt.args[1]
    send_message = evt.args[2] if len(evt.args) > 2 else None
    bridge = evt.args[3] if len(evt.args) > 3 else None

    evt.log.debug(
        f"The user {user_id} is resolving the room {room_id}, send_message? // {send_message} "
    )

    puppet: Puppet = await Puppet.get_customer_room_puppet(room_id=room_id)

    if room_id == puppet.control_room_id or (
        not await puppet.room_manager.is_customer_room(room_id=room_id)
        and not await puppet.room_manager.is_guest_room(room_id=room_id)
    ):

        detail = "Group rooms or control rooms cannot be resolved."
        evt.log.error(detail)
        await puppet.intent.send_notice(room_id=room_id, text=detail)
        return

    if send_message is not None:
        send_message = True if send_message == "yes" else False

    agent_id = await puppet.agent_manager.get_room_agent(room_id=room_id)

    try:
        if agent_id:
            await puppet.room_manager.remove_user_from_room(
                room_id=room_id, user_id=agent_id, reason=puppet.config["acd.resolve_chat.notice"]
            )
        supervisors = puppet.config["acd.supervisors_to_invite.invitees"]
        if supervisors:
            for supervisor_id in supervisors:
                await puppet.room_manager.remove_user_from_room(
                    room_id=room_id,
                    user_id=supervisor_id,
                    reason=puppet.config["acd.resolve_chat.notice"],
                )
    except Exception as e:
        evt.log.warning(e)

    # When the supervisor resolves an open chat, menubot is still in the chat
    await puppet.room_manager.menubot_leaves(
        room_id=room_id,
        reason=puppet.config["acd.resolve_chat.notice"],
    )

    await puppet.agent_manager.signaling.set_chat_status(
        room_id=room_id, status=Signaling.RESOLVED, agent=user_id
    )

    # clear campaign in the ik.chat.campaign_selection state event
    await puppet.agent_manager.signaling.set_selected_campaign(
        room_id=room_id, campaign_room_id=None
    )

    if send_message is not None:
        resolve_chat_params = puppet.config["acd.resolve_chat"]
        if send_message and bridge is not None:
            data = {
                "room_id": room_id,
                "template_message": resolve_chat_params["message"],
                "template_name": resolve_chat_params["template_name"],
                "template_data": resolve_chat_params["template_data"],
                "language": resolve_chat_params["language"],
                "bridge": bridge,
            }
            template_data = f"{json.dumps(data)}"

            cmd_evt = CommandEvent(
                intent=puppet.intent,
                config=puppet.config,
                command="template",
                sender=evt.sender,
                room_id=room_id,
                is_management=room_id == evt.sender.management_room,
                text=template_data,
                args=template_data.split(),
            )
            await template(cmd_evt)

        await puppet.intent.send_notice(room_id=room_id, text=resolve_chat_params["notice"])


class BulkResolve:

    loop: asyncio.AbstractEventLoop
    log: TraceLogger = logging.getLogger("acd.bulk_resolve")

    main_room_ids_blocks: List[RoomID] = []
    jesus_has_his_hand_up = False

    def __init__(self, loop: asyncio.AbstractEventLoop, config: Config) -> None:

        self.loop = loop
        self.config = config
        self.room_bloks = self.config["acd.bulk_resolve.room_blocks"]

    async def resolve(
        self, room_ids: List[RoomID], user: User, user_id: UserID, send_message: str
    ):
        self.log.debug(f"Starting bulk resolve of {len(room_ids)} rooms")

        room_ids_blocks: List[List[RoomID]] = [
            room_ids[i : i + self.room_bloks] for i in range(0, len(room_ids), self.room_bloks)
        ]
        self.main_room_ids_blocks += room_ids_blocks

        if self.jesus_has_his_hand_up:
            self.log.debug(f"##############")
            self.log.debug(f"##############")
            self.log.debug(f"jesus tells you to stop")
            self.log.debug(f"##############")
            self.log.debug(f"##############")
            return

        for room_ids_to_resolve in self.main_room_ids_blocks:
            tasks = []
            self.log.info(f"Rooms to be resolved: {len(room_ids_to_resolve)}")
            for room_id in room_ids_to_resolve:
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
                bridge_prefix = puppet.config[f"bridges.{bridge}.prefix"]

                args = [room_id, user_id, send_message, bridge_prefix]

                # Creating a fake command event and passing it to the command processor.

                fake_cmd_event = CommandEvent(
                    sender=user,
                    config=self.config,
                    command="resolve",
                    is_management=False,
                    intent=puppet.intent,
                    args=args,
                )

                tasks.append(resolve(fake_cmd_event))

            try:
                self.jesus_has_his_hand_up = True
                await asyncio.gather(*tasks)
            except Exception as e:
                self.log.error(e)
                continue

        self.jesus_has_his_hand_up = False
        self.main_room_ids_blocks = []
