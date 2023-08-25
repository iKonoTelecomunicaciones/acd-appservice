from attr import dataclass, ib
from mautrix.types import RoomID

from ..matrix_room import RoomType
from .base_event import BaseEvent


@dataclass
class RoomNameEvent(BaseEvent):
    room_id: RoomID = ib(factory=RoomID)
    room_name: str = ib(factory=str)
    room_type: RoomType = ib(factory=RoomType)
