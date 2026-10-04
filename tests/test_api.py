import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_analyze_and_retrieve_company(client: AsyncClient) -> None:
    response = await client.post(
        "/companies/analyze",
        json={"name": "Acme", "website": "https://acme.example"},
    )
    assert response.status_code == 201, response.text
    company = response.json()
    assert company["id"] == 1
    assert company["score"]["total"] == 100
    assert company["score"]["industry_match"] == 25
    assert len(company["signals"]) >= 4
    assert all(signal["source_url"] for signal in company["signals"])

    listed = await client.get("/companies")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "Acme"

    detail = await client.get("/companies/1")
    assert detail.status_code == 200
    assert detail.json()["score"]["total"] == 100

    signals = await client.get("/companies/1/signals")
    assert signals.status_code == 200
    assert any(item["name"] == "Demo or sales-led motion" for item in signals.json())


@pytest.mark.asyncio
async def test_batch_reports_row_level_errors(client: AsyncClient) -> None:
    csv_body = (
        "name,website\n"
        "Acme,https://acme.example\n"
        "Missing URL,not-a-url\n"
        "Down,https://unreachable.example\n"
    )
    response = await client.post(
        "/companies/batch",
        files={"file": ("companies.csv", csv_body, "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["processed"] == 3
    assert body["succeeded"] == 1
    assert body["failed"] == 2
    assert body["results"][1]["error"]


@pytest.mark.asyncio
async def test_health_and_not_found(client: AsyncClient) -> None:
    health = await client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok", "database": "connected", "llm_configured": False}
    assert (await client.get("/companies/999")).status_code == 404
    assert (await client.get("/companies/999/signals")).status_code == 404


@pytest.mark.asyncio
async def test_rejects_localhost_at_input_boundary(client: AsyncClient) -> None:
    response = await client.post(
        "/companies/analyze", json={"name": "Internal", "website": "http://localhost:8000"}
    )
    assert response.status_code == 422
