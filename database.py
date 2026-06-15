from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

DATABASE_URL = "sqlite:///./chatbot.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class Conversacion(Base):
    __tablename__ = "conversaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telefono_cliente: Mapped[str] = mapped_column(String(20), index=True)
    estado_humano: Mapped[bool] = mapped_column(Boolean, default=False)
    derivada: Mapped[bool] = mapped_column(Boolean, default=False)
    derivada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    mensajes: Mapped[list["HistorialMensaje"]] = relationship(
        "HistorialMensaje", back_populates="conversacion", order_by="HistorialMensaje.id"
    )


class HistorialMensaje(Base):
    __tablename__ = "historial_mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversacion_id: Mapped[int] = mapped_column(ForeignKey("conversaciones.id"), index=True)
    rol: Mapped[str] = mapped_column(String(10))  # "user" | "assistant"
    contenido: Mapped[str] = mapped_column(Text)
    nota_interna_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    conversacion: Mapped["Conversacion"] = relationship("Conversacion", back_populates="mensajes")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    with Session(engine) as session:
        yield session


# Inactividad tras la cual el próximo mensaje arranca una conversación NUEVA.
# Coincide con la ventana de sesión de WhatsApp/Twilio. Así un cliente que
# vuelve (incluso ya derivado) abre un caso nuevo y puede volver a derivarse.
VENTANA_CONVERSACION_HORAS = 24


def _as_utc(dt: datetime) -> datetime:
    """SQLite devuelve datetimes naive; los tratamos como UTC para poder comparar."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _ultima_actividad(db: Session, conversacion: Conversacion) -> datetime:
    """Fecha (UTC, tz-aware) del último mensaje; fecha_creacion si no hay mensajes."""
    fila = (
        db.query(HistorialMensaje.fecha)
        .filter(HistorialMensaje.conversacion_id == conversacion.id)
        .order_by(HistorialMensaje.id.desc())
        .first()
    )
    return _as_utc(fila[0] if fila else conversacion.fecha_creacion)


def obtener_o_crear_conversacion(
    db: Session, telefono: str, ahora: datetime | None = None
) -> Conversacion:
    """Devuelve la conversación activa y RECIENTE del teléfono, o crea una nueva.

    "Reciente" = con última actividad dentro de VENTANA_CONVERSACION_HORAS. Si la
    última conversación expiró (o no hay), se crea una nueva (con derivada=False).
    `ahora` es inyectable para tests.
    """
    instante = _as_utc(ahora or datetime.now(timezone.utc))
    conversacion = (
        db.query(Conversacion)
        .filter(
            Conversacion.telefono_cliente == telefono,
            Conversacion.estado_humano == False,  # noqa: E712
        )
        .order_by(Conversacion.fecha_creacion.desc())
        .first()
    )
    if conversacion is not None:
        dentro_de_ventana = (
            instante - _ultima_actividad(db, conversacion)
            < timedelta(hours=VENTANA_CONVERSACION_HORAS)
        )
        if dentro_de_ventana:
            return conversacion

    conversacion = Conversacion(telefono_cliente=telefono)
    db.add(conversacion)
    db.commit()
    db.refresh(conversacion)
    return conversacion


def guardar_mensaje(
    db: Session,
    conversacion_id: int,
    rol: str,
    contenido: str,
    nota_interna_json: str | None = None,
) -> HistorialMensaje:
    mensaje = HistorialMensaje(
        conversacion_id=conversacion_id,
        rol=rol,
        contenido=contenido,
        nota_interna_json=nota_interna_json,
    )
    db.add(mensaje)
    db.commit()
    db.refresh(mensaje)
    return mensaje


def reclamar_derivacion(db: Session, conversacion_id: int) -> bool:
    """Marca la conversación como derivada de forma ATÓMICA.

    Devuelve True solo si ESTE llamado fue el que la marcó (gana la carrera);
    False si ya estaba derivada. El `UPDATE ... WHERE derivada = False` evita que
    dos requests concurrentes del mismo cliente disparen el email dos veces.
    """
    resultado = db.execute(
        update(Conversacion)
        .where(Conversacion.id == conversacion_id, Conversacion.derivada == False)  # noqa: E712
        .values(derivada=True, derivada_en=datetime.now(timezone.utc))
    )
    db.commit()
    return resultado.rowcount == 1


def liberar_derivacion(db: Session, conversacion_id: int) -> None:
    """Revierte la marca de derivación (para reintentar si el envío de email falló)."""
    db.execute(
        update(Conversacion)
        .where(Conversacion.id == conversacion_id)
        .values(derivada=False, derivada_en=None)
    )
    db.commit()
