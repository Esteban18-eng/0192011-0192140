import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.adoptions import main as adoptions_api
from services.pets import main as pets_api
from services.shared.database import Base, get_db


@pytest.fixture
def services(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    pets_api.app.dependency_overrides[get_db] = override_get_db
    adoptions_api.app.dependency_overrides[get_db] = override_get_db
    pets_client = TestClient(pets_api.app)
    adoptions_client = TestClient(adoptions_api.app)

    def forward_get(url, **kwargs):
        response = pets_client.get(httpx.URL(url).path)
        return response

    def forward_request(method, url, json=None, **kwargs):
        return pets_client.request(method, httpx.URL(url).path, json=json)

    monkeypatch.setattr(adoptions_api.httpx, "get", forward_get)
    monkeypatch.setattr(adoptions_api.httpx, "request", forward_request)
    yield pets_client, adoptions_client
    pets_api.app.dependency_overrides.clear()
    adoptions_api.app.dependency_overrides.clear()
    engine.dispose()


def test_adoption_workflow_prevents_a_second_approval(services):
    pets, adoptions = services
    pet_response = pets.post(
        "/pets",
        json={
            "name": "Luna",
            "species": "Perro",
            "breed": "Criolla",
            "age": 2,
            "description": "Cariñosa y tranquila.",
        },
    )
    assert pet_response.status_code == 201
    pet_id = pet_response.json()["id"]

    first = adoptions.post(
        "/adoptions",
        json={
            "pet_id": pet_id,
            "applicant_name": "Ana Pérez",
            "email": "ana@example.com",
            "phone": "3001234567",
            "motivation": "Tengo espacio y tiempo para cuidarla.",
        },
    )
    second = adoptions.post(
        "/adoptions",
        json={
            "pet_id": pet_id,
            "applicant_name": "Luis Díaz",
            "email": "luis@example.com",
            "phone": "3007654321",
            "motivation": "Quiero ofrecerle un hogar responsable.",
        },
    )
    assert first.status_code == 201
    assert second.status_code == 201

    approved = adoptions.post(f"/adoptions/{first.json()['id']}/approve")
    conflict = adoptions.post(f"/adoptions/{second.json()['id']}/approve")

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert conflict.status_code == 409
    assert pets.get(f"/pets/{pet_id}").json()["status"] == "adopted"
    requests = {item["id"]: item for item in adoptions.get("/adoptions").json()}
    assert requests[second.json()["id"]]["status"] == "pending"

    unavailable = adoptions.post(
        "/adoptions",
        json={
            "pet_id": pet_id,
            "applicant_name": "Marta Ruiz",
            "email": "marta@example.com",
            "phone": "3003334455",
            "motivation": "Puedo brindarle cuidado y compañía.",
        },
    )
    rejected = adoptions.post(f"/adoptions/{second.json()['id']}/reject")
    assert unavailable.status_code == 409
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
