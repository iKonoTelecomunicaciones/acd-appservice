from __future__ import annotations

import logging

from aiohttp import ClientSession
from mautrix.util.logging import TraceLogger

from ..config import Config


class Base:
    log: TraceLogger = logging.getLogger("acd.client")
    config: Config
    session: ClientSession
