"""Este el archivo de migraciones de la bd, se crea cada migración dada una versión"""

from asyncpg import Connection
from mautrix.util.async_db import UpgradeTable

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE puppet (
        pk              SERIAL PRIMARY KEY,
        custom_mxid     TEXT,
        name            TEXT,
        username        TEXT,
        photo_id        TEXT,
        photo_mxc       TEXT,
        name_set        BOOLEAN NOT NULL DEFAULT false,
        avatar_set      BOOLEAN NOT NULL DEFAULT false,
        is_registered   BOOLEAN NOT NULL DEFAULT false,
        access_token    TEXT,
        next_batch      TEXT,
        base_url        TEXT,
        control_room_id TEXT
        )"""
    )
    await conn.execute(
        """CREATE TABLE room (
        id                  SERIAL PRIMARY KEY,
        room_id             TEXT NOT NULL,
        selected_option     TEXT,
        fk_puppet           INT NOT NULL,
        UNIQUE (room_id)
        )"""
    )
    await conn.execute(
        "ALTER TABLE room ADD CONSTRAINT FK_puppet FOREIGN KEY (fk_puppet) references puppet (pk)"
    )

    await conn.execute(
        """CREATE TABLE pending_room (
        id                  SERIAL PRIMARY KEY,
        room_id             TEXT NOT NULL,
        selected_option     TEXT,
        UNIQUE (room_id)
        )"""
    )
