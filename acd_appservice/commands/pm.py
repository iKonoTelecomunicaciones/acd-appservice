import json

from aiohttp import ClientSession
from markdown import markdown

from acd_appservice.http_client import ProvisionBridge

from ..agent_manager import AgentManager
from ..puppet import Puppet
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="pm",
    help_text=("Command that allows send a message to a customer"),
    help_args="<_dict_>",
)
async def pm(evt: CommandEvent) -> str:

    if len(evt.args) < 1:
        detail = "pm command incomplete arguments"
        evt.log.error(detail)
        evt.reply(text=detail)

    incoming_params = (evt.text[len(evt.cmd):]).strip()

    data: dict = json.loads(incoming_params)
    phone_number: str = data.get("phone_number")
    template_message = data.get("template_message")
    template_name = data.get("template_name")
    # bridge = data.get("bridge")

    return_params = {
        "sender_id": evt.sender,
        "phone_number_number": None,
        "room_id": None,
        "agent_displayname": None,
        "reply": None,
    }

    frontend_params = None  # TODO PONER ESTO EN EL CONFIG
    cmd_front_msg = None
    agent_displayname = None

    if not phone_number.isdigit():
        return_params["reply"] = "You must specify a valid phone number with country prefix."
    if not template_name or not template_message:
        return_params["reply"] = "You must specify a template name and message"

    phone_number  = phone_number if phone_number.startswith("+") else f"+{phone_number}"

    if return_params.get("reply"):
        cmd_front_msg = f"{frontend_params} {json.dumps(return_params)}"
        await evt.reply(text=cmd_front_msg)

    session: ClientSession = evt.matrix.provisioning_api.client.session
    bridge_connector = ProvisionBridge(session=session, config=evt.acd_appservice.config)
    status, data = await bridge_connector.pm(user_id=evt.intent.mxid, phone=phone_number)

    if not status in [200, 201]:
        evt.log.error(data)

    customer_room_id = data.get("room_id")
    if customer_room_id:
        agent_id = await evt.matrix.agent_manager.get_room_agent(
            room_id=customer_room_id
        )

        if agent_id and agent_id != evt.sender:
            agent_displayname = await evt.intent.get_displayname(user_id=agent_id)
            return_params[
                "reply"
            ] = "The agent <agent_displayname> is already in room with <number>"
        else:
            await evt.intent.send_text(
                room_id=data.get("room_id"), text=template_message, html=markdown(template_message)
            )
            await evt.acd_appservice.matrix.agent_manager.force_join_agent(
                room_id=data.get("room_id"), agent_id=evt.sender
            )
            agent_displayname = await evt.intent.get_displayname(user_id=evt.sender)

    return_params["sender_id"] = evt.sender
    return_params["phone_number"] = phone_number
    return_params["room_id"] = data.get("room_id")
    return_params["agent_displayname"] = agent_displayname if agent_displayname else "null"
    if not return_params.get("reply"):
        return_params["reply"] = (
            data.get("error")
            if data.get("error")
            else "Now you are joined in room with <number>, message was sent."
        )
    cmd_front_msg = f"!element pm {json.dumps(return_params)}"
    await evt.reply(text=cmd_front_msg)
