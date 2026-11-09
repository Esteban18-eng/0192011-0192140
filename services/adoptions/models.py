from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func, text

from services.shared.database import Base


class Adoption(Base):
    __tablename__ = "adoptions"
    __table_args__ = (
        Index(
            "uq_adoptions_one_approved_per_pet",
            "pet_id",
            unique=True,
            postgresql_where=text("status = 'approved'"),
            sqlite_where=text("status = 'approved'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    pet_id = Column(Integer, nullable=False, index=True)
    applicant_name = Column(String(120), nullable=False)
    email = Column(String(254), nullable=False)
    phone = Column(String(40), nullable=False)
    motivation = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
