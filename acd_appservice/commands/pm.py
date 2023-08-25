import asyncio
import json
import re
from argparse import ArgumentParser, Namespace
from typing import Dict

from markdown import markdown

from ..client import ProvisionBridge
from ..events import ACDConversationEvents, send_conversation_event
from ..portal import Portal, PortalState
from ..puppet import Puppet
from ..signaling import Signaling
from .handler import CommandArg, CommandEvent, command_handler

message_arg = CommandArg(
    name="--message or -m",
    help_text="Message to be sent to the customer",
    is_required=True,
    example="Hey there!",
)

phone_arg = CommandArg(
    name="--phone or -p",
    help_text="Number of the customer for whom the private chat is to be created",
    is_required=True,
    example="`573123456789` | `+573123456789`",
)


def args_parser():
    parser = ArgumentParser(description="PM", exit_on_error=False)

    parser.add_argument(
        "--message",
        "-m",
        dest="message",
        type=str,
        required=True,
    )
    parser.add_argument("--phone", "-p", dest="phone", type=str, required=True)

    return parser


@command_handler(
    name="pm",
    help_text=("Command that allows send a message to a customer"),
    help_args=[phone_arg, message_arg],
    args_parser=args_parser(),
)
async def pm(evt: CommandEvent) -> Dict:
    """It sends a message to a customer, if the customer is already in a room,
    it joins the agent to the room and sends a message to the room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        A dict with two keys:
        - data: The data to be sent to the frontend.
        - status: The HTTP status code to be sent to the frontend.

    """
    args: Namespace = evt.cmd_args
    puppet: Puppet = await Puppet.get_by_custom_mxid(evt.intent.mxid)

    if not puppet:
        return

    phone: str = args.phone
    message: str = args.message

    # A dict that will be sent to the frontend.
    return_params = {
        "sender_id": evt.sender.mxid,
        "phone_number": None,
        "room_id": None,
        "agent_displayname": None,
        "reply": None,
    }

    # Command that will be sent to frontend.
    cmd_front_msg = None
    agent_displayname = None

    # Checking if the phone number is a number and if the template name and message are not empty.

    if not phone.isdigit():
        return_params["reply"] = "You must specify a valid phone number with country prefix."

    # Checking if the phone number starts with a plus sign, if not, it adds it.
    phone = phone if phone.startswith("+") else f"+{phone}"

    # Sending a message to the frontend.
    if return_params.get("reply"):
        cmd_front_msg = (
            f"{puppet.config['acd.frontend_command_prefix']} {evt.command} "
            f"{json.dumps(return_params)}"
        )
        await evt.reply(text=cmd_front_msg)
        return {"data": return_params, "status": 422}

    # TODO WORKAROUND FOR NOT LINKING TO THE MENU IN A BIC
    user_prefix = evt.config[f"bridges.{puppet.bridge}.user_prefix"]
    user_domain = evt.config["homeserver.domain"]
    portal_creator = f"@{user_prefix}_{phone.replace('+', '')}:{user_domain}"

    evt.log.debug(f"Putting portal with creator {portal_creator} in BIC rooms")
    puppet.BIC_ROOMS.add(portal_creator)

    # Sending a message to the customer.
    bridge_connector = ProvisionBridge(
        session=evt.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )
    status, data = await bridge_connector.pm(user_id=evt.intent.mxid, phone=phone)

    if not status in [200, 201]:
        evt.log.error(data)

    # Checking if the room_id is set,
    # if it is, it gets the agent_id from the room_id,
    # if the agent_id is set and it is not the sender,
    # it returns a message to the frontend,
    # if the agent_id is set and it is the sender,
    # it returns a message to the frontend,
    # if the agent_id is not set,
    # it joins the agent to the room and sends a message to the room.
    customer_room_id = data.get("room_id")
    agent = None
    if customer_room_id:
        portal: Portal = await Portal.get_by_room_id(
            room_id=customer_room_id,
            fk_puppet=puppet.pk,
            intent=puppet.intent,
            bridge=puppet.bridge,
        )

        agent = await portal.get_current_agent()

        # Checking if the agent is already in the room, if it is, it returns a message to the frontend.
        if agent and agent.mxid != evt.sender.mxid:
            agent_displayname = await agent.get_displayname()
            return_params[
                "reply"
            ] = "The agent <agent_displayname> is already in room with [number]"
        else:
            if puppet.config[f"bridges.{puppet.bridge}.send_template_command"]:
                status, data = await bridge_connector.gupshup_template(
                    user_id=evt.intent.mxid, room_id=data.get("room_id"), template=message
                )
                message_event_id = data.get("event_id")
            else:
                message_event_id = await evt.intent.send_text(
                    room_id=data.get("room_id"),
                    text=message,
                    html=markdown(message),
                )

            if agent and agent.mxid == evt.sender.mxid:
                await portal.update_state(PortalState.FOLLOWUP)
                await puppet.agent_manager.signaling.set_chat_status(
                    room_id=portal.room_id, status=Signaling.FOLLOWUP, agent=evt.sender.mxid
                )

                await send_conversation_event(
                    portal=portal,
                    event_type=ACDConversationEvents.PortalMessage,
                    event_id=message_event_id,
                    sender=evt.sender.mxid,
                )

                # If the agent is already in the room, it returns a message to the frontend.
                return_params["reply"] = "You are already in room with [number], message was sent."
            else:
                # Joining the agent to the room.
                await puppet.agent_manager.add_agent(portal=portal, agent_id=evt.sender.mxid)

            agent_displayname = await evt.intent.get_displayname(user_id=evt.sender.mxid)

    # Setting the return_params dict with the sender_id, phone_number, room_id and agent_displayname.
    return_params["sender_id"] = evt.sender.mxid
    return_params["phone_number"] = phone
    # When other agent is in the room, room_id must be None
    return_params["room_id"] = (
        None if agent and agent.mxid != evt.sender.mxid else data.get("room_id")
    )
    return_params["agent_displayname"] = agent_displayname if agent_displayname else None

    error = None

    if data.get("error"):
        phone_is_not_on_whatsapp = re.match(
            puppet.config["bridges.mautrix.notice_messages.phone_is_not_on_whatsapp"],
            data.get("error"),
        )
        # Checking if the phone number is on whatsapp.
        if phone_is_not_on_whatsapp:
            error: str = data.get("error")
            return_params["reply"] = error.replace(
                f"+{phone_is_not_on_whatsapp.group('phone_number')}", "[number]"
            )
        else:
            return_params["reply"] = data.get("error")

    # If the reply is not set, it means there is no error.
    # The agent can join the room and the message was sent.
    if not return_params.get("reply"):
        # the room is marked as followup and campaign from previous room state
        # is not kept
        await portal.update_state(PortalState.FOLLOWUP)
        await send_conversation_event(
            portal=portal,
            event_type=ACDConversationEvents.BIC,
            sender=evt.sender.mxid,
            destination=evt.sender.mxid,
        )
        await puppet.agent_manager.signaling.set_chat_status(
            room_id=portal.room_id,
            status=Signaling.FOLLOWUP,
            agent=evt.sender.mxid,
            campaign_room_id=None,
            keep_campaign=False,
        )
        # clear campaign in the ik.chat.campaign_selection state event
        await puppet.agent_manager.signaling.set_selected_campaign(
            room_id=portal.room_id, campaign_room_id=None
        )
        if puppet.config["acd.supervisors_to_invite.invite"]:
            asyncio.create_task(portal.invite_supervisors())

        # kick menu bot
        evt.log.debug(f"Kicking the menubot out of the room {portal.room_id}")
        try:
            # TODO Remove when all clients have menuflow
            menubot = await portal.get_current_menubot()
            if menubot:
                await puppet.room_manager.send_menubot_command(
                    menubot.mxid, "cancel_task", portal.room_id
                )
                # ------  end remove -------
            await portal.remove_menubot(
                reason=f"{evt.sender.mxid} pm existing room {portal.room_id}"
            )
        except Exception as e:
            evt.log.exception(e)

        return_params["reply"] = "Now you are joined in room with [number], message was sent."

    # Sending a message to the frontend.
    cmd_front_msg = (
        f"{puppet.config['acd.frontend_command_prefix']} {evt.command} {json.dumps(return_params)}"
    )

    formatted_room = f"[{data.get('room_id')}](https://matrix.to/#/{data.get('room_id')})"

    phone = phone.replace("+", "")

    formatted_user = (
        f"[{phone}]"
        f"(https://matrix.to/#/"
        f"@{evt.config[f'bridges.{puppet.bridge}.user_prefix']}"
        f"_{phone}:{evt.intent.domain})"
    )
    formatted_agent = (
        await agent.get_formatted_displayname()
        if agent
        else await evt.sender.get_formatted_displayname()
    )

    await evt.reply(
        text=return_params["reply"]
        .replace("number", formatted_user if not data.get("error") else phone)
        .replace("room", formatted_room)
        .replace("<agent_displayname>", formatted_agent)
    )

    # Returning a dict with two keys:
    #     - data: The data to be sent to the frontend.
    #     - status: The HTTP status code to be sent to the frontend.
    return {"data": return_params, "status": status}
