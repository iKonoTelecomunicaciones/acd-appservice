from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from mautrix.appservice import IntentAPI
from mautrix.types import EventType, RoomID, StateEventContent, UserID
from mautrix.util.logging import TraceLogger

from .config import Config


class Signaling:
    """Send custom chat related events (status, campaign_selection, etc.)."""

    config: Config
    log: TraceLogger = logging.getLogger("acd.signaling")

    CHAT_STATUS_EVENT_TYPE = "ik.chat.status"
    CAMPAIGN_EVENT_TYPE = "ik.chat.campaign.assigned"
    POWER_LEVEL_EVENT_TYPE = "m.room.power_levels"
    ROOM_NAME_EVENT_TYPE = "m.room.name"
    JOIN_RULES = "m.room.join_rules"
    HISTORY_VISIBILITY = "m.room.history_visibility"
    CHAT_CONNECT = "ik.chat.connect"

    # different chat statuses:
    OPEN = "OPEN"
    PENDING = "PENDING"
    FOLLOWUP = "FOLLOWUP"
    RESOLVED = "RESOLVED"

    def __init__(self, intent: IntentAPI, config: Config):
        self.intent = intent
        self.config = config

    async def set_chat_status(
        self,
        room_id: RoomID,
        status: str,
        campaign_room_id: RoomID = None,
        agent: UserID = None,
        keep_campaign: bool = True,
        keep_agent: bool = True,
    ):
        """Build chat status event data and send the event.

        Parameters
        ----------
        room_id
            room id of the chat.
        status
            open -> Not resolved and no agent assigned. No campaign or agent
            pending -> wating response from agent. Has campaign and agent
            followup -> waiting response from customer. Has campaign and agent
            resolved -> resolved. Has campaign and agent
        campaign_room_id
            the campaign that the customer selected. In open chats, this is None
        agent
            the agent assigned to the chat. In open chats, this is None
        keep_campaign
            whether or not to keep the current state campaign for the room.
            This it True by default, but can be False when a customer is transferred to a specific
            agent and not a room, so the campaign_room must be updated to None in the room state
        keep_agent
            whether or not to keep the current state agent for the room
        """
        # if chat is pending or followup and the assigned agent or selected campaign_id
        # has not changed, keep the old values
        if status in [self.PENDING, self.FOLLOWUP, self.RESOLVED] and (
            keep_campaign or keep_agent
        ):
            chat_data = await self.get_chat_data(room_id)
            if chat_data:
                campaign_room_id = (
                    chat_data.get("campaign_room_id")
                    if not campaign_room_id and keep_campaign
                    else campaign_room_id
                )
                agent = chat_data.get("agent") if not agent and keep_agent else agent

        content = {"status": status, "campaign_room_id": campaign_room_id, "agent": agent}
        await self.send_state_event(
            room_id=room_id, event_type=self.CHAT_STATUS_EVENT_TYPE, content=content
        )
        self.log.debug(f"Setting {room_id} to {status}")

    async def set_selected_campaign(self, room_id: RoomID, campaign_room_id: RoomID):
        """It sends a state event to the room with the given room ID,
        with the given campaign room ID as the content

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to send the event to.
        campaign_room_id : RoomID
            The room ID of the campaign to be selected.

        """
        content = {"campaign_room_id": campaign_room_id}
        await self.send_state_event(
            room_id=room_id, event_type=self.CAMPAIGN_EVENT_TYPE, content=content
        )

    async def set_chat_connect_agent(
        self,
        room_id: RoomID,
        agent: UserID,
        source: UserID,
        campaign_room_id: RoomID = None,
        previous_agent: UserID = None,
    ):
        """It sends a state event to the room with the room ID `room_id`
        with the event type `CHAT_CONNECT` and the content `content`

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to send the event to.
        agent : UserID
            The user ID of the agent that is being connected to the chat.
        source : UserID
            The user ID of the user who initiated the connection.
        campaign_room_id : RoomID
            The room ID of the campaign that the agent is connected to.
        previous_agent : UserID
            The agent that was previously assigned to the chat.

        """
        content = {
            "agent": agent,
            "source": source,
            "campaign_room_id": campaign_room_id,
            "previous_agent": previous_agent,
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.log.debug(f"CONNECT event {agent} to {room_id} --> {source}")
        await self.send_state_event(room_id=room_id, event_type=self.CHAT_CONNECT, content=content)

    async def send_state_event(
        self,
        room_id: RoomID,
        event_type: EventType,
        content: StateEventContent | dict[str, Any] = None,
    ):
        """It sends a state event to the room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to send the event to.
        event_type : EventType
            The type of event to send.
        content : StateEventContent | dict[str, Any]
            The content of the event.

        """
        asyncio.create_task(
            self.put_room_state(room_id=room_id, event_type=event_type, content=content)
        )

    async def put_room_state(
        self,
        room_id: RoomID,
        event_type: EventType,
        content: StateEventContent | dict[str, Any] = None,
    ) -> None:
        """It tries to send a state event to the room, and if it fails,
        it waits 2 seconds and tries again

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to send the state event to.
        event_type : EventType
            The type of event to send.
        content : StateEventContent | dict[str, Any]
            The content of the event.

        """
        for attempt in range(10):
            try:
                await self.intent.send_state_event(
                    room_id=room_id, event_type=event_type, content=content
                )
                break
            except Exception as e:
                self.log.exception(f"Failed to put state event attempt {attempt} to {room_id} : ")
                await asyncio.sleep(2)

    async def get_chat_data(self, room_id: RoomID) -> StateEventContent:
        """It gets the chat status for a given room

        Parameters
        ----------
        room_id : RoomID
            The room ID of the room you want to get the chat status of.

        Returns
        -------
            The chat status event content.

        """
        chat_status = None
        try:
            chat_status = await self.intent.get_state_event(
                room_id=room_id, event_type=self.CHAT_STATUS_EVENT_TYPE
            )
        except Exception as e:
            self.log.error(f"Failed to get chat status {room_id}")

        return chat_status
