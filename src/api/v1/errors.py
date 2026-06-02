from fastapi import HTTPException, status


INTERNAL_SERVER_ERROR_DETAIL = "internal server error"


def internal_server_error() -> HTTPException:
    # Security: never expose unexpected exception text to API clients.
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=INTERNAL_SERVER_ERROR_DETAIL,
    )
