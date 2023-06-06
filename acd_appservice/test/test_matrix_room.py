import nest_asyncio
import pytest

from ..matrix_room import MatrixRoom
from ..user import User

nest_asyncio.apply()


@pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_get_portal_user_access_methods(
        self, admin_user: User, matrix_room: MatrixRoom, acd_init
    ):
        add_method, remove_method = matrix_room.get_access_methods(
            user_id=admin_user.mxid, context="acd.access_methods.portal"
        )
        assert add_method == "invite"
        assert remove_method == "leave"

    @pytest.mark.asyncio
    async def test_get_queue_user_access_methods(
        self, admin_user: User, matrix_room: MatrixRoom, acd_init
    ):
        add_method, remove_method = matrix_room.get_access_methods(
            user_id=admin_user.mxid, context="acd.access_methods.queue"
        )
        assert add_method == "join"
        assert remove_method == "leave"

    @pytest.mark.asyncio
    async def test_get_default_access_methods(self, matrix_room: MatrixRoom, acd_init):
        user_id: str = "@mxwa_573521487741:dominio_cliente.com"
        add_method, remove_method = matrix_room.get_access_methods(
            user_id=user_id, context="acd.access_methods.portal"
        )
        assert add_method == "invite"
        assert remove_method == "leave"

    # async def test_get_joined_users(self, matrix_room: MatrixRoom):
    #     pass
