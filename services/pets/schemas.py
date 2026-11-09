from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class PetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    species: Literal["Perro", "Gato", "Otro"]
    breed: str = Field(default="Mestizo", min_length=1, max_length=100)
    age: int = Field(ge=0, le=50)
    description: str = Field(min_length=1, max_length=2000)
    photo_url: HttpUrl | None = None


class PetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    species: str
    breed: str
    age: int
    description: str
    photo_url: str | None
    status: str


class ReservationRequest(BaseModel):
    adoption_id: int = Field(gt=0)

