"""Este archivo almacena todas las respuestas de error que se repiten en la API"""

NOT_DATA = {
    "data": {"error": "Please provide some data"},
    "status": 400,
}

NOT_EMAIL = {
    "data": {"error": "Please provide user email"},
    "status": 400,
}

NOT_USERNAME = {
    "data": {"error": "Please provide username"},
    "status": 400,
}

INVALID_EMAIL = {
    "data": {"error": "Not a valid email"},
    "status": 406,
}

INVALID_PHONE = {
    "data": {"error": "Not a valid phone"},
    "status": 400,
}

INVALID_USER_ID = {
    "data": {"error": "Not a valid user ID"},
    "status": 400,
}

MESSAGE_TYPE_NOT_SUPPORTED = {
    "data": {"error": "This type of message is not supported"},
    "status": 400,
}

USER_DOESNOT_EXIST = {
    "data": {"error": "User doesn't exist"},
    "status": 404,
}

QUEUE_DOESNOT_EXIST = {
    "data": {"error": "Queue doesn't exist"},
    "status": 404,
}

QUEUE_MEMBERSHIP_DOESNOT_EXIST = {
    "data": {"error": "Queue membership doesn't exist"},
    "status": 404,
}


TIMEOUT_ERROR = {
    "data": {
        "error": "The request took too long, please try again. If the error persists, contact technical support"
    },
    "status": 408,
}

REQUIRED_VARIABLES = {
    "data": {"error": "Please provide required variables"},
    "status": 422,
}

MESSAGE_NOT_SENT = {
    "data": {"error": "Message has not been sent"},
    "status": 422,
}

MESSAGE_NOT_FOUND = {
    "data": {"error": "Message not found"},
    "status": 404,
}

USER_ALREADY_EXISTS = {
    "data": {"error": "User already exists"},
    "status": 422,
}

REQUEST_ALREADY_EXISTS = {
    "data": {"error": "You already have a pending request"},
    "status": 429,
}

SERVER_ERROR = {
    "data": {"error": "Server error"},
    "status": 500,
}

BRIDGE_INVALID = {
    "data": {"error": "Bridge invalid"},
    "status": 422,
}

AGENT_DOESNOT_HAVE_QUEUES = {
    "data": {"error": "Agent does not belong to any existing queue"},
    "status": 406,
}

INVALID_ACTION = {
    "data": {"error": "The provided action is invalid"},
    "status": 422,
}

FORBIDDEN_OPERATION = {
    "data": {"error": "Forbidden operation"},
    "status": 403,
}

INVALID_USER_ROLE = {"data": {"error": "User role does not exist"}, "status": 404}

PUPPET_DOESNOT_EXIST = {"data": {"error": "Puppet with given mxid was not found."}, "status": 404}

INVALID_DESTINATION = {"data": {"error": "Given destination is invalid"}, "status": 409}

NO_PUPPET_IN_PORTAL = {
    "data": {"error": "Unable to find a puppet inside the portal"},
    "status": 409,
}

UNABLE_TO_FIND_PUPPET = {"data": {"error": "Unable to find puppet"}, "status": 409}

PORTAL_DOESNOT_EXIST = {
    "data": {"error": "Portal with given room id was not found."},
    "status": 404,
}

ROOM_NAME_NOT_UPDATED = {
    "data": {"error": "The name of room was not updated"},
    "status": 409,
}
