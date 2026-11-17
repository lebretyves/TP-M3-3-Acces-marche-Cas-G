from sqlalchemy import Boolean, Float, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from .crypto import SensitiveJSON


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = 'accounts'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
    org_id: Mapped[str] = mapped_column(String(60))
    patient_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    otp_secret: Mapped[str] = mapped_column(String(100))
    otp_last_counter: Mapped[int] = mapped_column(Integer, default=-1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WebSession(Base):
    __tablename__ = 'web_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    csrf: Mapped[str] = mapped_column(String(80))
    expires: Mapped[float] = mapped_column(Float)
    last_seen: Mapped[float] = mapped_column(Float)
    authenticated_at: Mapped[float] = mapped_column(Float, default=0)
    oidc_sid: Mapped[str | None] = mapped_column(String(200), nullable=True)


class CareLink(Base):
    __tablename__ = 'care_links'
    __table_args__ = (UniqueConstraint('patient_id', 'clinician_id'),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(60))
    clinician_id: Mapped[str] = mapped_column(String(60))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(100))
    recorded_at: Mapped[str] = mapped_column(String(40))
    quality: Mapped[str] = mapped_column(String(20))
    metrics: Mapped[dict] = mapped_column(SensitiveJSON())
    synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Share(Base):
    __tablename__ = 'shares'
    __table_args__ = (UniqueConstraint('report_id', 'clinician_id'),)
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    report_id: Mapped[str] = mapped_column(String(60))
    clinician_id: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[str | None] = mapped_column(String(40), nullable=True)


class Alert(Base):
    __tablename__ = 'alerts'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(200))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(60))
    org_id: Mapped[str] = mapped_column(String(60))
    device_id: Mapped[str] = mapped_column(String(60))
    category: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default='ouvert')


class Prevention(Base):
    __tablename__ = 'prevention'
    id: Mapped[str] = mapped_column(String(60), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default='à organiser')


class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[str] = mapped_column(String(40))
    event: Mapped[str] = mapped_column(String(50))
    actor_id: Mapped[str] = mapped_column(String(60))
    result: Mapped[str] = mapped_column(String(20))


class LoginLimit(Base):
    __tablename__ = 'login_limits'
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    start: Mapped[float] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer, default=0)


class OIDCIdentity(Base):
    __tablename__ = 'oidc_identities'
    subject: Mapped[str] = mapped_column(String(200), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(60), unique=True)


class OIDCState(Base):
    __tablename__ = 'oidc_states'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_hash: Mapped[str] = mapped_column(String(64))
    nonce: Mapped[str] = mapped_column(String(100))
    verifier: Mapped[str] = mapped_column(String(100))
    expires: Mapped[float] = mapped_column(Float)


class LogoutReplay(Base):
    __tablename__ = 'logout_replays'
    jti: Mapped[str] = mapped_column(String(200), primary_key=True)
    expires: Mapped[float] = mapped_column(Float)


class LoginDevice(Base):
    __tablename__ = 'login_devices'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(60), index=True)
    last_seen: Mapped[float] = mapped_column(Float)
