from __future__ import annotations

from typing import TYPE_CHECKING

from mautrix.types import EventID, RoomID, UserID

from ..queue import Queue
from ..user import User
from .models import ACDEventTypes, ACDPortalEvents
from .portal_event import (
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
    from ..portal import Portal, PortalState


def send_transfer_failed_event(
    portal: Portal,
    destination: UserID | RoomID,
    reason: str,
):
    event = TransferFailedEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.TransferFailed,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=portal.main_intent.mxid,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        destination=destination,
        reason=reason,
    )
    event.send()


def send_assign_failed_event(portal: Portal, user_mxid: UserID, reason: str):
    event = AssignFailedEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.AssignFailed,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=portal.main_intent.mxid,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        user_mxid=user_mxid,
        reason=reason,
    )
    event.send()


async def send_create_portal_event(portal: Portal):
    customer = {
        "mxid": portal.creator,
        "account_id": portal.creator_identifier(),
        "name": await portal.creator_displayname(),
        "username": None,
    }
    create_event = CreateEvent(
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

    create_event.send()


def send_uic_event(portal: Portal):
    uic_event = UICEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.UIC,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=portal.creator,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
    )

    uic_event.send()


def send_enterqueue_event(portal: Portal, queue_room_id: RoomID, sender: UserID):
    enter_queue_event = EnterQueueEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.EnterQueue,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=sender,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        queue_room_id=queue_room_id,
    )
    enter_queue_event.send()


async def send_connect_event(portal: Portal):
    current_agent = await portal.get_current_agent()
    connect_event = ConnectEvent(
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
    connect_event.send()


def send_assign_event(portal: Portal, sender: UserID, user_assigned: UserID):
    assign_agent = AssignEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.Assigned,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=sender,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        user_mxid=user_assigned,
    )
    assign_agent.send()


def send_portal_message_event(portal: Portal, sender: UserID, event_id: EventID):
    message_event = PortalMessageEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.PortalMessage,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=sender,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        event_mxid=event_id,
    )
    message_event.send()


def send_resolve_event(portal: Portal, sender: UserID, reason: str, agent_removed: User):
    resolve_event = ResolveEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.Resolve,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=sender,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        agent_mxid=agent_removed.mxid if agent_removed else None,
        reason=reason,
    )
    resolve_event.send()


def send_transfer_event(portal: Portal, sender: UserID, destination: UserID | RoomID):
    transfer_event = TransferEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.Transfer,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=sender,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        destination=destination,
    )
    transfer_event.send()


async def send_available_agents_event(portal: Portal, queue: Queue):
    available_agents_event = AvailableAgentsEvent(
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
    available_agents_event.send()


def send_queue_empty_event(portal: Portal, queue_room_id: RoomID):
    queue_empty_event = QueueEmptyEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.QueueEmpty,
        state=portal.state,
        prev_state=portal.prev_state,
        sender=portal.main_intent.mxid,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        queue_room_id=queue_room_id,
    )
    queue_empty_event.send()
