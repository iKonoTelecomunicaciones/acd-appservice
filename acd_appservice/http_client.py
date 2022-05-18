from __future__ import annotations

import logging
from typing import Dict

from aiohttp import ClientSession, WSMsgType, web
from aiohttp.web import WebSocketResponse
from mautrix.types import UserID
from mautrix.util.logging import TraceLogger

from .config import Config


class BaseClass:
    log: TraceLogger = logging.getLogger("acd.http")
    config: Config
    session: ClientSession
    app: web.Application | None


class HTTPClient(BaseClass):
    def __init__(self, app: web.Application()):
        self.app = app

    async def init_session(self):
        try:
            self.session = ClientSession()
        except Exception as e:
            self.log.exception(f"Error creating aiohttp session: {e}")


class ProvisionBridge(BaseClass):
    def __init__(self, session, config):
        self.session = session
        self.config = config

    @property
    def headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.config['bridges.mautrix.provisioning.shared_secret']}"
        }

    @property
    def url_base(self) -> str:
        return self.config["bridges.mautrix.provisioning.url_base"]

    async def ws_connect(self, user_id: UserID, ws_customer: WebSocketResponse):
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
        # Al endpoint de /v1/login se debe enviar el shared_secret generado el config del bridge
        # tambien se debe enviar el user_id del usuario que solicita el qr
        async with self.session.ws_connect(
            f"{self.url_base}/v1/login",
            headers=self.headers,
            params={"user_id": user_id},
        ) as ws_bridge:
            async for msg in ws_bridge:
                # Checking if the message is a text message, and if it is,
                # it is checking if the message is a success or not.
                if msg.type == WSMsgType.TEXT:
                    data = msg.json()
                    if data.get("code") or data.get("success"):
                        self.log.info(f"Sending data to {user_id}  :: data: {msg.json()}")
                        await ws_customer.send_json({"data": msg.json(), "status": 200})

                    # Si success == False es porque termino la conexión con el bridge
                    elif not data.get("success"):
                        self.log.info(
                            f"Closed connction for {user_id} and ws_bridge; Reason: {msg.json()}"
                        )
                        # Se envia al cliente la información envidada del bridge
                        await ws_customer.send_json({"data": msg.json(), "status": 422})
                        await ws_customer.close()
                        await ws_bridge.close()
                        break
                # Si la conexion con el bridge llega a cerrarse o producir un error
                elif msg.type in [WSMsgType.CLOSED, WSMsgType.ERROR]:
                    self.log.error(
                        "ws connection closed or error with exception %s" % ws_bridge.exception()
                    )
                    await ws_customer.close()
                    break
