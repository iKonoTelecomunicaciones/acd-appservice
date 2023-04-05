from re import match

from ..events import ACDEventTypes, ACDPortalEvents, EnterQueueEvent
from ..portal import Portal, PortalState
from ..puppet import Puppet
from ..queue import Queue
from .handler import CommandArg, CommandEvent, command_handler

campaign_room_id = CommandArg(
    name="campaign_room_id",
    help_text="Campaign room_id where the customer will be distributed",
    is_required=True,
    example="`!foo:foo.com`",
)

joined_message = CommandArg(
    name="joined_message",
    help_text="Message that will be sent when the agent joins the customer room",
    is_required=False,
    example='"{agentname} join to room"',
)

put_enqueued_portal = CommandArg(
    name="put_enqueued_portal",
    help_text="If the chat was not distributed, should the portal be enqueued?",
    is_required=False,
    example="`yes` | `no`",
)

customer_room_id = CommandArg(
    name="customer_room_id",
    help_text="Customer room_id to be distributed",
    is_required=True,
    example="`!foo:foo.com`",
    sub_args=[campaign_room_id, joined_message, put_enqueued_portal],
)


@command_handler(
    name="acd",
    help_text=(
        "Command that allows to distribute the chat of a client, "
        "optionally a campaign room and a joining message can be given."
    ),
    help_args=[customer_room_id],
)
async def acd(evt: CommandEvent) -> str:
    """It allows to distribute the chat of a client,
    optionally a campaign room and a joining message can be given

    Parameters
    ----------
    evt : CommandEvent
        Incoming CommandEvent

    """

    if len(evt.args_list) < 2:
        detail = "You have not all arguments"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    customer_room_id = evt.args_list[0]
    campaign_room_id = evt.args_list[1]
    joined_message = ""
    put_enqueued_portal = True

    if len(evt.args_list) > 2:
        try:
            put_enqueued_portal = False if evt.args_list[3] == "no" else True
            joined_message = evt.args_list[2]
        except IndexError:
            if match("no|yes", evt.args_list[2]):
                put_enqueued_portal = False if evt.args_list[2] == "no" else True
            else:
                joined_message = evt.args_list[2]

    puppet: Puppet = await Puppet.get_by_portal(portal_room_id=customer_room_id)
    portal: Portal = await Portal.get_by_room_id(
        room_id=customer_room_id, fk_puppet=puppet.pk, intent=puppet.intent, bridge=puppet.bridge
    )
    queue: Queue = await Queue.get_by_room_id(room_id=campaign_room_id)

    if not puppet:
        return

    try:
        enter_queue_event = EnterQueueEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.EnterQueue,
            state=PortalState.ENQUEUED,
            prev_state=portal.state,
            sender=evt.sender.mxid,
            room_id=portal.room_id,
            acd=puppet.mxid,
            customer_mxid=portal.creator,
            queue=queue.room_id,
        )
        await enter_queue_event.send()

        # Changing room state to ENQUEUED by acd command
        await portal.update_state(PortalState.ENQUEUED)
        return await puppet.agent_manager.process_distribution(
            portal=portal,
            queue=queue,
            joined_message=joined_message,
            put_enqueued_portal=put_enqueued_portal,
        )
    except Exception as e:
        evt.log.exception(e)
