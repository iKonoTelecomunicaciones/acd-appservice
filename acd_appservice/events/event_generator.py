from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from ..matrix_room import RoomType
from ..queue import Queue
from ..user import User
from .conversation_events import (
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
from .event_types import (
    ACDConversationEvents,
    ACDEventTypes,
    ACDMemberEvents,
    ACDMembershipEvents,
    ACDRoomEvents,
)
from .member_events import MemberLoginEvent, MemberLogoutEvent, MemberPauseEvent
from .membership_events import MemberAddedEvent, MemberRemovedEvent
from .room_events import RoomNameEvent

if TYPE_CHECKING:
    from ..portal import Portal


async def send_conversation_event(*, portal: Portal, event_type: ACDConversationEvents, **kwargs):
    if event_type == ACDConversationEvents.Create:
        customer = {
            "mxid": portal.creator,
            "account_id": await portal.creator_identifier(),
            "name": await portal.creator_displayname(),
            "username": None,
        }
        event = CreateEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.Create,
            state=portal.state,
            prev_state=None,
            sender=portal.creator,
            room_id=portal.room_id,
            room_name=await portal.get_update_name(),
            acd=portal.main_intent.mxid,
            customer=customer,
            bridge=portal.bridge,
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.UIC:
        event = UICEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.UIC,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.creator,
            room_name=await portal.get_update_name(),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            bridge=portal.bridge,
            customer_mxid=portal.creator,
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.BIC:
        event = BICEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.BIC,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_name=await portal.get_update_name(),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            bridge=portal.bridge,
            destination=kwargs.get("destination"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.EnterQueue:
        event = EnterQueueEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.EnterQueue,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            queue_room_id=kwargs.get("queue_room_id"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.Connect:
        current_agent = await portal.get_current_agent()
        event = ConnectEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.Connect,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            agent_mxid=current_agent.mxid,
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.Assigned:
        event = AssignEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.Assigned,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            user_mxid=kwargs.get("assigned_user"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.AssignFailed:
        event = AssignFailedEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.AssignFailed,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            user_mxid=kwargs.get("user_mxid"),
            reason=kwargs.get("reason"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.PortalMessage:
        event = PortalMessageEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.PortalMessage,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            event_mxid=kwargs.get("event_id"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.Resolve:
        agent_removed: User = kwargs.get("agent_removed")
        event = ResolveEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.Resolve,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            agent_mxid=agent_removed.mxid if agent_removed else None,
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.Transfer:
        event = TransferEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.Transfer,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=kwargs.get("sender"),
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            destination=kwargs.get("destination"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.TransferFailed:
        event = TransferFailedEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.TransferFailed,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            destination=kwargs.get("destination"),
            reason=kwargs.get("reason"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.AvailableAgents:
        queue: Queue = kwargs.get("queue")
        event = AvailableAgentsEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.AvailableAgents,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            queue_room_id=queue.room_id,
            agents_count=await queue.get_agent_count(),
            available_agents_count=await queue.get_available_agents_count(),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDConversationEvents.QueueEmpty:
        event = QueueEmptyEvent(
            event_type=ACDEventTypes.CONVERSATION,
            event=ACDConversationEvents.QueueEmpty,
            state=portal.state,
            prev_state=portal.prev_state,
            sender=portal.main_intent.mxid,
            room_id=portal.room_id,
            acd=portal.main_intent.mxid,
            customer_mxid=portal.creator,
            queue_room_id=kwargs.get("queue_room_id"),
            timestamp=datetime.utcnow().timestamp(),
        )

    event.send()


async def send_member_event(event_type: ACDMemberEvents, **kwargs):
    if event_type == ACDMemberEvents.MemberLogin:
        event = MemberLoginEvent(
            event_type=ACDEventTypes.MEMBER,
            event=ACDMemberEvents.MemberLogin,
            sender=kwargs.get("sender"),
            queue=kwargs.get("queue"),
            queue_name=kwargs.get("queue_name"),
            member=kwargs.get("member"),
            penalty=kwargs.get("penalty"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDMemberEvents.MemberLogout:
        event = MemberLogoutEvent(
            event_type=ACDEventTypes.MEMBER,
            event=ACDMemberEvents.MemberLogout,
            sender=kwargs.get("sender"),
            queue=kwargs.get("queue"),
            queue_name=kwargs.get("queue_name"),
            member=kwargs.get("member"),
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDMemberEvents.MemberPause:
        event = MemberPauseEvent(
            event_type=ACDEventTypes.MEMBER,
            event=ACDMemberEvents.MemberPause,
            sender=kwargs.get("sender"),
            queue=kwargs.get("queue"),
            queue_name=kwargs.get("queue_name"),
            member=kwargs.get("member"),
            paused=kwargs.get("paused"),
            pause_reason=kwargs.get("pause_reason"),
            timestamp=datetime.utcnow().timestamp(),
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
            timestamp=datetime.utcnow().timestamp(),
        )
    elif event_type == ACDMembershipEvents.MemberRemove:
        event = MemberRemovedEvent(
            event_type=ACDEventTypes.MEMBERSHIP,
            event=ACDMembershipEvents.MemberRemove,
            queue=kwargs.get("queue"),
            member=kwargs.get("member"),
            sender=kwargs.get("sender"),
            timestamp=datetime.utcnow().timestamp(),
        )

    event.send()


async def send_room_event(event_type: ACDRoomEvents, room: Portal | Queue, **kwargs):
    if event_type == ACDRoomEvents.NameChange:
        room_type = RoomType.PORTAL if await room.is_portal(room.room_id) else RoomType.QUEUE
        room_name = (
            await room.get_update_name() if await room.is_portal(room.room_id) else room.name
        )

        event = RoomNameEvent(
            event_type=ACDEventTypes.ROOM,
            event=ACDRoomEvents.NameChange,
            sender=room.main_intent.mxid,
            room_id=room.room_id,
            room_name=room_name,
            room_type=room_type,
            timestamp=datetime.utcnow().timestamp(),
        )

    event.send()
