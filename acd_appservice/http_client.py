import logging
from asyncio import Task
from typing import Dict

from aiohttp import ClientSession, WSMsgType, web
from mautrix.types import UserID
from mautrix.util.logging import TraceLogger


class HTTPClient:
    log: TraceLogger = logging.getLogger("acd.http_client")
    app: web.Application

    CONECTIONS_WS: Dict[UserID, Task] = {}

    def __init__(self, app: web.Application()):
        self.app = app
        self.session = None

    async def init_session(self):
        try:
            self.session = ClientSession()
        except Exception as e:
            self.log.error(f"Error creating aiohttp session: {e}")

    async def new_websocket_connection(self, user_id: UserID):
        if user_id in self.CONECTIONS_WS:
            return
            
        self.CONECTIONS_WS[user_id] = self.app.loop.create_task(
            self.websocket(user_id=user_id), name=user_id
        )

    async def websocket(self, user_id: UserID):

        headers = {
            "Authorization": "Bearer gZv0kzqrZ4PFHb614IusrTuhPTDhUalJWq9xXL1K9OKBIs2bsxGD6SUOkgyN4OWP"
        }
        data = {"user_id": user_id}
        async with self.session.ws_connect(
            "http://172.17.0.1:29665/_matrix/provision/v1/login", headers=headers, params=data
        ) as ws:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self.callback(msg.data)
                elif msg.type == WSMsgType.CLOSED:
                    break
                elif msg.type == WSMsgType.ERROR:
                    break

    async def callback(self, msg):
        self.log.debug(f"############## {msg}")
