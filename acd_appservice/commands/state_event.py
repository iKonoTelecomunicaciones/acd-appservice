import asyncio
import json
import re
from typing import Dict

from aiohttp import ClientSession
from markdown import markdown

from ..http_client import ProvisionBridge
from ..puppet import Puppet
from ..signaling import Signaling
from .handler import command_handler
from .typehint import CommandEvent


@command_handler(
    name="pm",
    help_text=("Command that allows send a message to a customer"),
    help_args="<_dict_>",
)
async def pm(evt: CommandEvent) -> Dict:
    pass
