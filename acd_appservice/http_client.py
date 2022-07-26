from __future__ import annotations

import logging
from typing import Dict, Optional

from aiohttp import ClientSession, WSMsgType
from aiohttp.web import WebSocketResponse
from mautrix.types import UserID
from mautrix.util.logging import TraceLogger

from . import puppet as pu
from .config import Config


class BaseClass:
    log: TraceLogger = logging.getLogger("acd.http")
    config: Config
    session: ClientSession


class HTTPClient(BaseClass):
    def __init__(self):
        self.session = None

    async def init_session(self):
        try:
            self.session = ClientSession()
        except Exception as e:
            self.log.exception(f"Error creating aiohttp session: {e}")


class IkonoAPIClient(BaseClass):
    def __init__(self, session: ClientSession, config: Config, user_id: UserID):
        self.session = session
        self.config = config
        self.user_id = user_id
        self.api_token = None

    async def get_api_token(self):

        base_url = self.config["ikono_api.base_url"]
        login_url = self.config["ikono_api.login_url"]
        data = {
            "username": self.user_id,
            "password": self.config["appservice.puppet_password"],
        }
        url = f"{base_url}{login_url}"
        try:
            async with self.session.post(url, data=data) as response:
                if response.status != 200:
                    self.log.error(
                        f"Failed to get api access token {self.user_id} {self.config['appservice.puppet_password']}: {await response.text()}"
                    )
                    return False
                response_json = await response.json()
        except Exception as e:
            self.log.error(f"Error getting api access token: {e}")
            return False

        self.api_token = response_json.get("access_token")
        return True

    async def get_request(self, url: str, data: dict = None):
        """Make get request"""

        self.log.debug(f"GET {url}")
        headers = {
            "Authorization": f"Bearer {self.api_token}",
        }

        try:
            async with self.session.get(url, headers=headers, data=data) as response:
                if response.status == 401:
                    self.log.debug("TOKEN viejo... Refrescando...")
                    await self.get_api_token()
                    headers = {"Authorization": f"Bearer {self.api_token}"}
                    async with self.session.get(url, headers=headers, data=data) as response:
                        response_json = await response.json()
                else:
                    response_json = await response.json()
                return response.status, response_json
        except Exception as e:
            self.log.error(f"Error in GET {url} : {e}")
            return (500, None)


class ProvisionBridge(BaseClass):
    def __init__(self, session: ClientSession, config: Config):
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
        puppet: pu.Puppet,
        ws_customer: Optional[WebSocketResponse] = None,
        easy_mode: bool = False,
    ):
        """The function connects to the bridge websocket, and sends the data to the client

        Parameters
        ----------
        puppet : pu.Puppet
            The puppet of the user requesting the qr.
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
        # the puppet.mxid of the user requesting the qr must also be sent to /v1/login.
        async with self.session.ws_connect(
            f"{self.url_base}/v1/login",
            headers=self.headers,
            params={"user_id": puppet.mxid},
        ) as ws_bridge:
            async for msg in ws_bridge:
                # Checking if the message is a text message, and if it is,
                # it is checking if the message is a success or not.
                if msg.type == WSMsgType.TEXT:
                    data = msg.json()
                    if data.get("code") or data.get("success"):
                        # if the connection is to return the first qr sent by the bridge
                        # then as soon as we send the response to the client
                        self.log.info(f"Sending data to {puppet.mxid}  :: data: {data}")
                        if easy_mode and ws_customer is None:
                            await ws_bridge.close()
                            return {"data": data, "status": 200}
                        if not easy_mode and not ws_customer.closed:
                            status = 201 if data.get("phone") else 200
                            puppet.phone = data.get("phone")
                            await puppet.save()
                            await ws_customer.send_json({"data": data, "status": status})

                    # If success == False, the connection to the bridge is terminated.
                    elif not data.get("success"):
                        self.log.info(
                            f"Closed connection for {puppet.mxid} and ws_bridge; Reason: {msg.json()}"
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

    async def pm(self, user_id: UserID, phone: str) -> tuple[int, Dict]:
        """It sends a private message to a user.

        Parameters
        ----------
        user_id : UserID
            The user_id of the user you want to send the message to.
        phone : str
            The phone number to send the message to.

        Returns
        -------
            A tuple of the status code and the data.

        """
        try:
            response = await self.session.post(
                url=f"{self.url_base}/v1/pm/{phone}",
                headers=self.headers,
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return 500, {"error": str(e)}

        data = await response.json()
        if not response.status in [200, 201]:
            self.log.error(data)

        return response.status, data

    async def ping(self, user_id: UserID) -> Dict:
        """It sends a ping to the user with the given user_id.

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to ping.

        Returns
        -------
            A dictionary with the key "error" and the value of the error message.

        """

        try:
            response = await self.session.get(
                url=f"{self.url_base}/v1/ping",
                headers=self.headers,
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return {"error": str(e)}

        data = await response.json()
        if not response.status in [200, 201]:
            self.log.error(data)
            return

        return data


client = HTTPClient()
