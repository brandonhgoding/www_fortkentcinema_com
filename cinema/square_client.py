import uuid
from square import Square
from square.environment import SquareEnvironment
from django.conf import settings


def get_square_client() -> Square:
    return Square(
        environment=SquareEnvironment.PRODUCTION,
        token=settings.SQUARE_ACCESS_TOKEN
    )


def idempotency_key(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"
