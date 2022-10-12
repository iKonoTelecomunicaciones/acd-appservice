from typing import Dict

from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="br_cmd",
    help_text=("Command that sends a state event to matrix"),
    help_args="<_bridge_command_>",
)
async def br_cmd(evt: CommandEvent) -> Dict:
    """It takes the command arguments, joins them together, and sends them to the room

    Parameters
    ----------
    evt : CommandEvent
        CommandEvent

    Returns
    -------
        A dictionary

    """
    if len(evt.args) < 2:
        detail = f"{evt.command} command incomplete arguments"
        evt.log.error(detail)
        await evt.reply(text=detail)
        return

    command = " ".join(evt.args)
    await evt.intent.send_text(room_id=evt.room_id, text=command)
