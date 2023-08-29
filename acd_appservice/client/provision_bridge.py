from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from aiohttp import ClientSession, WSMsgType, client_exceptions
from aiohttp.web import WebSocketResponse
from mautrix.types import RoomID, UserID

from ..config import Config
from .base import Base

if TYPE_CHECKING:
    from ..puppet import Puppet


class ProvisionBridge(Base):
    def __init__(self, config: Config, session: ClientSession = None, bridge: str = "mautrix"):
        self.session = session
        self.config = config
        self.bridge = bridge
        self.log = self.log.getChild(f"provision_bridge.{bridge}")
        self.endpoints: Dict[str, str] = config[f"bridges.{bridge}.provisioning.endpoints"]

    @property
    def headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.config[f'bridges.{self.bridge}.provisioning.shared_secret']}"
        }

    @property
    def url_base(self) -> str:
        return self.config[f"bridges.{self.bridge}.provisioning.url_base"]

    async def mautrix_ws_connect(
        self,
        puppet: Puppet,
        ws_customer: Optional[WebSocketResponse] = None,
        easy_mode: bool = False,
    ):
        """The function connects to the bridge websocket, and sends the data to the client

        Parameters
        ----------
        puppet : Puppet
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
            f"{self.url_base}{self.endpoints['login']}",
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
                            if data.get("phone"):
                                puppet.phone = data.get("phone").replace("+", "")
                                status = 201
                            else:
                                status = 200

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
                url=f"{self.url_base}{self.endpoints['pm']}/{phone}",
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

    async def gupshup_template(
        self, user_id: UserID, room_id: RoomID, template: str
    ) -> tuple[int, Dict]:
        """It sends a template message to a user.

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to send the message to.
        room_id : RoomID
            The room ID of the room you want to send the message to.
        template : str
            The template message to be sent.

        Returns
        -------
            The status code and the data

        """

        try:
            response = await self.session.post(
                url=f"{self.url_base}{self.endpoints['template']}",
                headers=self.headers,
                json={"room_id": room_id, "template_message": template},
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return 500, {"error": str(e)}

        data = await response.json()
        if not response.status in [200, 201]:
            self.log.error(data)

        return response.status, data

    async def gupshup_register_app(self, user_id: UserID, data: Dict) -> tuple[int, Dict]:
        """It registers an app with Gupshup.

        Parameters
        ----------
        user_id : UserID
            The user ID of the user who is registering the app.
        data : Dict
            The data necessary to register a line
        Returns
        -------
            A tuple of the status code and the data.

        """

        try:
            response = await self.session.post(
                url=f"{self.url_base}{self.endpoints['register_app']}",
                headers=self.headers,
                json=data,
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return 500, {"error": str(e)}

        data = await response.json()
        if not response.status in [200, 201]:
            self.log.error(data)

        return response.status, data

    async def meta_register_app(self, user_id: UserID, data: Dict) -> tuple[int, Dict]:
        """Register an application in the Meta bridge.

        Parameters
        ----------
        user_id : UserID
            The user ID of the user who is registering the app.
        data : Dict
            The data necessary to register a meta facebook or instagram app
        Returns
        -------
            A tuple of the status code and the data.

        """
        try:
            response = await self.session.post(
                url=f"{self.url_base}{self.endpoints['register_app']}",
                headers=self.headers,
                json=data,
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return 500, {"error": str(e)}

        data = await response.json()
        if not response.status in [200, 201]:
            self.log.error(data)

        return response.status, data

    async def ping(self, user_id: UserID) -> tuple[int, Dict]:
        """It sends a ping to the user with the given user_id.

        Parameters
        ----------
        user_id : UserID
            The user ID of the user you want to ping.

        Returns
        -------
            A tuple with status code and a dictionary with data or the
            key "error" and the value of the error message.

        """

        try:
            response = await self.session.get(
                url=f"{self.url_base}{self.endpoints['ping']}",
                headers=self.headers,
                params={"user_id": user_id},
            )
            data = await response.json()
        except client_exceptions.ContentTypeError as err:
            error_data = {"bridge": self.bridge, "mxid": user_id, "error": await response.text()}
            self.log.error(error_data)
            return 500, error_data
        except Exception as e:
            error_data = {"bridge": self.bridge, "mxid": user_id, "error": str(e)}
            self.log.error(error_data)
            return 500, error_data

        if response.status not in [200, 201]:
            self.log.error(data)

        return response.status, data

    async def metainc_login(
        self, user_id: UserID, email: str, username: str, password: str
    ) -> tuple(int, Dict):
        """It sends a POST request to the login endpoint with the user's
        Instagram username (or Facebook email) and password

        Parameters
        ----------
        user_id : UserID
            The user ID of the puppet user who is logging in.
        email : str
            The email of the account you want to login to.
        username : str
            The username of the account you want to login to.
        password : str
            The password of the account you want to login to.

        Returns
        -------
            A tuple with the status code and dictionary with the response data or key "error"
            and the value of the error message.

        """
        try:
            bridge_credentials = {
                "instagram": {
                    "username": username,
                    "password": password,
                },
                "facebook": {
                    "email": email,
                    "password": password,
                },
            }
            data = bridge_credentials.get(self.bridge, {})
            self.log.debug(
                f"Login with {user_id} and ({email or username}) in the {self.bridge} bridge."
            )
            response = await self.session.post(
                url=f"{self.url_base}{self.endpoints['login']}",
                headers=self.headers,
                json=data,
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return 500, {"error": str(e)}

        data = await response.json()
        if response.status not in [200, 201]:
            self.log.error(await response.text())

        return response.status, data

    async def metainc_challenge(
        self,
        user_id: UserID,
        username: str,
        email: str,
        code: str,
        type_2fa: str = None,
        id_2fa: str = None,
        resend_2fa_sms: bool = False,
    ) -> tuple(int, Dict):
        """It sends a POST request to the Instagram API with the user's ID and the
        code they entered

        Parameters
        ----------
        user_id : UserID
            The user ID of the puppet account you're trying to log into.
        username: str
            The username of the Instagram account you're trying to log into
        email: str
            The email of the Facebook account you're trying to log into
        code : str
            The code number to challenge (TOTP, SMS or checkpoint)
        type_2fa: str
            Two factor authentication type (TOTP, SMS or checkpoint):
                - totp_2fa
                - sms_2fa
                - checkpoint
        id_2fa: str
            Two factor authentication identifier
        resend_2fa_sms: bool
            Re-send SMS with the 2FA code

        Returns
        -------
            A tuple with status code and a dictionary with the response data or key "error"
            and the value of the error message.

        """
        try:
            if self.bridge == "instagram":
                if type_2fa == "checkpoint":
                    # Resolve with checkpoint code
                    path = "login_checkpoint"
                    data = {"code": code}
                elif type_2fa == "sms_2fa" and resend_2fa_sms:
                    # Re-send 2FA SMS code
                    path = "login_resend_2fa_sms"
                    data = {
                        "username": username,
                        "2fa_identifier": id_2fa,
                    }
                    self.log.debug(f"Re-send 2FA SMS code to ({username}).")
                else:
                    # Resolve with 2FA code
                    path = "login_2fa"
                    data = {
                        "username": username,
                        "code": code,
                        "2fa_identifier": id_2fa,
                        "is_totp": True if type_2fa == "totp_2fa" else False,
                    }
            elif self.bridge == "facebook":
                path = "login_2fa"
                data = {
                    "email": email,
                    "code": code,
                }
            self.log.debug(
                f"Challenge with {user_id} and ({email or username}) in the {self.bridge} bridge."
            )
            response = await self.session.post(
                url=f"{self.url_base}{self.endpoints[path]}",
                headers=self.headers,
                json=data,
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return 500, {"error": str(e)}

        data = await response.json()
        if response.status not in [200, 201]:
            self.log.error(await response.text())

        return response.status, data

    async def logout(self, user_id: UserID) -> tuple(int, Dict):
        """It logs out a user.

        Parameters
        ----------
        user_id : UserID
            The user ID of the user to log out.

        Returns
        -------
            A tuple of the status code and the data.

        """

        try:
            response = await self.session.post(
                url=f"{self.url_base}{self.endpoints['logout']}",
                headers=self.headers,
                params={"user_id": user_id},
            )
        except Exception as e:
            self.log.error(e)
            return 500, {"error": str(e)}

        data = await response.json()
        if not response.status in [200, 201]:
            self.log.error(await response.text())

        return response.status, data
