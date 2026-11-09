from sqlalchemy import Column, Integer, String, Text

from services.shared.database import Base


class Pet(Base):
    __tablename__ = "pets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    species = Column(String(40), nullable=False)
    breed = Column(String(100), nullable=False, default="Mestizo")
    age = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    photo_url = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="available", index=True)
    reservation_id = Column(Integer, nullable=True, unique=True)

