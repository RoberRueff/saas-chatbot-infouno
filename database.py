from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
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


def obtener_o_crear_conversacion(db: Session, telefono: str) -> Conversacion:
    conversacion = (
        db.query(Conversacion)
        .filter(
            Conversacion.telefono_cliente == telefono,
            Conversacion.estado_humano == False,
        )
        .order_by(Conversacion.fecha_creacion.desc())
        .first()
    )
    if conversacion is None:
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
