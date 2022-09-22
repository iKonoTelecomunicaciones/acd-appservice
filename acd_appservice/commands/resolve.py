import json
from typing import Dict

from ..puppet import Puppet
from ..signaling import Signaling
from .handler import command_handler, command_processor
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

    room_id = evt.args[1]
    user_id = evt.args[2]
    send_message = evt.args[3] if len(evt.args) > 3 else None
    bridge = evt.args[4] if len(evt.args) > 4 else None

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
            template_data = f"template {json.dumps(data)}"
            cmd_evt = CommandEvent(
                intent=puppet.intent,
                config=puppet.config,
                cmd="template",
                sender=evt.sender,
                room_id=room_id,
                text=template_data,
            )
            await command_processor(cmd_evt=cmd_evt)

        await puppet.intent.send_notice(room_id=room_id, text=resolve_chat_params["notice"])
