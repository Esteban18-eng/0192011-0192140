import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update
from sqlalchemy.orm import Session

from services.pets.models import Pet
from services.pets.schemas import PetCreate, PetRead, ReservationRequest
from services.shared.database import Base, engine, get_db


def _origins() -> list[str]:
    return [
        origin.strip()
        for origin in os.getenv("FRONTEND_ORIGINS", "http://localhost:8080").split(",")
        if origin.strip()
    ]


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Huellas de Esperanza - API de Mascotas",
    description="Registro, consulta, disponibilidad y reserva de mascotas.",
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
    return {"status": "ok", "service": "pets"}


@app.post("/pets", response_model=PetRead, status_code=201, tags=["Mascotas"])
def create_pet(payload: PetCreate, db: Session = Depends(get_db)):
    pet = Pet(**payload.model_dump(mode="json"))
    db.add(pet)
    db.commit()
    db.refresh(pet)
    return pet


@app.get("/pets", response_model=list[PetRead], tags=["Mascotas"])
def list_pets(
    available_only: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    query = db.query(Pet)
    if available_only:
        query = query.filter(Pet.status == "available")
    return query.order_by(Pet.id.desc()).all()


@app.get("/pets/{pet_id}", response_model=PetRead, tags=["Mascotas"])
def get_pet(pet_id: int, db: Session = Depends(get_db)):
    pet = db.get(Pet, pet_id)
    if pet is None:
        raise HTTPException(status_code=404, detail="Mascota no encontrada")
    return pet


@app.post("/pets/{pet_id}/reservations", tags=["Integración"])
def reserve_pet(pet_id: int, payload: ReservationRequest, db: Session = Depends(get_db)):
    result = db.execute(
        update(Pet)
        .where(
            Pet.id == pet_id,
            (Pet.status == "available")
            | (
                (Pet.status == "reserved")
                & (Pet.reservation_id == payload.adoption_id)
            ),
        )
        .values(status="reserved", reservation_id=payload.adoption_id)
    )
    db.commit()
    if result.rowcount == 0:
        if db.get(Pet, pet_id) is None:
            raise HTTPException(status_code=404, detail="Mascota no encontrada")
        raise HTTPException(
            status_code=409,
            detail="La mascota ya no está disponible para esta solicitud",
        )
    return {"pet_id": pet_id, "adoption_id": payload.adoption_id, "status": "reserved"}


@app.post("/pets/{pet_id}/complete-adoption", tags=["Integración"])
def complete_adoption(
    pet_id: int, payload: ReservationRequest, db: Session = Depends(get_db)
):
    result = db.execute(
        update(Pet)
        .where(
            Pet.id == pet_id,
            Pet.status == "reserved",
            Pet.reservation_id == payload.adoption_id,
        )
        .values(status="adopted")
    )
    db.commit()
    if result.rowcount == 0:
        pet = db.get(Pet, pet_id)
        if pet is not None and pet.status == "adopted" and pet.reservation_id == payload.adoption_id:
            return {"pet_id": pet_id, "adoption_id": payload.adoption_id, "status": "adopted"}
        raise HTTPException(
            status_code=409,
            detail="No existe una reserva activa para esta solicitud",
        )
    return {"pet_id": pet_id, "adoption_id": payload.adoption_id, "status": "adopted"}


@app.delete("/pets/{pet_id}/reservations", tags=["Integración"])
def release_reservation(
    pet_id: int, payload: ReservationRequest, db: Session = Depends(get_db)
):
    result = db.execute(
        update(Pet)
        .where(
            Pet.id == pet_id,
            Pet.status.in_(("reserved", "adopted")),
            Pet.reservation_id == payload.adoption_id,
        )
        .values(status="available", reservation_id=None)
    )
    db.commit()
    if result.rowcount == 0:
        pet = db.get(Pet, pet_id)
        if pet is None:
            raise HTTPException(status_code=404, detail="Mascota no encontrada")
        if pet.status == "available":
            return {"pet_id": pet_id, "status": "available"}
        raise HTTPException(status_code=409, detail="La reserva pertenece a otra solicitud")
    return {"pet_id": pet_id, "status": "available"}

