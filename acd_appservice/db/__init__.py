from mautrix.util.async_db import Database

from .message import Message
from .puppet import Puppet
from .queue import Queue
from .queue_membership import QueueMembership
from .portal import Portal
from .upgrade import upgrade_table
from .user import User


def init(db: Database) -> None:
    for table in [Puppet, Portal, Message, User, Queue, QueueMembership]:
        table.db = db


__all__ = [
    "upgrade_table",
    "Puppet",
    "Portal",
    "init",
    "Message",
    "User",
    "Queue",
    "QueueMembership",
]
