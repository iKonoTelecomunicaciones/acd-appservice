from __future__ import annotations

import asyncio
import re
from argparse import ArgumentParser, Namespace
from typing import Any, Dict

from markdown import markdown
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from ..client import ProvisionBridge
from ..events import ACDPortalEvents, send_portal_event
from ..portal import Portal, PortalState
from ..puppet import Puppet
from ..signaling import Signaling
from ..user import User
from ..util.util import Util
from .handler import CommandArg, CommandEvent, CommandProcessor, command_handler

message_arg = CommandArg(
    name="--message or -m",
    help_text="Message to be sent to the customer",
    is_required=False,
    example="Hey there!",
)

phone_arg = CommandArg(
    name="--phone or -p",
    help_text="Number of the customer for whom the private chat is to be created",
    is_required=True,
    example="`573123456789` | `+573123456789`",
)

destination_arg = CommandArg(
    name="--destination or -d",
    help_text="""
        Destination where the chat will be distributed,
        it can be a queue, an agent or a menubot
    """,
    is_required=False,
    example="`@agent1:example.com` | `@menubot1:example.com` | `!shyEsTagScmkOLsndjRs:example.com`",
)

on_transit_arg = CommandArg(
    name="--on_transit or -t",
    help_text="""
        Do you want to process destinations inmediately or wait a customer message to proccess it?
    """,
    is_required=False,
    example="`yes` | `no`",
)

fordce_arg = CommandArg(
    name="--force or -f",
    help_text="Force to start a new chat by the bussines",
    is_required=False,
    example="`yes` | `no`",
)


def args_parser():
    parser = ArgumentParser(description="BIC", exit_on_error=False)

    parser.add_argument("--phone", "-p", dest="phone", type=str, required=True)
    parser.add_argument(
        "--message",
        "-m",
        dest="message",
        type=str,
        required=False,
    )
    parser.add_argument("--destination", "-d", dest="destination", type=str, required=False)
    parser.add_argument(
        "--on-transit", "-t", dest="on_transit", type=str, required=False, default="no"
    )
    parser.add_argument("--force", "-f", dest="force", type=str, required=False, default="no")

    return parser


@command_handler(
    name="bic",
    help_text="Command to create a private chat with a customer by the business",
    help_args=[phone_arg, message_arg, destination_arg, on_transit_arg],
    args_parser=args_parser(),
)
async def bic(evt: CommandEvent) -> Dict:
    args: Namespace = evt.cmd_args
    puppet: Puppet = await Puppet.get_by_custom_mxid(evt.intent.mxid)

    if not puppet:
        return Util.create_response_data(detail="Puppet not found", status=404, room_id=None)

    phone: str = args.phone
    message: str = args.message
    destination: str = args.destination
    on_transit: bool = True if args.on_transit == "yes" else False
    force: bool = True if args.force == "yes" else False

    if not phone.isdigit():
        message = "You must specify a valid phone number with country prefix."
        await evt.reply(message)
        return Util.create_response_data(detail=message, status=400, room_id=None)

    # Sending a message to the customer.
    formated_phone = phone if phone.startswith("+") else f"+{phone}"
    bridge_connector = ProvisionBridge(
        session=evt.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )
    status, data = await bridge_connector.pm(user_id=evt.intent.mxid, phone=formated_phone)

    if not status in [200, 201]:
        evt.log.error(data)

    if data.get("error"):
        phone_is_not_on_whatsapp = re.match(
            puppet.config["bridges.mautrix.notice_messages.phone_is_not_on_whatsapp"],
            data.get("error"),
        )
        # Checking if the phone number is on whatsapp.
        if phone_is_not_on_whatsapp:
            error: str = data.get("error")
            detail = error.replace(
                f"+{phone_is_not_on_whatsapp.group('phone_number')}", "[number]"
            )
        else:
            detail = data.get("error")

        payload = {
            "phone_number": phone,
            "agent_display_name": None,
        }
        return Util.create_response_data(detail=detail, status=404, additional_info=payload)

    portal_room_id = data.get("room_id")
    if portal_room_id:
        portal: Portal = await Portal.get_by_room_id(
            room_id=portal_room_id,
            fk_puppet=puppet.pk,
            intent=puppet.intent,
            bridge=puppet.bridge,
        )

        current_agent: User = await portal.get_current_agent()
        # Checking if the agent is already in the room, if it is, it returns a message to the frontend.
        if current_agent and current_agent.mxid != destination and not force:
            agent_displayname = await current_agent.get_displayname()
            detail = "The agent <agent_displayname> is already in room with [number]"
            return Util.create_response_data(
                detail=detail,
                status=409,
                additional_info={
                    "phone_number": portal.creator_identifier(),
                    "agent_displayname": agent_displayname,
                },
            )

        # TODO WORKAROUND FOR NOT LINKING TO THE MENU IN A BIC
        puppet.BIC_ROOMS.add(portal.room_id)

        if message:
            await send_bic_message(
                portal=portal, message=message, bridge_connector=bridge_connector
            )

        if not destination:
            return Util.create_response_data(
                detail="BIC successfully", status=200, room_id=portal.room_id
            )

        if on_transit:
            if force and current_agent:
                args = ["-a", portal.main_intent.mxid, "-sm", "no", "-p", portal.room_id]
                await evt.processor.handle(
                    sender=portal.main_intent.mxid,
                    command="resolve",
                    args_list=args,
                    is_management=False,
                    intent=puppet.intent,
                )

            # Set chat status to ON_TRANSIT
            portal.update_state(PortalState.ON_TRANSIT)
            await send_portal_event(
                portal=portal, event_type=ACDPortalEvents.BIC, sender=evt.sender
            )

            # Setting destination that will be processed when the customer sends a message.
            portal.destination_on_transit = destination
            await portal.update()

            return Util.create_response_data(
                detail="BIC successfully, waiting for client message",
                status=200,
                room_id=portal.room_id,
            )

        await portal.update_state(PortalState.START)
        await send_portal_event(portal=portal, event_type=ACDPortalEvents.BIC, sender=evt.sender)

        if force and current_agent:
            args = ["-a", portal.main_intent.mxid, "-sm", "no", "-p", portal.room_id]
            await evt.processor.handle(
                sender=portal.main_intent.mxid,
                command="resolve",
                args_list=args,
                is_management=False,
                intent=puppet.intent,
            )

        return await process_bic_destination(
            destination=destination,
            portal=portal,
            puppet=puppet,
            sender=evt.sender,
            command_processor=evt.processor,
            logger=evt.log,
        )


async def process_bic_destination(
    destination: UserID | RoomID,
    portal: Portal,
    puppet: Puppet,
    sender: User,
    command_processor: CommandProcessor,
    logger: TraceLogger,
) -> Dict[str, Any]:
    if Util.is_user_id(destination):
        user: User = await User.get_by_mxid(destination)
        if user.is_agent:
            response = await process_destination_agent(
                agent_id=destination, portal=portal, puppet=puppet, logger=logger
            )
            return response
        elif user.is_menubot:
            asyncio.create_task(portal.add_menubot(user.mxid))
            return Util.create_response_data(
                detail="Menubot added", status=200, room_id=portal.room_id
            )
    elif Util.is_room_id(destination):
        args = ["-c", portal.room_id, "-q", destination]
        response = await command_processor.handle(
            sender=sender,
            command="acd",
            args_list=args,
            is_management=False,
            intent=puppet.intent,
        )
        return response


async def process_destination_agent(
    agent_id: UserID,
    portal: Portal,
    puppet: Puppet,
    logger: TraceLogger = None,
) -> Dict:
    agent: User = await User.get_by_mxid(agent_id)
    current_agent = await portal.get_current_agent()

    # If the agent is already in the room, it returns a message to the frontend.
    await portal.update_state(PortalState.FOLLOWUP)
    await puppet.agent_manager.signaling.set_chat_status(
        room_id=portal.room_id, status=Signaling.FOLLOWUP, agent=agent.mxid
    )

    if current_agent and current_agent.mxid == agent.mxid:
        detail = "You are already in room with [number], message was sent."
    else:
        # Joining the agent to the room.
        await portal.join_user(user_id=agent_id)
        detail = "Now you are joined in room with [number], message was sent."

        # clear campaign in the ik.chat.campaign_selection state event
        await puppet.agent_manager.signaling.set_selected_campaign(
            room_id=portal.room_id, campaign_room_id=None
        )
        if puppet.config["acd.supervisors_to_invite.invite"]:
            asyncio.create_task(portal.invite_supervisors())

        # kick menu bot
        logger.debug(f"Kicking the menubot out of the room {portal.room_id}")
        try:
            # TODO Remove when all clients have menuflow
            menubot = await portal.get_current_menubot()
            if menubot:
                await puppet.room_manager.send_menubot_command(
                    menubot.mxid, "cancel_task", portal.room_id
                )
                # ------  end remove -------
            await portal.remove_menubot(reason=f"{agent.mxid} pm existing room {portal.room_id}")
        except Exception as e:
            logger.exception(e)

    agent_displayname = await agent.get_displayname()
    payload = {
        "phone_number": portal.creator_identifier(),
        "agent_displayname": agent_displayname if agent_displayname else agent_id,
    }

    return Util.create_response_data(
        detail=detail, status=200, room_id=portal.room_id, additional_info=payload
    )


async def send_bic_message(
    portal: Portal,
    message: str,
    bridge_connector: ProvisionBridge,
) -> Dict:
    if portal.config[f"bridges.{portal.bridge}.send_template_command"]:
        await bridge_connector.gupshup_template(
            user_id=portal.main_intent.mxid, room_id=portal.room_id, template=message
        )
    else:
        await portal.main_intent.send_text(
            room_id=portal.room_id,
            text=message,
            html=markdown(message),
        )
