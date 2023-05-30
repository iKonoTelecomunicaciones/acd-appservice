from mautrix.types import SerializableEnum


class ACDEventTypes(SerializableEnum):
    PORTAL = "PORTAL"


class ACDPortalEvents(SerializableEnum):
    Create = "Create"
    UIC = "UIC"
    EnterQueue = "EnterQueue"
    Connect = "Connect"
    PortalMessage = "PortalMessage"
    Resolve = "Resolve"
    Transfer = "Transfer"
    Assigned = "Assigned"
    MenuStart = "MenuStart"
    TransferStatus = "TransferStatus"
    QueueEmpty = "QueueEmpty"
    AvailableAgents = "AvailableAgents"
