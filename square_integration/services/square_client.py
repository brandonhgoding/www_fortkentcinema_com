import uuid
from square import Square
from square.environment import SquareEnvironment
from django.conf import settings


def get_square_client() -> Square:
    square_environment = (
        SquareEnvironment.PRODUCTION
        if settings.SQUARE_ENVIRONMENT == "production"
        else SquareEnvironment.SANDBOX
    )
    return Square(environment=square_environment, token=settings.SQUARE_ACCESS_TOKEN)


def idempotency_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"
