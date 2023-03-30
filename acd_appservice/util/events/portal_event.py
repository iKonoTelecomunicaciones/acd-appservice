from attr import dataclass, ib
from mautrix.types import RoomID, UserID

from .base_event import BaseEvent


@dataclass
class PortalEvent(BaseEvent):
    room_id: RoomID = ib(factory=str)
    acd: UserID = ib(factory=str)
    customer_mxid: UserID = ib(factory=str)


@dataclass
class CreateEvent(BaseEvent):
    room_id: RoomID = ib(factory=str)
    acd: UserID = ib(factory=str)
    customer: dict = ib(factory=dict)
    bridge: str = ib(factory=str)


@dataclass
class UICEvent(PortalEvent):
    pass


@dataclass
class EnterQueueEvent(PortalEvent):
    queue: RoomID = ib(factory=str)


@dataclass
class ConnectEvent(PortalEvent):
    agent_mxid: UserID = ib(factory=str)


@dataclass
class AgentMessageEvent(PortalEvent):
    event_mxid: str = ib(factory=str)
    agent_mxid: UserID = ib(factory=str)


@dataclass
class CustomerMessageEvent(PortalEvent):
    event_mxid: str = ib(factory=str)
    agent_mxid: UserID = ib(factory=str)


@dataclass
class ResolveEvent(PortalEvent):
    agent_mxid: UserID = ib(factory=str)
    reason: str = ib(factory=str)


@dataclass
class TransferEvent(PortalEvent):
    destination: UserID | RoomID = ib(factory=str)
