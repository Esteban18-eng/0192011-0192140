from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdoptionCreate(BaseModel):
    pet_id: int = Field(gt=0)
    applicant_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=40)
    motivation: str = Field(min_length=10, max_length=2000)


class AdoptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pet_id: int
    applicant_name: str
    email: EmailStr
    phone: str
    motivation: str
    status: str
    created_at: datetime

