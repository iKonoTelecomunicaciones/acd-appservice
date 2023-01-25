import asyncio
import json
import re
from typing import Dict

from markdown import markdown

from ..client import ProvisionBridge
from ..puppet import Puppet
from ..signaling import Signaling
from .handler import CommandArg, CommandEvent, command_handler

phone = CommandArg(
    name="phone",
    help_text="Number of the customer for whom the private chat is to be created",
    is_required=True,
    example="`573123456789` | `+573123456789`",
)

message = CommandArg(
    name="message",
    help_text="Message to be sent to the customer",
    is_required=True,
    example="Hey there!",
)


@command_handler(
    name="pm",
    help_text=("Command that allows send a message to a customer"),
    help_args=[phone, message],
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

    puppet: Puppet = await Puppet.get_by_custom_mxid(evt.intent.mxid)

    if not puppet:
        return

    message = " ".join(evt.args_list[1:])

    # A dict that will be sent to the frontend.
    return_params = {
        "sender_id": evt.sender.mxid,
        "phone_number": None,
        "room_id": None,
        "agent_displayname": None,
        "reply": None,
    }

    # Es el comando que se le enviara al front.
    cmd_front_msg = None
    agent_displayname = None

    # Checking if the phone number is a number and if the template name and message are not empty.

    if not evt.args.phone.isdigit():
        return_params["reply"] = "You must specify a valid phone number with country prefix."

    # Checking if the phone number starts with a plus sign, if not, it adds it.
    phone = evt.args.phone if evt.args.phone.startswith("+") else f"+{evt.args.phone}"

    # Sending a message to the frontend.
    if return_params.get("reply"):
        cmd_front_msg = (
            f"{puppet.config['acd.frontend_command_prefix']} {evt.command} "
            f"{json.dumps(return_params)}"
        )
        await evt.reply(text=cmd_front_msg)
        return {"data": return_params, "status": 422}

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
    agent_id = None
    if customer_room_id:
        # TODO WORKAROUND FOR NOT LINKING TO THE MENU IN A BIC
        puppet.BIC_ROOMS.add(customer_room_id)

        agent_id = await puppet.agent_manager.get_room_agent(room_id=customer_room_id)

        # Checking if the agent is already in the room, if it is, it returns a message to the frontend.
        if agent_id and agent_id != evt.sender.mxid:
            agent_displayname = await evt.intent.get_displayname(user_id=agent_id)
            return_params[
                "reply"
            ] = "The agent <agent_displayname> is already in room with [number]"
        else:
            # If the agent is already in the room, it returns a message to the frontend.
            await puppet.agent_manager.signaling.set_chat_status(
                room_id=customer_room_id, status=Signaling.FOLLOWUP, agent=evt.sender.mxid
            )
            if agent_id == evt.sender.mxid:
                return_params["reply"] = "You are already in room with [number], message was sent."
            else:
                # Joining the agent to the room.
                await puppet.agent_manager.force_join_agent(
                    room_id=data.get("room_id"), agent_id=evt.sender.mxid
                )

            agent_displayname = await evt.intent.get_displayname(user_id=evt.sender.mxid)

            if puppet.config[f"bridges.{puppet.bridge}.send_template_command"]:
                await bridge_connector.gupshup_template(
                    user_id=evt.intent.mxid, room_id=data.get("room_id"), template=message
                )
            else:
                await evt.intent.send_text(
                    room_id=data.get("room_id"),
                    text=message,
                    html=markdown(message),
                )

    # Setting the return_params dict with the sender_id, phone_number, room_id and agent_displayname.
    return_params["sender_id"] = evt.sender.mxid
    return_params["phone_number"] = phone
    # Cuando ya hay otro agente en la sala, se debe enviar room_id en None
    return_params["room_id"] = (
        None if agent_id and agent_id != evt.sender.mxid else data.get("room_id")
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
            agent=evt.sender.mxid,
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
                reason=f"{evt.sender.mxid} pm existing room {customer_room_id}",
            )
        except Exception as e:
            evt.log.exception(e)

        return_params["reply"] = "Now you are joined in room with [number], message was sent."

    # Sending a message to the frontend.
    cmd_front_msg = (
        f"{puppet.config['acd.frontend_command_prefix']} {evt.command} {json.dumps(return_params)}"
    )

    formatted_room = f"[{data.get('room_id')}](https://matrix.to/#/{data.get('room_id')})"
    formatted_user = (
        f"[{evt.args.phone}]"
        f"(https://matrix.to/#/"
        f"@{evt.config[f'bridges.{puppet.bridge}.user_prefix']}"
        f"_{evt.args.phone}:{evt.intent.domain})"
    )
    formatted_agent = (
        f"[{agent_displayname}](https://matrix.to/#/{agent_id if agent_id else evt.sender.mxid})"
    )

    await evt.reply(
        text=return_params["reply"]
        .replace("number", formatted_user if not data.get("error") else evt.args.phone)
        .replace("room", formatted_room)
        .replace("<agent_displayname>", formatted_agent)
    )

    # Returning a dict with two keys:
    #     - data: The data to be sent to the frontend.
    #     - status: The HTTP status code to be sent to the frontend.
    return {"data": return_params, "status": status}
