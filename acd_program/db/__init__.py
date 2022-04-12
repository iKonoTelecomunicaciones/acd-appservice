from mautrix.util.async_db import Database

from .puppet import Puppet
from .upgrade import upgrade_table
from .user import User


def init(db: Database) -> None:
    for table in (User, Puppet):
        table.db = db


__all__ = ["upgrade_table", "User", "Puppet", "init"]
