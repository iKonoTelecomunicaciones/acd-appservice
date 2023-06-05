from __future__ import annotations

from typing import TYPE_CHECKING

from ..queue import Queue
from ..user import User
from .models import ACDEventTypes, ACDPortalEvents
from .portal_event_models import (
    AssignEvent,
    AssignFailedEvent,
    AvailableAgentsEvent,
    ConnectEvent,
    CreateEvent,
    EnterQueueEvent,
    PortalMessageEvent,
    QueueEmptyEvent,
    ResolveEvent,
    TransferEvent,
    TransferFailedEvent,
    UICEvent,
)

if TYPE_CHECKING:
    from ..portal import Portal


async def send_portal_event(*, portal: Portal, event_type: ACDPortalEvents, **kwargs):
    if event_type == ACDPortalEvents.Create:
        customer = {
            "mxid": portal.creator,
            "account_id": portal.creator_identifier(),
            "name": await portal.creator_displayname(),
            "username": None,
        }
        event = CreateEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.Create,
            state=portal.state,
            prev_state=None,
            sender=portal.creator,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer=customer,
            bridge=portal.bridge,
        )
    elif event_type == ACDPortalEvents.UIC:
        event = UICEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.UIC,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.creator,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
        )
    elif event_type == ACDPortalEvents.EnterQueue:
        event = EnterQueueEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.EnterQueue,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            queue_room_id=kwargs.get("queue_room_id"),
        )
    elif event_type == ACDPortalEvents.Connect:
        current_agent = await portal.get_current_agent()
        event = ConnectEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.Connect,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            agent_mxid=current_agent.mxid,
        )
    elif event_type == ACDPortalEvents.Assigned:
        event = AssignEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.Assigned,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            user_mxid=kwargs.get("user_assigned"),
        )
    elif event_type == ACDPortalEvents.AssignFailed:
        event = AssignFailedEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.AssignFailed,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            user_mxid=kwargs.get("user_mxid"),
            reason=kwargs.get("reason"),
        )
    elif event_type == ACDPortalEvents.PortalMessage:
        event = PortalMessageEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.PortalMessage,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            event_mxid=kwargs.get("event_id"),
        )
    elif event_type == ACDPortalEvents.Resolve:
        agent_removed: User = kwargs.get("agent_removed")
        event = ResolveEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.Resolve,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            agent_mxid=agent_removed.mxid if agent_removed else None,
            reason=kwargs.get("reason"),
        )
    elif event_type == ACDPortalEvents.Transfer:
        event = TransferEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.Transfer,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            destination=kwargs.get("destination"),
        )
    elif event_type == ACDPortalEvents.TransferFailed:
        event = TransferFailedEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.TransferFailed,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            destination=kwargs.get("destination"),
            reason=kwargs.get("reason"),
        )
    elif event_type == ACDPortalEvents.AvailableAgents:
        queue: Queue = kwargs.get("queue")
        event = AvailableAgentsEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.AvailableAgents,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            queue_room_id=queue.room_id,
            agents_count=await queue.get_agent_count(),
            available_agents_count=await queue.get_available_agents_count(),
        )
    elif event_type == ACDPortalEvents.QueueEmpty:
        event = QueueEmptyEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.QueueEmpty,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            queue_room_id=kwargs.get("queue_room_id"),
        )

    event.send()
