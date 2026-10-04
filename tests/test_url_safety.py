import pytest
from pydantic import ValidationError

from app.schemas import CompanyAnalyzeRequest
from app.services.url_safety import UnsafeURLError, validate_public_url


def test_request_rejects_credentials() -> None:
    with pytest.raises(ValidationError):
        CompanyAnalyzeRequest(name="Acme", website="https://user:pass@example.com")


@pytest.mark.asyncio
async def test_rejects_literal_private_ip() -> None:
    with pytest.raises(UnsafeURLError):
        await validate_public_url("http://127.0.0.1/admin")


@pytest.mark.asyncio
async def test_rejects_localhost() -> None:
    with pytest.raises(UnsafeURLError):
        await validate_public_url("http://localhost")
