import logging
from datetime import datetime
from typing import List

import pytz
from mautrix.appservice import IntentAPI
from mautrix.util.logging import TraceLogger

from ..config import Config
from ..http_client import IkonoAPIClient, client


class BusinessHour:
    log: TraceLogger = logging.getLogger("acd.business_hour")
    HOLIDAY_INFO = {}

    def __init__(self, intent: IntentAPI, config: Config) -> None:
        self.intent = intent
        self.config = config
        self.ikono_client = IkonoAPIClient(
            session=client.session, config=config, user_id=self.intent.mxid
        )

    async def is_not_business_hour(self) -> bool:
        """If the current time is not within the business hours, return True

        Returns
        -------
            A boolean value.

        """
        if self.config["utils.business_hours"]:
            time_zone = pytz.timezone(self.config["utils.timezone"])
            now = datetime.now(time_zone)
            day = now.strftime("%A").lower()

            if await self.is_holiday(now) and day != "sunday":
                day = "holiday"

            business_day_hours: List[str] = self.config[f"utils.business_hours.{day}"]
            if business_day_hours:
                for business_range in business_day_hours:
                    time_range = business_range.split("-")
                    start_hour = datetime.strptime(time_range[0], "%H:%M").time()
                    end_hour = datetime.strptime(time_range[1], "%H:%M").time()

                    if now.time() > start_hour and now.time() < end_hour:
                        return False
            self.log.debug("Message out of business hours")
            return True

        return False

    async def is_holiday(self, now: datetime) -> bool:
        """It checks if the current date is a holiday or not

        Parameters
        ----------
        now : datetime
            datetime

        Returns
        -------
            A boolean value.

        """

        if not self.HOLIDAY_INFO or self.HOLIDAY_INFO.get("today") != now.strftime("%Y-%m-%d"):
            base_url = self.config["ikono_api.base_url"]
            holidays_url = self.config["ikono_api.holidays_url"]
            url = f"{base_url}{holidays_url}?holiday_date={now.strftime('%Y-%m-%d')}"
            response_status, holiday = await self.ikono_client.get_request(url)

            self.HOLIDAY_INFO["today"] = now.strftime("%Y-%m-%d")
            self.HOLIDAY_INFO["is_holiday"] = False if response_status != 200 else True

        return self.HOLIDAY_INFO.get("is_holiday")

    async def send_business_hours_message(self, room_id) -> None:
        """This function sends a message to the room_id provided, if the message is set in the config

        Parameters
        ----------
        room_id
            The room ID of the room you want to send the message to.

        """
        if self.config["utils.business_hours.business_hours_message"]:
            business_hour_message = self.config["utils.business_hours.business_hours_message"]
            await self.intent.send_text(room_id, business_hour_message, False)
