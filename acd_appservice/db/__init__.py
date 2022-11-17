from mautrix.util.async_db import Database

from .message import Message
from .puppet import Puppet
from .queue import Queue
from .queue_membership import QueueMembership
from .room import Room
from .upgrade import upgrade_table
from .user import User


def init(db: Database) -> None:
    for table in [Puppet, Room, Message, User, Queue, QueueMembership]:
        table.db = db


__all__ = [
    "upgrade_table",
    "Puppet",
    "Room",
    "init",
    "Message",
    "User",
    "Queue",
    "QueueMembership",
]
