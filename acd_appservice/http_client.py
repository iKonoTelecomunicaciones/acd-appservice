from __future__ import annotations

import logging
from typing import Dict, Optional

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

    async def ws_connect(
        self,
        user_id: UserID,
        ws_customer: Optional[WebSocketResponse] = None,
        easy_mode: bool = False,
    ):
        """The function connects to the bridge websocket, and sends the data to the client

        Parameters
        ----------
        user_id : UserID
            The user_id of the user requesting the qr.
        ws_customer : Optional[WebSocketResponse]
            The websocket connection to the client.
            It is the websocket we have with the customer,
            we can send information through there.
        easy_mode : bool, optional
            If True, the bridge will return the first qr sent by the bridge.

        Returns
        -------
            The data is being returned to the client.

        """
        # Connecting to the WebSocket, and sending the data to the client.
        # The shared_secret generated by the bridge config must be sent to the /v1/login endpoint.
        # the user_id of the user requesting the qr must also be sent to /v1/login.
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
                        # if the connection is to return the first qr sent by the bridge
                        # then as soon as we send the response to the client
                        self.log.info(f"Sending data to {user_id}  :: data: {msg.json()}")
                        if easy_mode and ws_customer is None:
                            await ws_bridge.close()
                            return {"data": msg.json(), "status": 200}
                        if not easy_mode and not ws_customer.closed:
                            status = 201 if data.get("phone") else 200
                            await ws_customer.send_json({"data": msg.json(), "status": status})

                    # If success == False, the connection to the bridge is terminated.
                    elif not data.get("success"):
                        self.log.info(
                            f"Closed connection for {user_id} and ws_bridge; Reason: {msg.json()}"
                        )
                        # the information sent from the bridge is sent to the client
                        # and closes the bridge and client websocket (if easy_mode == False)
                        if easy_mode and ws_customer is None:
                            await ws_bridge.close()
                            return {"data": msg.json(), "status": 422}
                        if not easy_mode and not ws_customer.closed:
                            await ws_customer.send_json({"data": msg.json(), "status": 422})
                            await ws_customer.close()
                            await ws_bridge.close()

                        break
                # If the connection to the bridge is closed or an error occurs
                elif msg.type in [WSMsgType.CLOSED, WSMsgType.ERROR]:
                    self.log.error(
                        "ws connection closed or error with exception %s" % ws_bridge.exception()
                    )
                    if ws_customer:
                        await ws_customer.close()
                    break

    async def pm(self, user_id: UserID, phone: str) -> tuple:

        response = await self.session.post(
            url=f"{self.url_base}/v1/pm/{phone}", headers=self.headers, params={"user_id": user_id}
        )
        data = await response.json()
        if not response.status in [200, 201]:
            self.log.error(data)

        return response.status, data
