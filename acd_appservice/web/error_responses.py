"""Este archivo almacena todas las respuestas de error que se repiten en la API"""


NOT_DATA = {
    "data": {"error": "Please provide some data"},
    "status": 400,
}

NOT_EMAIL = {
    "data": {"error": "Please provide user email"},
    "status": 400,
}

INVALID_EMAIL = {
    "data": {"error": "Not a valid email"},
    "status": 400,
}

INVALID_PHONE = {
    "data": {"error": "Not a valid phone"},
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
    "data": {"error": "Message has not found"},
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
