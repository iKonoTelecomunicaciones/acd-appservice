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
    log: TraceLogger = logging.getLogger("acd.enqueued_portals")

    def __init__(
        self,
        config: Config,
        intent: IntentAPI,
        puppet_pk: int,
        agent_manager: AgentManager,
    ) -> None:
        self.config = config
        self.business_hours = BusinessHour(config=config, intent=intent)
        self.puppet_pk = puppet_pk
        self.agent_manager = agent_manager
        self.intent = intent

    async def process_enqueued_portals(self):
        """This function processes enqueued portals by checking if it's within business hours,
        grouping them by queue, and distributing them to available agents in the queue.

        """
        enqueued_iteration_count: int = 1

        try:
            while True:
                # If the enqueued portals distribution process took too many iterations,
                # change the enqueued time interval to distribute it faster
                if enqueued_iteration_count >= self.config["acd.enqueued_portals.max_iterations"]:
                    enqueued_interval = self.config["acd.enqueued_portals.min_time"]
                else:
                    enqueued_interval = self.config[
                        "acd.enqueued_portals.search_pending_rooms_interval"
                    ]

                # Stop process enqueued rooms if the conversation is not within the business hour
                if await self.business_hours.is_not_business_hour():
                    self.log.debug(
                        (
                            f"[{PortalState.ENQUEUED.value}] rooms process is stopped,"
                            " the conversation is not within the business hour"
                        )
                    )
                    await sleep(self.config["acd.enqueued_portals.search_pending_rooms_interval"])
                    continue

                grouped_enqueued_portals = await self.get_grouped_enqueued_portals()

                if grouped_enqueued_portals:
                    are_available_agents = False
                    for group in grouped_enqueued_portals:
                        queue: Queue = await Queue.get_by_room_id(group[0].selected_option)

                        self.log.info(
                            f"Enqueued rooms in [{queue.name} - {queue.room_id}]: {len(group)}"
                        )

                        available_agents_count = await queue.get_available_agents_count()

                        # Flag to know if iteration count will be increased
                        if available_agents_count > 0:
                            are_available_agents = True

                        portals_to_distibute_count = (
                            available_agents_count
                            * self.config["acd.enqueued_portals.portals_per_agent"]
                        )

                        # Get a range of portals with respect to available agents in queue
                        enqueued_portals_to_distribute: List[Portal] = group[
                            :portals_to_distibute_count
                        ]

                        await self.distribute_enqueued_portals(
                            enqueued_portals_to_distribute, queue
                        )

                    # Increase enqueued_iteration_count if there are available agents
                    if are_available_agents:
                        enqueued_iteration_count += 1
                else:
                    enqueued_iteration_count = 1

                await sleep(enqueued_interval)

        except Exception as error:
            self.log.exception(error)

    async def distribute_enqueued_portals(self, enqueued_portals: List[Portal], queue: Queue):
        """This function distributes enqueued portals to agents if they are available.

        Parameters
        ----------
        enqueued_portals : List[Portal]
        queue : Queue
        """
        if not enqueued_portals:
            return

        for portal in enqueued_portals:
            portal.main_intent = self.intent
            portal.bridge = self.agent_manager.bridge

            if await portal.get_current_agent():
                self.log.debug(
                    (
                        f"Room {portal.room_id} has already an agent, "
                        f"removing from [{PortalState.ENQUEUED.value}] rooms..."
                    )
                )
                continue

            response = await self.agent_manager.process_distribution(portal=portal, queue=queue)
            self.log.info(response)

    async def get_grouped_enqueued_portals(self) -> List[List[Portal]]:
        """This function groups enqueued portals by selected option in different lists to be processed later.

        Returns
        -------
            A list of lists of `Portal` objects, grouped by selected_option.
            If there are no enqueued portals, it returns `None`.

        """
        self.log.debug(f"Searching for [{PortalState.ENQUEUED.value}] rooms...")
        # Get enqueued portals sorted by queue and state_date
        enqueued_portals: List[Portal] = await Portal.get_rooms_by_state_and_puppet(
            state=PortalState.ENQUEUED, fk_puppet=self.puppet_pk
        )

        if enqueued_portals:
            # Group enqueued portals by selected option in different lists to be processed later
            # Example:
            # [
            #   [
            #       Portal(
            #               room_id: "!uenwcBsogtBGjVqMrb:example.com",
            #               selected_option: "!UIjPlZcxTSxUwtrgaL:example.com"
            #       ),
            #       Portal(
            #               room_id: "!iunfsBsogtBGjVqMrb:example.com",
            #               selected_option: "!UIjPlZcxTSxUwtrgaL:example.com"
            #       )
            #   ],
            #   [
            #       Portal(
            #               room_id: "!MsMrHCHWxDjtbehFAD:example.com",
            #               selected_option: "!PiLnvfTcxTSxUwtrgaL:example.com"
            #       ),
            #       Portal(
            #               room_id: "!kmnrtsdBsogtBGjVqMrb:example.com",
            #               selected_option: "!PiLnvfTcxTSxUwtrgaL:example.com"
            #       )
            #   ]
            # ]
            return [
                list(group)
                for key, group in itertools.groupby(
                    enqueued_portals, lambda portal: portal.selected_option
                )
            ]

        return None
