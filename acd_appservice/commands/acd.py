import logging
from typing import List

from mautrix.util.logging import TraceLogger

from .command_processor import command_handler

log: TraceLogger = logging.getLogger("mau.matrix")


@command_handler
async def acd(args: List):
    log.debug(args)
