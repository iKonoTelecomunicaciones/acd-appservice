import nest_asyncio
import pytest
from mautrix.types import RoomID
from pytest_mock import MockerFixture

from ..room_manager import RoomManager

nest_asyncio.apply()


@pytest.mark.asyncio
class TestRoomManager:
    async def test_get_room_mautrix_bridge(
        self,
        mocker: MockerFixture,
        room_manager_mock: RoomManager,
        get_room_info_mock,
    ):
        """
        Returns the bridge that belongs to the room, None if the room does not have a client.
        """
        room_creator = "@mxwa_573123456789:matrix.org"

        mocker.patch.object(RoomManager, "get_room_creator", return_value=room_creator)
        room_manager_mock.intent = None
        result = await room_manager_mock.get_room_bridge(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )

        assert result == "mautrix"

    async def test_get_room_instagram_bridge(
        self,
        mocker: MockerFixture,
        room_manager_mock: RoomManager,
        get_room_info_mock,
    ):
        """
        Returns the bridge that belongs to the room, None if the room does not have a client.
        """
        room_creator = "@ig_6546846652:matrix.org"

        mocker.patch.object(RoomManager, "get_room_creator", return_value=room_creator)
        room_manager_mock.intent = None
        result = await room_manager_mock.get_room_bridge(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )

        assert result == "instagram"

    async def test_get_room_gupshup_bridge(
        self,
        mocker: MockerFixture,
        room_manager_mock: RoomManager,
        get_room_info_mock,
    ):
        """
        Returns the bridge that belongs to the room, None if the room does not have a client.
        """
        room_creator = "@gswa_573123456789:matrix.org"

        mocker.patch.object(RoomManager, "get_room_creator", return_value=room_creator)
        room_manager_mock.intent = None
        result = await room_manager_mock.get_room_bridge(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )

        assert result == "gupshup"

    async def test_not_get_room_bridge(
        self,
        mocker: MockerFixture,
        room_manager_mock: RoomManager,
        get_room_info_mock,
    ):
        """
        You should not return the room bridge, A bridge if the room has a client.
        """
        room_creator = "@agente:matrix.org"

        mocker.patch.object(RoomManager, "get_room_creator", return_value=room_creator)
        mocker.patch.object(RoomManager, "is_guest_room", return_value=False)

        room_manager_mock.intent = None
        result = await room_manager_mock.get_room_bridge(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )

        assert result == None

    async def test_is_mx_whatsapp_status_broadcast(
        self, mocker: MockerFixture, room_manager_mock: RoomManager
    ):
        """
        True if the room is whatsapp_status_broadcast, False otherwise.
        """
        room_name = "WhatsApp Status Broadcast"

        mocker.patch.object(RoomManager, "get_room_name", return_value=room_name)
        room_manager_mock.intent = None
        result = await room_manager_mock.is_mx_whatsapp_status_broadcast(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )

        assert result == True

    async def test_is_not_mx_whatsapp_status_broadcast(
        self, mocker: MockerFixture, room_manager_mock: RoomManager
    ):
        """
        True if the room is whatsapp_status_broadcast, False otherwise.
        """
        room_name = "SALA DE CONTROL"

        mocker.patch.object(RoomManager, "get_room_name", return_value=room_name)
        room_manager_mock.intent = None
        result = await room_manager_mock.is_mx_whatsapp_status_broadcast(
            room_id=RoomID("!mscvqgqpHYjBGDxNym:matrix.org")
        )
        assert result == False
