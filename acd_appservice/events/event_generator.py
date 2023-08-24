from __future__ import annotations

from typing import TYPE_CHECKING

from ..queue import Queue
from ..user import User
from .event_types import ACDEventTypes, ACDMemberEvents, ACDMembershipEvents, ACDPortalEvents
from .member_events import MemberLoginEvent, MemberLogoutEvent, MemberPauseEvent
from .membership_events import MemberAddedEvent, MemberRemovedEvent
from .portal_events import (
    AssignEvent,
    AssignFailedEvent,
    AvailableAgentsEvent,
    BICEvent,
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
            "account_id": await portal.creator_identifier(),
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
    elif event_type == ACDPortalEvents.BIC:
        event = BICEvent(
            event_type=ACDEventTypes.PORTAL,
            event=ACDPortalEvents.BIC,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            destination=kwargs.get("destination"),
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
            user_mxid=kwargs.get("assigned_user"),
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


async def send_member_event(event_type: ACDMemberEvents, **kwargs):
    if event_type == ACDMemberEvents.MemberLogin:
        event = MemberLoginEvent(
            event_type=ACDEventTypes.MEMBER,
            event=ACDMemberEvents.MemberLogin,
            sender=kwargs.get("sender"),
            queue=kwargs.get("queue"),
            member=kwargs.get("member"),
            penalty=kwargs.get("penalty"),
        )
    elif event_type == ACDMemberEvents.MemberLogout:
        event = MemberLogoutEvent(
            event_type=ACDEventTypes.MEMBER,
            event=ACDMemberEvents.MemberLogout,
            sender=kwargs.get("sender"),
            queue=kwargs.get("queue"),
            member=kwargs.get("member"),
        )
    elif event_type == ACDMemberEvents.MemberPause:
        event = MemberPauseEvent(
            event_type=ACDEventTypes.MEMBER,
            event=ACDMemberEvents.MemberPause,
            sender=kwargs.get("sender"),
            queue=kwargs.get("queue"),
            member=kwargs.get("member"),
            paused=kwargs.get("paused"),
            pause_reason=kwargs.get("pause_reason"),
        )

    event.send()


async def send_membership_event(event_type: ACDMembershipEvents, **kwargs):
    if event_type == ACDMembershipEvents.MemberAdd:
        event = MemberAddedEvent(
            event_type=ACDEventTypes.MEMBERSHIP,
            event=ACDMembershipEvents.MemberAdd,
            queue=kwargs.get("queue"),
            member=kwargs.get("member"),
            penalty=kwargs.get("penalty"),
            sender=kwargs.get("sender"),
        )
    elif event_type == ACDMembershipEvents.MemberRemove:
        event = MemberRemovedEvent(
            event_type=ACDEventTypes.MEMBERSHIP,
            event=ACDMembershipEvents.MemberRemove,
            queue=kwargs.get("queue"),
            member=kwargs.get("member"),
            sender=kwargs.get("sender"),
        )

    event.send()
