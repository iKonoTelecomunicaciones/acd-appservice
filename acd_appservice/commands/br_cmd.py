from typing import Dict

from .handler import CommandArg, CommandEvent, command_handler

cmd = CommandArg(
    name="cmd",
    help_text="Command that will be forwarded for the acd[n] that listens to it.",
    is_required=True,
    example="!wa help",
)


@command_handler(
    name="br_cmd",
    help_text=("This command works as an echo"),
    help_args=[cmd],
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

    if not evt.args_list:
        detail = "You have not sent the argument command"
        evt.log.error(detail)
        await evt.reply(detail)
        return {"data": {"error": detail}, "status": 422}

    command = " ".join(evt.args_list)
    await evt.intent.send_text(room_id=evt.room_id, text=command)
