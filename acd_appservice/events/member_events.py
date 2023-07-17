from __future__ import annotations

from attr import dataclass, ib
from mautrix.types import RoomID, UserID

from .base_event import BaseEvent


@dataclass
class MemberLoginEvent(BaseEvent):
    queue: RoomID = ib(factory=RoomID)
    member: UserID = ib(factory=UserID)
    penalty: int = ib(factory=int)


@dataclass
class MemberLogoutEvent(BaseEvent):
    queue: RoomID = ib(factory=RoomID)
    member: UserID = ib(factory=UserID)


@dataclass
class MemberPauseEvent(BaseEvent):
    queue: RoomID = ib(factory=RoomID)
    member: UserID = ib(factory=UserID)
    paused: bool = ib(factory=bool)
    pause_reason: str = ib(default=None)
