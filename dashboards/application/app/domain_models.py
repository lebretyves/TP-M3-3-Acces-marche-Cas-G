"""Persistent domain data. Access checks live in domain.py, never in browser state."""
from sqlalchemy import Boolean, Float, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base
from .crypto import SensitiveJSON


class DomainRecord(Base):
    __tablename__ = 'domain_records'
    __table_args__ = (UniqueConstraint('document_id', 'version', name='uq_document_version'),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    owner_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    patient_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    document_id: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default='active')
    data: Mapped[dict] = mapped_column(SensitiveJSON(), default=dict)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class DomainJob(Base):
    __tablename__ = 'domain_jobs'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    target_id: Mapped[str] = mapped_column(String(80), index=True)
    owner_id: Mapped[str] = mapped_column(String(80), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default='pending', index=True)
    payload: Mapped[dict] = mapped_column(SensitiveJSON(), default=dict)
    result: Mapped[dict] = mapped_column(SensitiveJSON(), default=dict)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)


class DomainGrant(Base):
    __tablename__ = 'domain_grants'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(80), index=True)
    patient_id: Mapped[str] = mapped_column(String(80), index=True)
    clinician_id: Mapped[str] = mapped_column(String(80), index=True)
    start: Mapped[str] = mapped_column(String(10))
    end: Mapped[str] = mapped_column(String(10))
    categories: Mapped[list] = mapped_column(JSON)
    expires: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class DomainDiagnostic(Base):
    __tablename__ = 'domain_diagnostics'
    ticket_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80), index=True)
    support_id: Mapped[str] = mapped_column(String(80), index=True)
    owner_id: Mapped[str] = mapped_column(String(80), index=True)
    expires: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class SupportScope(Base):
    __tablename__ = 'support_scopes'
    support_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
