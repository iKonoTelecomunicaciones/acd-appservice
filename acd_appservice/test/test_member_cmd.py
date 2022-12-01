from typing import Dict

import nest_asyncio
import pytest
from mautrix.util.async_db import Database

from ..commands.handler import CommandProcessor
from ..queue import Queue
from ..queue_membership import QueueMembership
from ..user import User

nest_asyncio.apply()


@pytest.mark.asyncio
class TestMemberCMD:
    async def test_member_login(self, agent_user: User, processor: CommandProcessor, queue: Dict):
        """> This function tests the memeber login command

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        test_queue: Queue = await Queue.get_by_room_id(queue.get("data").get("room_id"))
        await QueueMembership.get_by_queue_and_user(agent_user.id, test_queue.id)

        args = ["login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )
        assert response.get("status") == 200

    async def test_member_login_over_other_agent(
        self, agent_user: User, processor: CommandProcessor, queue: Dict
    ):
        """> This function tests the memeber login command using agent param

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        test_queue: Queue = await Queue.get_by_room_id(queue.get("data").get("room_id"))
        await QueueMembership.get_by_queue_and_user(agent_user.id, test_queue.id)

        args = ["login", "@agent2:dominio_cliente.com"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )
        assert response.get("status") == 403

    async def test_member_login_already_login(
        self, agent_user: User, processor: CommandProcessor, queue: Dict
    ):

        """> The function tests that a member can login to a queue, and that if they try to login again,
        they get a message saying they are already logged in

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        test_queue: Queue = await Queue.get_by_room_id(queue.get("data").get("room_id"))
        await QueueMembership.get_by_queue_and_user(agent_user.id, test_queue.id)

        args = ["login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )

        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )
        assert response.get("status") == 409

    async def test_member_logout(self, agent_user: User, processor: CommandProcessor, queue: Dict):

        """It tests the member logout command.

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to login and logout.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        test_queue: Queue = await Queue.get_by_room_id(queue.get("data").get("room_id"))
        await QueueMembership.get_by_queue_and_user(agent_user.id, test_queue.id)

        args = ["login"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )

        args = ["logout"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )
        assert response.get("status") == 200

    async def test_member_logout_already_logout(
        self, agent_user: User, processor: CommandProcessor, queue: Dict
    ):

        """> The function tests that a member can login to a queue, and that if they try to login again,
        they get a message saying they are already logged in

        Parameters
        ----------
        agent_user : User
            This is the user that will be used to send the command.
        processor : CommandProcessor
            CommandProcessor
        queue : Dict
            A list of queue that the user is a member of.

        """

        test_queue: Queue = await Queue.get_by_room_id(queue.get("data").get("room_id"))
        await QueueMembership.get_by_queue_and_user(agent_user.id, test_queue.id)

        args = ["logout"]
        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )

        response = await processor.handle(
            sender=agent_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )
        assert response.get("status") == 409

    async def test_member_login_by_admin(
        self,
        db: Database,
        admin_user: User,
        agent_user: User,
        processor: CommandProcessor,
        queue: Dict,
    ):
        test_queue: Queue = await Queue.get_by_room_id(queue.get("data").get("room_id"))
        await QueueMembership.get_by_queue_and_user(agent_user.id, test_queue.id)

        args = ["login", agent_user.mxid]
        response = await processor.handle(
            sender=admin_user,
            command="member",
            args_list=args,
            is_management=False,
            room_id=queue.get("data").get("room_id"),
        )
        assert response.get("status") == 200
