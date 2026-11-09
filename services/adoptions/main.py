import os
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.adoptions.models import Adoption
from services.adoptions.schemas import AdoptionCreate, AdoptionRead
from services.shared.database import Base, engine, get_db


PETS_API_URL = os.getenv("PETS_API_URL", "http://localhost:8001").rstrip("/")
PET_REQUEST_TIMEOUT = 5.0


def _origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:8080").split(",")
        if origin.strip()
    ]


def _pet_service_request(method: str, path: str, adoption_id: int | None = None):
    payload = {"adoption_id": adoption_id} if adoption_id is not None else None
    try:
        response = httpx.request(
            method,
            f"{PETS_API_URL}{path}",
            json=payload,
            timeout=PET_REQUEST_TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="El servicio de mascotas no está disponible",
        ) from exc
    return response


def _ensure_pet_available(pet_id: int):
    try:
        response = httpx.get(
            f"{PETS_API_URL}/pets/{pet_id}",
            timeout=PET_REQUEST_TIMEOUT,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail="El servicio de mascotas no está disponible",
        ) from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    if response.is_error:
        raise HTTPException(status_code=502, detail="Error consultando el servicio de mascotas")
    if response.json().get("status") != "available":
        raise HTTPException(status_code=409, detail="La mascota no está disponible")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Huellas de Esperanza - API de Adopciones",
    description="Solicitudes de adopción y coordinación con el servicio de mascotas.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "adoptions"}


@app.post("/adoptions", response_model=AdoptionRead, status_code=201, tags=["Adopciones"])
def create_adoption(payload: AdoptionCreate, db: Session = Depends(get_db)):
    _ensure_pet_available(payload.pet_id)
    adoption = Adoption(**payload.model_dump())
    db.add(adoption)
    db.commit()
    db.refresh(adoption)
    return adoption


@app.get("/adoptions", response_model=list[AdoptionRead], tags=["Adopciones"])
def list_adoptions(db: Session = Depends(get_db)):
    return db.query(Adoption).order_by(Adoption.created_at.desc(), Adoption.id.desc()).all()


@app.get("/adoptions/{adoption_id}", response_model=AdoptionRead, tags=["Adopciones"])
def get_adoption(adoption_id: int, db: Session = Depends(get_db)):
    adoption = db.get(Adoption, adoption_id)
    if adoption is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return adoption


@app.post(
    "/adoptions/{adoption_id}/approve",
    response_model=AdoptionRead,
    tags=["Adopciones"],
)
def approve_adoption(adoption_id: int, db: Session = Depends(get_db)):
    adoption = db.get(Adoption, adoption_id)
    if adoption is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if adoption.status != "pending":
        raise HTTPException(status_code=409, detail="Solo se pueden aprobar solicitudes pendientes")

    reserve = _pet_service_request(
        "POST", f"/pets/{adoption.pet_id}/reservations", adoption.id
    )
    if reserve.status_code == 404:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    if reserve.status_code == 409:
        raise HTTPException(status_code=409, detail="La mascota ya fue reservada o adoptada")
    if reserve.is_error:
        raise HTTPException(status_code=502, detail="Error reservando la mascota")

    try:
        approval = db.execute(
            update(Adoption)
            .where(Adoption.id == adoption.id, Adoption.status == "pending")
            .values(status="approved")
        )
        if approval.rowcount == 0:
            db.rollback()
            db.refresh(adoption)
            if adoption.status == "approved":
                return adoption
            release = _pet_service_request(
                "DELETE", f"/pets/{adoption.pet_id}/reservations", adoption.id
            )
            if release.is_error:
                raise HTTPException(
                    status_code=502,
                    detail="La solicitud cambió y no fue posible liberar la reserva",
                )
            raise HTTPException(status_code=409, detail="La solicitud ya fue gestionada")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        release = _pet_service_request(
            "DELETE", f"/pets/{adoption.pet_id}/reservations", adoption.id
        )
        if release.is_error:
            raise HTTPException(
                status_code=502,
                detail="Conflicto al aprobar y no fue posible liberar la reserva",
            ) from exc
        raise HTTPException(
            status_code=409,
            detail="Ya existe una adopción aprobada para esta mascota",
        ) from exc
    db.refresh(adoption)

    complete = _pet_service_request(
        "POST", f"/pets/{adoption.pet_id}/complete-adoption", adoption.id
    )
    if complete.is_error:
        db.execute(
            update(Adoption)
            .where(Adoption.id == adoption.id, Adoption.status == "approved")
            .values(status="pending")
        )
        db.commit()
        release = _pet_service_request(
            "DELETE", f"/pets/{adoption.pet_id}/reservations", adoption.id
        )
        if release.is_error:
            raise HTTPException(
                status_code=502,
                detail="Falló la confirmación y la compensación de la reserva",
            )
        raise HTTPException(status_code=502, detail="No fue posible confirmar la adopción")
    return adoption


@app.post(
    "/adoptions/{adoption_id}/reject",
    response_model=AdoptionRead,
    tags=["Adopciones"],
)
def reject_adoption(adoption_id: int, db: Session = Depends(get_db)):
    adoption = db.get(Adoption, adoption_id)
    if adoption is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    if adoption.status != "pending":
        raise HTTPException(status_code=409, detail="Solo se pueden rechazar solicitudes pendientes")
    result = db.execute(
        update(Adoption)
        .where(Adoption.id == adoption.id, Adoption.status == "pending")
        .values(status="rejected")
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="La solicitud ya fue gestionada")
    db.commit()
    db.refresh(adoption)
    return adoption
