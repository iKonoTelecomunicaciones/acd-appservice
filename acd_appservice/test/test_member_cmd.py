from typing import Dict

import nest_asyncio
import pytest

from ..commands.handler import CommandProcessor
from ..user import User

nest_asyncio.apply()


@pytest.mark.asyncio
class TestMemberCMD:
    async def test_member_login(self, agent_user: User, processor: CommandProcessor, queues: Dict):
        """> This function tests the memeber login command

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queues : Dict
            A list of queues that the user is a member of.

        """

        args = ["login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queues[0].get("room_id"),
        )
        assert response.get("status") == 200

    async def test_member_logout(
        self, agent_user: User, processor: CommandProcessor, queues: Dict
    ):

        """It tests the member logout command.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to login and logout.
        processor : CommandProcessor
            CommandProcessor
        queues : Dict
            A list of queues that the user is a member of.

        """

        args = ["login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queues[0].get("room_id"),
        )

        args = ["logout"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queues[0].get("room_id"),
        )
        assert response.get("status") == 200
