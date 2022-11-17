from __future__ import annotations

from aiohttp import ClientSession
from mautrix.types import UserID

from ..config import Config
from .base import Base


class IkonoAPI(Base):
    def __init__(self, session: ClientSession, config: Config, user_id: UserID):
        self.session = session
        self.config = config
        self.user_id = user_id
        self.log = self.log.getChild(f"ikono_api.{user_id}")
        self.api_token = None

    async def get_api_token(self):
        """It gets an access token from the API

        Returns
        -------
            The return value is a list of dictionaries.

        """

        base_url = self.config["ikono_api.base_url"]
        login_url = self.config["ikono_api.login_url"]
        data = {
            "username": self.user_id,
            "password": self.config["ikono_api.password"],
        }
        url = f"{base_url}{login_url}"
        try:
            async with self.session.post(url, data=data) as response:
                if response.status != 200:
                    self.log.error(
                        f"Failed to get api access token {self.user_id}: {await response.text()}"
                    )
                    return False
                response_json = await response.json()
        except Exception as e:
            self.log.error(f"Error getting api access token: {e}")
            return False

        self.api_token = response_json.get("access_token")
        return True

    async def get_request(self, url: str, data: dict = None):
        """It makes a GET request to the url provided.

        Parameters
        ----------
        url : str
            The URL to make the request to.
        data : dict
            The data to send to the server.

        Returns
        -------
            The status code and the response in json format.

        """

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
