from mautrix.util.async_db import Database

from .message import Message
from .puppet import Puppet
from .room import Room
from .upgrade import upgrade_table
from .user import User


def init(db: Database) -> None:
    for table in [Puppet, Room, Message, User]:
        table.db = db


__all__ = ["upgrade_table", "Puppet", "Room", "init", "Message", "User"]
