from mautrix.util.async_db import Database

# from .portal import Portal
from .puppet import Puppet
from .upgrade import upgrade_table

# from .upgrade import upgrade_table
# from .user import User


def init(db: Database) -> None:
    for table in [Puppet]:
        table.db = db


__all__ = ["upgrade_table", "Puppet", "init"]
