import asyncio
import json
import re
from typing import Dict

from markdown import markdown

from ..http_client import ProvisionBridge
from ..puppet import Puppet
from ..signaling import Signaling
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="pm",
    help_text=("Command that allows send a message to a customer"),
    help_args="<_dict_>",
)
async def pm(evt: CommandEvent) -> Dict:
    """It takes a phone number and a message, and sends the message to the phone number

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    Returns
    -------
        The return value of the command handler is a dict with two keys:
        - data: The data to be sent to the frontend.
        - status: The HTTP status code to be sent to the frontend.

    """

    # Checking if the command has arguments.
    if len(evt.args) < 1:
        detail = "pm command incomplete arguments"
        evt.log.error(detail)
        await evt.reply(text=detail)
        return

    # Getting the arguments of the command.
    incoming_params = (evt.text[len(evt.cmd) :]).strip()

    # Getting the phone number, template message and template name from the incoming parameters.
    data: dict = json.loads(incoming_params)
    phone_number: str = data.get("phone_number")
    template_message = data.get("template_message")
    template_name = data.get("template_name")

    puppet: Puppet = await Puppet.get_by_custom_mxid(evt.intent.mxid)

    if not puppet:
        return

    # A dict that will be sent to the frontend.
    return_params = {
        "sender_id": evt.sender,
        "phone_number": None,
        "room_id": None,
        "agent_displayname": None,
        "reply": None,
    }

    # Es el comando que se le enviara al front.
    cmd_front_msg = None
    agent_displayname = None

    # Checking if the phone number is a number and if the template name and message are not empty.

    if not phone_number.isdigit():
        return_params["reply"] = "You must specify a valid phone number with country prefix."
    if not template_name or not template_message:
        return_params["reply"] = "You must specify a template name and message"

    # Checking if the phone number starts with a plus sign, if not, it adds it.
    phone_number = phone_number if phone_number.startswith("+") else f"+{phone_number}"

    # Sending a message to the frontend.
    if return_params.get("reply"):
        cmd_front_msg = (
            f"{puppet.config['acd.frontend_command_prefix']} {evt.cmd} {json.dumps(return_params)}"
        )
        await evt.reply(text=cmd_front_msg)
        return {"data": return_params, "status": 422}

    # Sending a message to the customer.
    bridge_connector = ProvisionBridge(
        session=evt.intent.api.session, config=puppet.config, bridge=puppet.bridge
    )
    status, data = await bridge_connector.pm(user_id=evt.intent.mxid, phone=phone_number)

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
    agent_id = None
    if customer_room_id:
        agent_id = await puppet.agent_manager.get_room_agent(room_id=customer_room_id)

        # Checking if the agent is already in the room, if it is, it returns a message to the frontend.
        if agent_id and agent_id != evt.sender:
            agent_displayname = await evt.intent.get_displayname(user_id=agent_id)
            return_params[
                "reply"
            ] = "The agent <agent_displayname> is already in room with [number]"
        else:
            # If the agent is already in the room, it returns a message to the frontend.
            await puppet.agent_manager.signaling.set_chat_status(
                room_id=customer_room_id, status=Signaling.FOLLOWUP, agent=evt.sender
            )
            if agent_id == evt.sender:
                return_params["reply"] = "You are already in room with [number], message was sent."
            else:
                # Joining the agent to the room.
                await puppet.agent_manager.force_join_agent(
                    room_id=data.get("room_id"), agent_id=evt.sender
                )

            agent_displayname = await evt.intent.get_displayname(user_id=evt.sender)

            if puppet.config[f"bridges.{puppet.bridge}.send_template_command"]:
                await bridge_connector.gupshup_template(
                    user_id=evt.intent.mxid, room_id=data.get("room_id"), template=template_message
                )
            else:
                await evt.intent.send_text(
                    room_id=data.get("room_id"),
                    text=template_message,
                    html=markdown(template_message),
                )

    # Setting the return_params dict with the sender_id, phone_number, room_id and agent_displayname.
    return_params["sender_id"] = evt.sender
    return_params["phone_number"] = phone_number
    # Cuando ya hay otro agente en la sala, se debe enviar room_id en None
    return_params["room_id"] = None if agent_id and agent_id != evt.sender else data.get("room_id")
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

    # If the reply is not set, it sets the reply to the default message.
    # Si reply no tiene contenido, significa que no ha ocurrido ningún error
    # y se puede concluir que el agente se puede unir a la sala y que
    # el mensaje fue enviado.
    if not return_params.get("reply"):
        # the room is marked as followup and campaign from previous room state
        # is not kept
        await puppet.agent_manager.signaling.set_chat_status(
            room_id=customer_room_id,
            status=Signaling.FOLLOWUP,
            agent=evt.sender,
            campaign_room_id=None,
            keep_campaign=False,
        )
        # clear campaign in the ik.chat.campaign_selection state event
        await puppet.agent_manager.signaling.set_selected_campaign(
            room_id=customer_room_id, campaign_room_id=None
        )
        if puppet.config["acd.supervisors_to_invite.invite"]:
            asyncio.create_task(puppet.room_manager.invite_supervisors(room_id=customer_room_id))

        # kick menu bot
        evt.log.debug(f"Kicking the menubot out of the room {customer_room_id}")
        try:
            await puppet.room_manager.menubot_leaves(
                room_id=customer_room_id,
                reason=f"{evt.sender} pm existing room {customer_room_id}",
            )
        except Exception as e:
            evt.log.exception(e)

        return_params["reply"] = "Now you are joined in room with [number], message was sent."

    # Sending a message to the frontend.
    cmd_front_msg = (
        f"{puppet.config['acd.frontend_command_prefix']} {evt.cmd} {json.dumps(return_params)}"
    )
    await evt.reply(text=cmd_front_msg)

    # Returning a dict with two keys:
    #     - data: The data to be sent to the frontend.
    #     - status: The HTTP status code to be sent to the frontend.
    return {"data": return_params, "status": status}
