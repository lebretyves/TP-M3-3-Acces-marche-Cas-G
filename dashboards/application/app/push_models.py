"""Push secrets are encrypted; delivery metadata never contains health content."""
from sqlalchemy import Boolean, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base
from .crypto import SensitiveJSON


class PushSubscription(Base):
    __tablename__='push_subscriptions'
    id: Mapped[str]=mapped_column(String(80),primary_key=True)
    owner_id: Mapped[str]=mapped_column(String(80),index=True)
    endpoint_hash: Mapped[str]=mapped_column(String(64),unique=True)
    data: Mapped[dict]=mapped_column(SensitiveJSON())
    label: Mapped[str]=mapped_column(String(80))
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[float]=mapped_column(Float)
    updated_at: Mapped[float]=mapped_column(Float)


class PushDelivery(Base):
    __tablename__='push_deliveries'
    __table_args__=(UniqueConstraint('notification_id','subscription_id',name='uq_push_delivery'),)
    id: Mapped[str]=mapped_column(String(80),primary_key=True)
    owner_id: Mapped[str]=mapped_column(String(80),index=True)
    notification_id: Mapped[str]=mapped_column(String(80),index=True)
    subscription_id: Mapped[str]=mapped_column(String(80),index=True)
    kind: Mapped[str]=mapped_column(String(20))
    status: Mapped[str]=mapped_column(String(40),default='pending',index=True)
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    next_attempt: Mapped[float]=mapped_column(Float)
    provider_status: Mapped[int | None]=mapped_column(Integer,nullable=True)
    created_at: Mapped[float]=mapped_column(Float)
    updated_at: Mapped[float]=mapped_column(Float)


class PushSchedule(Base):
    __tablename__='push_schedules'
    owner_id: Mapped[str]=mapped_column(String(80),primary_key=True)
    next_pause: Mapped[float]=mapped_column(Float)
