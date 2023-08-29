from mautrix.types import SerializableEnum


class ACDEventTypes(SerializableEnum):
    CONVERSATION = "CONVERSATION"
    MEMBER = "MEMBER"
    MEMBERSHIP = "MEMBERSHIP"
    ROOM = "ROOM"


class ACDConversationEvents(SerializableEnum):
    Create = "Create"
    UIC = "UIC"
    BIC = "BIC"
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


class ACDMemberEvents(SerializableEnum):
    MemberLogin = "MemberLogin"
    MemberLogout = "MemberLogout"
    MemberPause = "MemberPause"


class ACDMembershipEvents(SerializableEnum):
    MemberAdd = "MemberAdd"
    MemberRemove = "MemberRemove"


class ACDRoomEvents(SerializableEnum):
    NameChange = "NameChange"
