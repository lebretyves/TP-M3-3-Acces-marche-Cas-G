"""Private transport registry, independent of account identifiers and raw payloads."""
from sqlalchemy import Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base


class DeviceIdentity(Base):
    __tablename__ = 'transport_device_identity'
    cert_cn: Mapped[str] = mapped_column(String(80), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80), unique=True)
    cert_serial: Mapped[str] = mapped_column(String(80))
    expires_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    revoked_at: Mapped[float | None] = mapped_column(Float, nullable=True)


class IngestCursor(Base):
    __tablename__ = 'transport_ingest_cursor'
    __table_args__ = (UniqueConstraint('device_id', 'session_id'),)
    id: Mapped[str] = mapped_column(String(180), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80))
    session_id: Mapped[str] = mapped_column(String(40))
    last_sequence: Mapped[int] = mapped_column(Integer)
    last_measured_at: Mapped[float] = mapped_column(Float)


class IngestDeviceCursor(Base):
    """Global window watermark; changing MQTT/firmware session never resets it."""
    __tablename__ = 'transport_device_cursor'
    device_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_window_end: Mapped[float] = mapped_column(Float)


class IngestReceipt(Base):
    __tablename__ = 'transport_ingest_receipt'
    __table_args__ = (UniqueConstraint('device_id', 'session_id', 'sequence'),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80))
    session_id: Mapped[str] = mapped_column(String(40))
    sequence: Mapped[int] = mapped_column(Integer)
    measured_at: Mapped[float] = mapped_column(Float)
    received_at: Mapped[float] = mapped_column(Float)
    payload_digest: Mapped[str] = mapped_column(String(64))
    report_id: Mapped[str] = mapped_column(String(60))

