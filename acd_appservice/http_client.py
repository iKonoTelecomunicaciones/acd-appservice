from __future__ import annotations

import logging
from typing import Dict

from aiohttp import ClientSession, ClientWebSocketResponse, WSMsgType, web
from aiohttp.web import WebSocketResponse
from mautrix.types import UserID
from mautrix.util.logging import TraceLogger

from .config import Config


class BaseSession:
    config: Config
    session: ClientSession
    app: web.Application | None


class HTTPClient(BaseSession):
    log: TraceLogger = logging.getLogger("acd.http_client")

    def __init__(self, app: web.Application()):
        self.app = app

    async def init_session(self):
        try:
            self.session = ClientSession()
        except Exception as e:
            self.log.exception(f"Error creating aiohttp session: {e}")


class ProvisionBridgeWebSocket(BaseSession):
    log: TraceLogger = logging.getLogger("acd.websocket")

    def __init__(self, session, config):
        self.session = session
        self.config = config

    @property
    def headers_provision(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.config['bridges.mautrix.provisioning.shared_secret']}"
        }

    @property
    def url_base_provision(self) -> str:
        return self.config["bridges.mautrix.provisioning.url_base"]

    async def connect(self, user_id: UserID, custom_ws: WebSocketResponse):
        """It connects to the WebSocket, and sends the data to the client

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to connect to.
        custom_ws : WebSocketResponse
            The websocket that the user is connected to.

        """
        """Connect to the WebSocket."""
        # Connecting to the WebSocket, and sending the data to the client.
        async with self.session.ws_connect(
            f"{self.url_base_provision}/v1/login",
            headers=self.headers_provision,
            params={"user_id": user_id},
        ) as ws:
            async for msg in ws:
                # Checking if the message is a text message, and if it is,
                # it is checking if the message is a success or not.
                if msg.type == WSMsgType.TEXT:
                    data = msg.json()
                    if data.get("code"):
                        await custom_ws.send_json({"data": msg.json(), "status": 200})
                    elif not data.get("success"):
                        self.log.debug(
                            f"Close connction for {user_id} and ws_bridge; Reason: {msg.json()}"
                        )
                        await custom_ws.send_json({"data": msg.json(), "status": 422})
                        await custom_ws.close()
                        await ws.close()
                        break
                elif msg.type in [WSMsgType.CLOSED, WSMsgType.ERROR]:
                    self.log.error(
                        "ws connection closed or error with exception %s" % ws.exception()
                    )
                    await custom_ws.close()
                    break
