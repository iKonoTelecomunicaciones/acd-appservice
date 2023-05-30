from __future__ import annotations

from typing import TYPE_CHECKING

from mautrix.types import RoomID, UserID

from .models import ACDEventTypes, ACDPortalEvents
from .portal_event import TransferStatusEvent

if TYPE_CHECKING:
    from ..portal import Portal, PortalState


async def send_transfer_status_event(
    portal: Portal,
    prev_portal_state: PortalState,
    destination: UserID | RoomID,
    status: str,
    reason: str,
):
    event = TransferStatusEvent(
        event_type=ACDEventTypes.PORTAL,
        event=ACDPortalEvents.TransferStatus,
        state=prev_portal_state,
        prev_state=portal.state,
        sender=portal.main_intent.mxid,
        room_id=portal.room_id,
        acd=portal.main_intent.mxid,
        customer_mxid=portal.creator,
        destination=destination,
        status=status,
        reason=reason,
    )
    event.send()
