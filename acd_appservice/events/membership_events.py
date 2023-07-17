from __future__ import annotations

from attr import dataclass, ib
from mautrix.types import RoomID, UserID

from .base_event import BaseEvent


@dataclass
class MemberAddedEvent(BaseEvent):
    queue: RoomID = ib(factory=RoomID)
    penalty: int = ib(factory=int)
    member: UserID = ib(factory=UserID)


@dataclass
class MemberRemovedEvent(BaseEvent):
    queue: RoomID = ib(factory=RoomID)
    member: UserID = ib(factory=UserID)
