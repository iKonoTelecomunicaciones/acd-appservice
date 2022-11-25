"""Este el archivo de migraciones de la bd, se crea cada migración dada una versión"""

from asyncpg import Connection
from mautrix.util.async_db import UpgradeTable

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE puppet (
        pk              SERIAL PRIMARY KEY,
        email           TEXT,
        phone           TEXT,
        bridge          TEXT,
        photo_id        TEXT,
        photo_mxc       TEXT,
        name_set        BOOLEAN NOT NULL DEFAULT false,
        avatar_set      BOOLEAN NOT NULL DEFAULT false,
        is_registered   BOOLEAN NOT NULL DEFAULT false,
        custom_mxid     TEXT,
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
        "ALTER TABLE room ADD CONSTRAINT FK_puppet_room FOREIGN KEY (fk_puppet) references puppet (pk)"
    )

    await conn.execute(
        """CREATE TABLE pending_room (
        id                  SERIAL PRIMARY KEY,
        room_id             TEXT NOT NULL,
        selected_option     TEXT,
        fk_puppet           INT NOT NULL,
        UNIQUE (room_id)
        )"""
    )
    await conn.execute(
        "ALTER TABLE pending_room ADD CONSTRAINT FK_puppet_p_room FOREIGN KEY (fk_puppet) references puppet (pk)"
    )

    await conn.execute(
        """CREATE TABLE message (
        event_id            TEXT PRIMARY KEY,
        room_id             TEXT NOT NULL,
        sender              TEXT NOT NULL,
        receiver            TEXT NOT NULL,
        timestamp_send      BIGINT,
        timestamp_read      BIGINT,
        was_read            BOOLEAN NOT NULL DEFAULT false
        )"""
    )


@upgrade_table.register(description="Table user")
async def upgrade_v2(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE "user" (
        id                  SERIAL PRIMARY KEY,
        mxid                TEXT UNIQUE,
        management_room     TEXT
        )"""
    )
    await conn.execute("""ALTER TABLE puppet RENAME COLUMN photo_id TO destination""")


@upgrade_table.register(description="Table queue and queue_membership")
async def upgrade_v3(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE queue (
        id          SERIAL PRIMARY KEY,
        name        TEXT,
        room_id     TEXT NOT NULL,
        description TEXT
        )"""
    )

    await conn.execute(
        """CREATE TABLE queue_membership (
        id            SERIAL PRIMARY KEY,
        fk_user       INT NOT NULL,
        fk_queue      INT NOT NULL,
        creation_date TIMESTAMP,
        state_date    TIMESTAMP,
        pause_date    TIMESTAMP,
        pause_reason  TEXT,
        state         TEXT,
        paused        BOOLEAN,
        UNIQUE (fk_user, fk_queue)
        )"""
    )
    await conn.execute(
        'ALTER TABLE queue_membership ADD CONSTRAINT FK_user_queue_membership FOREIGN KEY (fk_user) references "user" (id)'
    )
    await conn.execute(
        "ALTER TABLE queue_membership ADD CONSTRAINT FK_queue_queue_membership FOREIGN KEY (fk_queue) references queue (id)"
    )
    await conn.execute("CREATE INDEX idx_queue_room_id ON queue(room_id)")
    await conn.execute("CREATE INDEX idx_queue_membership_user ON queue_membership(fk_user)")
    await conn.execute("CREATE INDEX idx_queue_membership_queue ON queue_membership(fk_queue)")
