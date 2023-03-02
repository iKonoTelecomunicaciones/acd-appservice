import nest_asyncio
import pytest

nest_asyncio.apply()


@pytest.mark.asyncio
@pytest.mark.skip
class TestQueue:
    async def test_get_by_room_id(self):
        pass

    async def test_get_by_room_id_create(self):
        pass

    async def test_insert(self):
        pass

    async def test_update(self):
        pass

    async def test_delete(self):
        pass

    async def test_add_member(self):
        pass

    async def test_update_description(self):
        pass

    async def test_update_name(self):
        pass

    async def test_get_agent_count(self):
        pass

    async def test_get_agents(self):
        pass

    async def test_remove_not_agents(self):
        pass

    async def test_get_first_online_agent(self):
        pass

    async def test_get_membership(self):
        pass
