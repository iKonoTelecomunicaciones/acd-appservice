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
    queue: RoomID = ib(factory=RoomID)


@dataclass
class ConnectEvent(PortalEvent):
    agent_mxid: UserID = ib(factory=UserID)


@dataclass
class AgentMessageEvent(PortalEvent):
    event_mxid: EventID = ib(factory=EventID)
    agent_mxid: UserID = ib(factory=UserID)


@dataclass
class CustomerMessageEvent(PortalEvent):
    event_mxid: EventID = ib(factory=EventID)
    agent_mxid: UserID = ib(factory=UserID)


@dataclass
class ResolveEvent(PortalEvent):
    agent_mxid: UserID = ib(factory=UserID)
    reason: str = ib(factory=str)


@dataclass
class TransferEvent(PortalEvent):
    destination: UserID | RoomID = ib(factory=UserID)
