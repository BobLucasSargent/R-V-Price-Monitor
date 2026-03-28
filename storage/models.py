"""R&V IPC — Database models."""
from datetime import date, datetime
from sqlalchemy import (
    Column, String, Float, Date, DateTime, Integer, Boolean, Text,
    UniqueConstraint, Index, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


class PrecioRaw(Base):
    """Individual price observation from a collector."""
    __tablename__ = "precios_raw"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False)
    collector_id = Column(String(50), nullable=False)
    producto = Column(String(300), nullable=False)
    precio = Column(Float, nullable=False)
    unidad = Column(String(50), default="unidad")
    categoria_coicop = Column(String(20))  # e.g. "01.1.1"
    division_coicop = Column(String(5))     # e.g. "01"
    fuente = Column(String(100))
    url = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_precio_fecha_collector", "fecha", "collector_id"),
        Index("ix_precio_division", "division_coicop", "fecha"),
    )


class PrecioPromedio(Base):
    """Geometric mean price per variety per period."""
    __tablename__ = "precios_promedio"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False)
    periodo_tipo = Column(String(10), nullable=False)  # "diario", "semanal", "mensual"
    variedad_coicop = Column(String(20), nullable=False)
    division_coicop = Column(String(5), nullable=False)
    precio_promedio = Column(Float, nullable=False)
    n_observaciones = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("fecha", "periodo_tipo", "variedad_coicop",
                         name="uq_precio_promedio"),
    )


class IndiceElemental(Base):
    """Elementary index per variety (relative to base)."""
    __tablename__ = "indices_elementales"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False)
    periodo_tipo = Column(String(10), nullable=False)
    variedad_coicop = Column(String(20), nullable=False)
    division_coicop = Column(String(5), nullable=False)
    indice = Column(Float, nullable=False)
    variacion = Column(Float)  # vs previous period (%)
    created_at = Column(DateTime, default=datetime.utcnow)


class IndiceAgregado(Base):
    """Aggregated index at division / category / nivel general."""
    __tablename__ = "indices_agregados"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fecha = Column(Date, nullable=False)
    periodo_tipo = Column(String(10), nullable=False)  # "semanal", "mensual"
    nivel = Column(String(50), nullable=False)  # "nivel_general", "01", "nucleo", etc.
    indice = Column(Float, nullable=False)
    variacion_periodo = Column(Float)   # vs previous period (%)
    variacion_mensual = Column(Float)   # vs previous month if weekly
    es_oficial = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("fecha", "periodo_tipo", "nivel", name="uq_indice_agregado"),
        Index("ix_indice_fecha_nivel", "fecha", "nivel"),
    )


class CollectorStatus(Base):
    """Track collector health and runs."""
    __tablename__ = "collector_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    collector_id = Column(String(50), nullable=False)
    fecha_corrida = Column(DateTime, nullable=False)
    exito = Column(Boolean, nullable=False)
    n_precios = Column(Integer, default=0)
    error_msg = Column(Text)
    duracion_seg = Column(Float)


class ComparacionINDEC(Base):
    """Month-end comparison: R&V proxy vs INDEC official."""
    __tablename__ = "comparacion_indec"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mes = Column(String(7), nullable=False, unique=True)  # "2026-03"
    rv_nivel_general = Column(Float)
    rv_var_mensual = Column(Float)
    indec_nivel_general = Column(Float)
    indec_var_mensual = Column(Float)
    diferencia_pp = Column(Float)  # puntos porcentuales de diferencia
    created_at = Column(DateTime, default=datetime.utcnow)


def create_tables(database_url: str):
    """Create all tables (for dev/testing)."""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine
