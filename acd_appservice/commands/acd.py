import logging
from typing import List

from mautrix.util.logging import TraceLogger

from ..room_manager import RoomManager
from .handler import command_handler

log: TraceLogger = logging.getLogger("mau.acd_cmd")


@command_handler(name="acd", help_text="comando acd", help_args="<_anything_>")
async def acd(args: List) -> str:
    if len(args) < 2:
        detail = "acd command incomplete arguments"
        log.error(detail)
        return detail

    user_room_id = args[0]
    campaign_room_id = args[1] if len(args) >= 2 else None
    room_params = f"acd {user_room_id} {campaign_room_id}"
    joined_message = (args[len(room_params) :]).strip() if len(args) > 3 else None
