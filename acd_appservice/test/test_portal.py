import nest_asyncio
import pytest

nest_asyncio.apply()


@pytest.mark.asyncio
@pytest.mark.skip
class TestPortal:
    async def test_get_by_room_id(self):
        pass

    async def test_get_by_room_id_create(self):
        pass

    async def test_update_state(self):
        pass

    async def test_get_current_agent(self):
        pass

    async def test_is_online_agents(self):
        pass

    async def test_is_not_online_agents(self):
        pass

    async def test_is_portal(self):
        pass

    async def test_is_not_portal(self):
        pass
