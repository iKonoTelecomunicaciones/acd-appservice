from __future__ import annotations

from attr import dataclass, ib
from mautrix.types import EventID, RoomID, UserID

from .base_event import BaseEvent


@dataclass
class PortalEvent(BaseEvent):
    room_id: RoomID = ib(factory=RoomID)
    acd: UserID = ib(factory=UserID)
    customer_mxid: UserID = ib(factory=UserID)


@dataclass
class CreateEvent(BaseEvent):
    room_id: RoomID = ib(factory=RoomID)
    acd: UserID = ib(factory=UserID)
    customer: dict = ib(factory=dict)
    bridge: str = ib(factory=str)


@dataclass
class UICEvent(PortalEvent):
    pass


@dataclass
class EnterQueueEvent(PortalEvent):
    queue_room_id: RoomID = ib(factory=RoomID)


@dataclass
class ConnectEvent(PortalEvent):
    agent_mxid: UserID = ib(factory=UserID)


@dataclass
class AssignEvent(PortalEvent):
    user_mxid: UserID = ib(factory=UserID)


@dataclass
class AssignFailedEvent(PortalEvent):
    user_mxid: UserID = ib(factory=UserID)
    reason: str = ib(factory=str)


@dataclass
class PortalMessageEvent(PortalEvent):
    event_mxid: EventID = ib(factory=EventID)


@dataclass
class ResolveEvent(PortalEvent):
    agent_mxid: UserID = ib(factory=UserID)


@dataclass
class TransferEvent(PortalEvent):
    destination: UserID | RoomID = ib(factory=UserID)


@dataclass
class TransferFailedEvent(PortalEvent):
    destination: UserID | RoomID = ib(factory=UserID)
    reason: str = ib(factory=str)


@dataclass
class AvailableAgentsEvent(PortalEvent):
    queue_room_id: str = ib(factory=str)
    agents_count: int = ib(factory=int)
    available_agents_count: int = ib(factory=int)


@dataclass
class QueueEmptyEvent(EnterQueueEvent):
    pass
