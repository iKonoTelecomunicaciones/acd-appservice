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
    TransferFailed = "TransferFailed"
    Assigned = "Assigned"
    AssignFailed = "AssignFailed"
    QueueEmpty = "QueueEmpty"
    AvailableAgents = "AvailableAgents"
