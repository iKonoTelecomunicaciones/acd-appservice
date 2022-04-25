from __future__ import annotations

import logging
from typing import List

from mautrix.util.logging import TraceLogger

command_handlers: dict[str, function] = {}

log: TraceLogger = logging.getLogger("mau.matrix")

def command_handler(func: function):
    if not func.__name__ in command_handlers:
        new_func_name = func.__name__.replace("_", "-")
        command_handlers[new_func_name] = func
    print(command_handlers)
    # def command_processor(cmd: str, args: List):

async def command_processor(text: str):
    args = text.split()
    if args[0] in command_handlers:
        await command_handlers[args[0]](args[1:])
    else:
        return "Unrecognized command"





