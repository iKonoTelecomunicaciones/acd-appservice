import itertools
import logging
from asyncio import sleep
from typing import List

from mautrix.appservice import IntentAPI
from mautrix.util.logging import TraceLogger

from .agent_manager import AgentManager
from .config import Config
from .portal import Portal, PortalState
from .queue import Queue
from .util.business_hours import BusinessHour


class EnqueuedPortals:
    log: TraceLogger = logging.getLogger("acd.agent_manager")

    def __init__(
        self, config: Config, intent: IntentAPI, pupet_pk: int, agent_manager: AgentManager
    ) -> None:
        self.config = config
        self.business_hours = BusinessHour(config=config, intent=intent)
        self.puppet_pk = pupet_pk
        self.agent_manager = agent_manager

    async def process_enqueued_portals(self):
        try:
            while True:
                # Stop process enqueued rooms if the conversation is not within the business hour
                if await self.business_hours.is_not_business_hour():
                    self.log.debug(
                        (
                            f"[{PortalState.ENQUEUED.value}] rooms process is stopped,"
                            " the conversation is not within the business hour"
                        )
                    )
                    await sleep(self.config["acd.search_pending_rooms_interval"])
                    continue

                enqueued_portals: List[Portal] = await Portal.get_rooms_by_state_and_puppet(
                    state=PortalState.ENQUEUED, fk_puppet=self.puppet_pk
                )

                grouped_enqueued_portals = [
                    list(group)
                    for key, group in itertools.groupby(
                        enqueued_portals, lambda portal: portal.selected_option
                    )
                ]

                for group in grouped_enqueued_portals:
                    queue: Queue = await Queue.get_by_room_id(group[0].selected_option)
                    available_agents_count = await queue.get_available_agents_count()
                    distruibution_range = (
                        available_agents_count * self.config["acd.queues.portals_per_agent"]
                    )
                    # Get a range of portals with respect to available agents in queue
                    enqueued_portals_to_distribute: List[Portal] = group[:distruibution_range]
                    await self.distribute_enqueued_portals(enqueued_portals_to_distribute, queue)

                await sleep(self.config["acd.search_pending_rooms_interval"])

        except Exception as error:
            self.log.exception(error)

    async def distribute_enqueued_portals(self, enqueued_portals: List[Portal], queue: Queue):
        for portal in enqueued_portals:
            if portal.get_current_agent():
                self.log.debug(
                    (
                        f"Room {portal.room_id} has already an agent, "
                        f"removing from [{PortalState.ENQUEUED.value}] rooms..."
                    )
                )
                continue

            await self.agent_manager.process_distribution(portal=portal, queue=queue)
