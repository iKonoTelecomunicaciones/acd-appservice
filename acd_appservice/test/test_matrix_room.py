import nest_asyncio
import pytest

from ..matrix_room import MatrixRoom

nest_asyncio.apply()


@pytest.mark.asyncio
@pytest.mark.skip
class TestMatrixRoom:
    async def test_set_creator(self, matrix_room: MatrixRoom):
        await matrix_room.set_creator()
        assert matrix_room.creator == "@mxwa_3123456789:matrix.org"

    async def test_get_room_name(self, matrix_room: MatrixRoom):
        assert await matrix_room.get_room_name() == "Mauricio Valderrama (3123456789)"

    async def test_get_room_topic(self, matrix_room: MatrixRoom):
        assert await matrix_room.get_room_topic() == "Theory, Composition, Notation, Analysis"

    async def test_get_formatted_room_id(self, matrix_room: MatrixRoom):
        assert (
            f"[{matrix_room.room_id}](https://matrix.to/#/{matrix_room.room_id})"
            == await matrix_room.get_formatted_room_id()
        )

    # async def test_get_joined_users(self, matrix_room: MatrixRoom):
    #     pass
