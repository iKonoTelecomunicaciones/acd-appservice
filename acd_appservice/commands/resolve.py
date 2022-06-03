import json
import re
from typing import Dict

from aiohttp import ClientSession
from markdown import markdown

from ..http_client import ProvisionBridge
from ..signaling import Signaling
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="resolve",
    help_text=("Command resolving a chat, ejecting the supervisor and the agent"),
    help_args="<_room_id_> <_user_id_> <_send_message_> <_bridge_>",
)
async def resolve(evt: CommandEvent) -> Dict:
    # Checking if the command has arguments.
    if len(evt.args) < 3:
        detail = "Incomplete arguments for <code>resolve_chat</code> command"
        evt.log.error(detail)
        evt.reply(text=detail)
        return

    room_id = evt.args[1]
    user_id = evt.args[2]
    send_message = evt.args[3] if len(evt.args) > 3 else None
    bridge = evt.args[4] if len(evt.args) > 4 else None

    if send_message is not None:
        send_message = True if send_message == "yes" else False

    agent_id = await evt.agent_manager.get_room_agent(room_id=room_id)

    if agent_id:
        await evt.intent.kick_user(room_id=room_id, user_id=agent_id, reason="Chat resuelto")

    supervisors = evt.config["acd.supervisors_to_invite.invitees"]
    if supervisors:
        for supervisor_id in supervisors:
            await evt.intent.kick_user(
                room_id=room_id, user_id=supervisor_id, reason="Chat resuelto"
            )

    # When the supervisor resolves an open chat, menubot is still in the chat
    await evt.agent_manager.room_manager.kick_menubot(
        room_id=room_id, reason="Chat resuelto", intent=evt.intent
    )

    await evt.agent_manager.signaling.set_chat_status(
        room_id=room_id, status=Signaling.RESOLVED, agent=user_id
    )

    # clear campaign in the ik.chat.campaign_selection state event
    await evt.agent_manager.signaling.set_selected_campaign(room_id=room_id, campaign_room_id=None)

    if send_message is not None:
        resolve_chat_params = evt.config["acd.resolve_chat"]
        if send_message and bridge is not None:
            data = {
                "room_id": room_id,
                "template_message": resolve_chat_params["message"],
                "template_name": resolve_chat_params["template_name"],
                "template_data": resolve_chat_params["template_data"],
                "language": resolve_chat_params["language"],
                "bridge": bridge,
            }
            # template_data = json.dumps(data)
            # template = Template(self.bot)
            # await template.process_template_message(template_data)

        await evt.intent.send_notice(room_id=room_id, text=resolve_chat_params["notice"])
