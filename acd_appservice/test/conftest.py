import pytest
import pytest_asyncio

from acd_appservice import room_manager

from ..config import Config


@pytest_asyncio.fixture
async def room_manager_mock():

    config = Config(
        path="acd_appservice/example-config.yaml",
        registration_path="registration.yaml",
        base_path=".",
    )

    config.load()

    return room_manager.RoomManager(config=config)


@pytest_asyncio.fixture
async def get_room_info_mock(mocker, room_manager_mock: room_manager.RoomManager):

    room_info = {
        "room_id": "!mscvqgqpHYjBGDxNym:matrix.org",
        "name": "The big bang Theory",
        "avatar": "mxc://matrix.org/AQDaVFlbkQoErdOgqWRgiGSV",
        "topic": "Theory, Composition, Notation, Analysis",
        "canonical_alias": "#thebigbangtheory:matrix.org",
        "joined_members": 2,
        "joined_local_members": 2,
        "joined_local_devices": 2,
        "version": "1",
        "creator": "@foo:matrix.org",
        "encryption": None,
        "federatable": True,
        "public": True,
        "join_rules": "invite",
        "guest_access": None,
        "history_visibility": "shared",
        "state_events": 93534,
    }
    room_manager_mock.ROOMS["!mscvqgqpHYjBGDxNym:matrix.org"] = room_info
    mocker.patch.object(room_manager.RoomManager, "get_room_info", room_info)
