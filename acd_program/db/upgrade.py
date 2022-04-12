"""Este el archivo de migraciones de la bd, se crea cada migración dada una versión"""

from asyncpg import Connection
from mautrix.util.async_db import UpgradeTable

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE "user" (
        mxid        TEXT PRIMARY KEY,
        email       TEXT,
        room_id     TEXT,
        notice_room TEXT
        )"""
    )
    await conn.execute(
        """CREATE TABLE puppet (
        custom_mxid   TEXT PRIMARY KEY,
        name          TEXT,
        username      TEXT,
        photo_id      TEXT,
        photo_mxc     TEXT,
        name_set      BOOLEAN NOT NULL DEFAULT false,
        avatar_set    BOOLEAN NOT NULL DEFAULT false,
        is_registered BOOLEAN NOT NULL DEFAULT false,
        access_token  TEXT,
        next_batch    TEXT,
        base_url      TEXT
    )"""
    )
