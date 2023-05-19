from mautrix.types import SerializableEnum


class ACDEventTypes(SerializableEnum):
    PORTAL = "PORTAL"


class ACDPortalEvents(SerializableEnum):
    Create = "Create"
    UIC = "UIC"
    EnterQueue = "EnterQueue"
    Connect = "Connect"
    AgentMessage = "AgentMessage"
    CustomerMessage = "CustomerMessage"
    Resolve = "Resolve"
    Transfer = "Transfer"
    AssignedAgent = "AssignedAgent"
