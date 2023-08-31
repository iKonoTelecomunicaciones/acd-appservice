from __future__ import annotations

from typing import Dict

from attr import dataclass, ib
from mautrix.types import RoomID, UserID

from .base_event import BaseEvent


@dataclass
class MemberEvent(BaseEvent):
    queue: RoomID = ib(factory=RoomID)
    queue_name: str = ib(default=None)
    member: Dict = ib(factory=Dict)


@dataclass
class MemberLoginEvent(MemberEvent):
    penalty: int = ib(factory=int)


@dataclass
class MemberLogoutEvent(MemberEvent):
    pass


@dataclass
class MemberPauseEvent(MemberEvent):
    paused: bool = ib(factory=bool)
    pause_reason: str = ib(default=None)
