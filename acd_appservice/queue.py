from __future__ import annotations

import logging
from typing import List, Optional, cast

from mautrix.appservice import IntentAPI
from mautrix.errors.base import IntentError
from mautrix.types import RoomID, UserID
from mautrix.util.logging import TraceLogger

from .db.queue import Queue as DBQueue
from .matrix_room import MatrixRoom
from .queue_membership import QueueMembership
from .user import User


class Queue(DBQueue, MatrixRoom):
    room_id: RoomID
    name: str = ""
    description: str | None = None

    log: TraceLogger = logging.getLogger("acd.queue")

    by_id: dict[int, Queue] = {}
    by_room_id: dict[RoomID, Queue] = {}

    def __init__(
        self,
        room_id: RoomID,
        name: str = "",
        description: str | None = None,
        id: int = None,
        intent: IntentAPI = None,
    ):
        DBQueue.__init__(self, id=id, name=name, room_id=room_id, description=description)
        MatrixRoom.__init__(self, room_id=self.room_id)
        self.main_intent = intent
        self.log = self.log.getChild(room_id)

    async def _add_to_cache(self) -> None:
        self.by_id[self.id] = self
        self.by_room_id[self.room_id] = self
        await self.post_init()

    def clean_cache(self):
        del self.by_room_id[self.room_id]
        del self.by_id[self.id]

    async def save(self) -> None:
        await self._add_to_cache()
        await self.update()

    async def clean_up(self):
        """It removes all members from the queue, leaves the queue, and deletes the queue"""
        try:
            members = await self.main_intent.get_joined_members(self.room_id)
        except Exception as error:
            members = None
            self.log.exception(f"Error getting members of queue {self.room_id}: {error}")

        if members:
            reason = "The queue will be removed"

            for member in members.keys():
                if self.main_intent.mxid == member:
                    continue

                await self.remove_member(member=member, reason=reason)

            await self.leave(reason=reason)
        else:
            self.log.error(f"Unable to obtain members in the queue {self.room_id}")

        self.clean_cache()

        memberships = await QueueMembership.get_by_queue(fk_queue=self.id)

        if memberships:
            for membership in memberships:
                await membership.delete()

        await self.delete()

    async def sync(self):
        """It gets the name and description of the room, saves it,
        and then gets the members of the room and adds them to the database
        """
        self.name = await self.get_room_name()
        self.description = await self.get_room_topic()

        self.log.debug(f"Syncing the memberships for this room")
        members = await self.main_intent.get_joined_members(room_id=self.room_id)
        for member in members.keys():
            if member == self.main_intent.mxid:
                continue
            user: User = await User.get_by_mxid(member)

            # Set the room (queue) tag for the member
            await user.set_room_tag(room_id=self.room_id, tag="m.queue")

            await QueueMembership.get_by_queue_and_user(fk_queue=self.id, fk_user=user.id)

        await self.save()

    @classmethod
    async def is_queue(cls, room_id: RoomID) -> bool:
        """if a queue exists for the given room, return True, otherwise return False

        Parameters
        ----------
        room_id : RoomID
            The room ID of the queue.

        Returns
        -------
            A boolean value.

        """
        queue = await cls.get_by_room_id(room_id=room_id, create=False)

        if not queue:
            return False

        return True

    async def update_description(self, new_description: Optional[str]):
        """It updates the description of the room

        Parameters
        ----------
        new_description : str
            The new description of the room.
        """
        if not new_description:
            return
        self.description = new_description.strip()
        await self.main_intent.set_room_topic(room_id=self.room_id, topic=new_description)
        await self.save()

    async def update_name(self, new_name: str):
        """It updates the name of the room

        Parameters
        ----------
        new_name : str
            The new name of the room.
        """
        if not new_name:
            return
        self.name = new_name
        await self.main_intent.set_room_name(room_id=self.room_id, name=new_name)
        await self.save()

    async def get_agent_count(self) -> int:
        """It returns the number of agents in the system

        Returns
        -------
            The number of agents in the system.

        """
        agents = await self.get_agents() or []
        return len(agents)

    async def get_available_agents_count(self) -> int:
        """This function returns the number of available agents.

        Returns
        -------
            An integer value which represents the count of available agents.

        """
        available_agents = await self.get_available_agents()
        return len(available_agents) if available_agents else 0

    async def get_agents(self) -> List[User]:
        """Get all the users in the channel, remove the bots, and return the remaining users

        Returns
        -------
            A list of users

        """
        members = []

        try:
            members = await self.get_joined_users()
        except IntentError as e:
            self.log.error(e)

        if not members:
            return members

        # remove bots from member list
        return self.remove_not_agents(members)

    async def get_available_agents(self) -> List[User] | None:
        """This function returns a list of available agents who are online and not paused,
           or None if no agents are available.

        Returns
        -------
            A list of `User` or `None` if there are no available agents.

        """

        agents: List[User] = await self.get_agents()
        available_agents = [
            agent
            for agent in agents
            if await agent.is_online(self.id) and not await agent.is_paused(self.id)
        ]
        if not available_agents:
            available_agents = None
        return available_agents

    def remove_not_agents(self, members: List[User]) -> List[User]:
        """Removes non-agents from a list of users

        Parameters
        ----------
        members : List[User]
            List[User]

        Returns
        -------
            A list of users that are agents.

        """
        only_agents: List[User] = []
        if members:
            # Removes non-agents
            only_agents = [user for user in members if user.is_agent]

        return only_agents

    async def get_first_online_agent(self) -> User | None:
        """It returns the first agent that is online in the room

        Returns
        -------
            UserID

        """
        agents: List[User] = await self.get_agents()

        if not agents:
            self.log.debug(f"There's no agent in room: {self.room_id}")
            return

        for agent in agents:
            # Switch between presence and agent operation login using config parameter
            # to verify if agent is logged in

            is_agent_online = await agent.is_online(queue_id=self.id)

            if is_agent_online:
                return agent

    async def get_membership(self, agent: User) -> QueueMembership:
        """It returns a QueueMembership object if the user is a member of the queue,
        otherwise it returns None

        Parameters
        ----------
        agent : User
            User = The user that is being added to the queue

        Returns
        -------
            A QueueMembership object

        """

        membership: QueueMembership = await QueueMembership.get_by_queue_and_user(
            fk_user=agent.id, fk_queue=self.id, create=False
        )

        if not membership:
            return

        return membership

    async def add_member(self, new_member: UserID):
        return await super().add_member(new_member=new_member, context="acd.access_methods.queue")

    async def remove_member(self, member: UserID, reason: Optional[str] = None):
        return await super().remove_member(
            member=member, context="acd.access_methods.queue", reason=reason
        )

    @classmethod
    async def get_by_room_id(cls, room_id: RoomID, *, create: bool = True) -> Queue | None:
        try:
            return cls.by_room_id[room_id]
        except KeyError:
            pass

        queue = cast(cls, await super().get_by_room_id(room_id))
        if queue is not None:
            await queue._add_to_cache()
            return queue

        if create:
            queue = cls(room_id)
            await queue.insert()
            queue = await super().get_by_room_id(room_id)
            await queue._add_to_cache()
            return queue

        return None
