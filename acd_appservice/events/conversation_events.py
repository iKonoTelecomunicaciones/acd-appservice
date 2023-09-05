from __future__ import annotations

from typing import Optional

from attr import dataclass, ib
from mautrix.types import EventID, RoomID, UserID

from ..db.portal import PortalState
from .base_event import BaseEvent


@dataclass
class ConversationEvent(BaseEvent):
    room_id: RoomID = ib(factory=RoomID)
    acd: UserID = ib(factory=UserID)
    customer_mxid: UserID = ib(factory=UserID)
    state: PortalState = ib(default=None)
    prev_state: Optional[PortalState] = ib(default=None)


@dataclass
class CreateEvent(BaseEvent):
    room_id: RoomID = ib(factory=RoomID)
    room_name: str = ib(factory=str)
    acd: UserID = ib(factory=UserID)
    customer: dict = ib(factory=dict)
    bridge: str = ib(factory=str)
    state: PortalState = ib(default=None)
    prev_state: Optional[PortalState] = ib(default=None)


@dataclass
class UICEvent(ConversationEvent):
    room_name: str = ib(default=None)
    bridge: str = ib(default=None)


@dataclass
class BICEvent(ConversationEvent):
    destination: UserID | RoomID = ib(factory=UserID)
    room_name: str = ib(default=None)
    bridge: str = ib(default=None)


@dataclass
class EnterQueueEvent(ConversationEvent):
    queue_room_id: RoomID = ib(factory=RoomID)
    queue_name: str = ib(factory=str)


@dataclass
class ConnectEvent(ConversationEvent):
    agent_mxid: UserID = ib(factory=UserID)


@dataclass
class AssignEvent(ConversationEvent):
    user_mxid: UserID = ib(factory=UserID)


@dataclass
class AssignFailedEvent(ConversationEvent):
    user_mxid: UserID = ib(factory=UserID)
    reason: str = ib(factory=str)


@dataclass
class PortalMessageEvent(ConversationEvent):
    event_mxid: EventID = ib(factory=EventID)


@dataclass
class ResolveEvent(ConversationEvent):
    agent_mxid: UserID = ib(factory=UserID)
    reason: str = ib(default=None)


@dataclass
class TransferEvent(ConversationEvent):
    destination: UserID | RoomID = ib(factory=UserID)


@dataclass
class TransferFailedEvent(ConversationEvent):
    destination: UserID | RoomID = ib(factory=UserID)
    reason: str = ib(factory=str)


@dataclass
class AvailableAgentsEvent(ConversationEvent):
    queue_room_id: str = ib(factory=str)
    agents_count: int = ib(factory=int)
    available_agents_count: int = ib(factory=int)


@dataclass
class QueueEmptyEvent(EnterQueueEvent):
    enqueued: bool = ib(factory=bool)
