"""
R&V IPC — Repository: data access layer for price storage and index series.

Handles:
- Saving raw price observations to PostgreSQL
- Computing monthly averages by division (geometric mean)
- Loading previous month's averages for variation calculation
- Closing months (saving final monthly index)
- Building the full time series (INDEC + R&V)
"""
from datetime import date, datetime
from collections import defaultdict
from sqlalchemy import create_engine, text, func, and_, distinct
from sqlalchemy.orm import sessionmaker, Session
import numpy as np
import structlog

from storage.models import (
    Base, PrecioRaw, PrecioPromedio, IndiceAgregado,
    CollectorStatus, ComparacionINDEC,
)
from config.settings import get_settings
from config.ipc_oficial import (
    IPC_DIVISIONES_FEB2026, EMPALME_NIVEL_GENERAL, EMPALME_FECHA,
)

log = structlog.get_logger()


def get_engine():
    s = get_settings()
    return create_engine(s.DATABASE_URL_SYNC, pool_pre_ping=True)


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def ensure_tables():
    """Create tables if they don't exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    log.info("db.tables_ensured")


# ─── Save raw prices ─────────────────────────────────────────────────────────

def save_raw_prices(observations: list, collector_id: str, fecha: date) -> int:
    """
    Save raw price observations from a collector run.
    Returns number of rows saved.
    """
    if not observations:
        return 0

    session = get_session()
    try:
        rows = []
        for obs in observations:
            rows.append(PrecioRaw(
                fecha=fecha,
                collector_id=collector_id,
                producto=obs.producto[:300],
                precio=obs.precio,
                unidad=obs.unidad,
                categoria_coicop=obs.categoria_coicop,
                division_coicop=obs.division_coicop,
                fuente=obs.fuente,
                url=(obs.url or "")[:500],
            ))

        session.bulk_save_objects(rows)
        session.commit()
        log.info("db.prices_saved", collector=collector_id, n=len(rows), fecha=str(fecha))
        return len(rows)

    except Exception as e:
        session.rollback()
        log.error("db.save_error", error=str(e))
        return 0
    finally:
        session.close()


def save_collector_status(collector_id: str, exito: bool, n_precios: int,
                          duracion_seg: float, error_msg: str = None):
    """Log collector run status."""
    session = get_session()
    try:
        session.add(CollectorStatus(
            collector_id=collector_id,
            fecha_corrida=datetime.utcnow(),
            exito=exito,
            n_precios=n_precios,
            duracion_seg=duracion_seg,
            error_msg=error_msg,
        ))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


# ─── Monthly averages ────────────────────────────────────────────────────────

def get_monthly_avg_by_division(mes: str) -> dict[str, float]:
    """
    Compute geometric mean of prices per division for a given month.

    Args:
        mes: "YYYY-MM" format (e.g. "2026-03")

    Returns:
        {"01": 2345.67, "02": 1234.56, ...}
    """
    session = get_session()
    try:
        # Parse month boundaries
        year, month = int(mes[:4]), int(mes[5:7])
        fecha_inicio = date(year, month, 1)
        if month == 12:
            fecha_fin = date(year + 1, 1, 1)
        else:
            fecha_fin = date(year, month + 1, 1)

        # Get all prices for this month grouped by division
        rows = session.query(
            PrecioRaw.division_coicop,
            PrecioRaw.precio,
        ).filter(
            PrecioRaw.fecha >= fecha_inicio,
            PrecioRaw.fecha < fecha_fin,
            PrecioRaw.precio > 0,
            PrecioRaw.division_coicop.isnot(None),
            PrecioRaw.division_coicop != "",
        ).all()

        if not rows:
            return {}

        # Group by division
        by_division = defaultdict(list)
        for div, precio in rows:
            by_division[div].append(precio)

        # Geometric mean per division
        result = {}
        for div, precios in by_division.items():
            if precios:
                log_mean = np.mean(np.log(precios))
                result[div] = float(np.exp(log_mean))

        log.info("db.monthly_avg", mes=mes, divisions=list(result.keys()),
                 total_prices=len(rows))
        return result

    except Exception as e:
        log.error("db.monthly_avg_error", mes=mes, error=str(e))
        return {}
    finally:
        session.close()


def get_price_count_by_month(mes: str) -> int:
    """Count total raw prices stored for a month."""
    session = get_session()
    try:
        year, month = int(mes[:4]), int(mes[5:7])
        fecha_inicio = date(year, month, 1)
        if month == 12:
            fecha_fin = date(year + 1, 1, 1)
        else:
            fecha_fin = date(year, month + 1, 1)

        count = session.query(func.count(PrecioRaw.id)).filter(
            PrecioRaw.fecha >= fecha_inicio,
            PrecioRaw.fecha < fecha_fin,
        ).scalar()
        return count or 0
    except Exception:
        return 0
    finally:
        session.close()


def get_collection_days_in_month(mes: str) -> int:
    """Count distinct days with price data in a month."""
    session = get_session()
    try:
        year, month = int(mes[:4]), int(mes[5:7])
        fecha_inicio = date(year, month, 1)
        if month == 12:
            fecha_fin = date(year + 1, 1, 1)
        else:
            fecha_fin = date(year, month + 1, 1)

        count = session.query(func.count(distinct(PrecioRaw.fecha))).filter(
            PrecioRaw.fecha >= fecha_inicio,
            PrecioRaw.fecha < fecha_fin,
        ).scalar()
        return count or 0
    except Exception:
        return 0
    finally:
        session.close()


# ─── Index persistence ───────────────────────────────────────────────────────

def save_monthly_index(mes: str, nivel: str, indice: float,
                       variacion: float, es_oficial: bool = False):
    """Save a monthly index value (division or nivel_general)."""
    session = get_session()
    try:
        year, month = int(mes[:4]), int(mes[5:7])
        fecha = date(year, month, 1)

        # Upsert: delete existing then insert
        session.query(IndiceAgregado).filter(
            IndiceAgregado.fecha == fecha,
            IndiceAgregado.periodo_tipo == "mensual",
            IndiceAgregado.nivel == nivel,
        ).delete()

        session.add(IndiceAgregado(
            fecha=fecha,
            periodo_tipo="mensual",
            nivel=nivel,
            indice=round(indice, 2),
            variacion_periodo=round(variacion, 2) if variacion is not None else None,
            es_oficial=es_oficial,
        ))
        session.commit()
        log.info("db.index_saved", mes=mes, nivel=nivel, indice=round(indice, 2))

    except Exception as e:
        session.rollback()
        log.error("db.index_save_error", error=str(e))
    finally:
        session.close()


def get_latest_monthly_indices() -> dict[str, dict]:
    """
    Get the most recent monthly index for each nivel (division + nivel_general).
    Returns: {"01": {"indice": 12345, "fecha": "2026-03", "variacion": 3.2}, ...}
    """
    session = get_session()
    try:
        # Subquery: max fecha per nivel
        from sqlalchemy import desc
        results = session.query(IndiceAgregado).filter(
            IndiceAgregado.periodo_tipo == "mensual",
        ).order_by(desc(IndiceAgregado.fecha)).all()

        # Group by nivel, take most recent
        latest = {}
        for row in results:
            if row.nivel not in latest:
                latest[row.nivel] = {
                    "indice": row.indice,
                    "fecha": row.fecha.strftime("%Y-%m"),
                    "variacion": row.variacion_periodo,
                    "es_oficial": row.es_oficial,
                }
        return latest

    except Exception:
        return {}
    finally:
        session.close()


def get_index_series(nivel: str = "nivel_general") -> list[dict]:
    """
    Get full time series of monthly indices for a given nivel.
    Returns list sorted by fecha ascending.
    """
    session = get_session()
    try:
        rows = session.query(IndiceAgregado).filter(
            IndiceAgregado.periodo_tipo == "mensual",
            IndiceAgregado.nivel == nivel,
        ).order_by(IndiceAgregado.fecha).all()

        return [
            {
                "fecha": row.fecha.strftime("%Y-%m"),
                "indice": row.indice,
                "variacion": row.variacion_periodo,
                "es_oficial": row.es_oficial,
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        session.close()


# ─── Month closing logic ─────────────────────────────────────────────────────

def get_previous_month_indices() -> dict[str, float]:
    """
    Get the base indices for variation calculation.
    Checks DB for last closed month; falls back to INDEC empalme.

    Returns: {"01": 11624.98, "02": 7659.91, ..., "nivel_general": 10714.63}
    """
    latest = get_latest_monthly_indices()

    if latest and "nivel_general" in latest:
        # We have previous R&V data
        result = {}
        for nivel, data in latest.items():
            result[nivel] = data["indice"]
        return result

    # Fallback: INDEC empalme (feb 2026)
    result = dict(IPC_DIVISIONES_FEB2026)
    result["nivel_general"] = EMPALME_NIVEL_GENERAL
    return result


def seed_empalme_data():
    """
    Seed the DB with INDEC empalme data as the starting point.
    Only runs if no data exists yet.
    """
    existing = get_index_series("nivel_general")
    if existing:
        log.info("db.empalme_already_seeded", n_months=len(existing))
        return

    log.info("db.seeding_empalme")

    # Save feb 2026 as official data point
    save_monthly_index("2026-02", "nivel_general", EMPALME_NIVEL_GENERAL,
                       variacion=2.9, es_oficial=True)

    for div_code, indice in IPC_DIVISIONES_FEB2026.items():
        from config.ipc_oficial import VAR_DIVISIONES_FEB2026
        var = VAR_DIVISIONES_FEB2026.get(div_code, 0)
        save_monthly_index("2026-02", div_code, indice,
                           variacion=var, es_oficial=True)

    log.info("db.empalme_seeded")



# ─── Intra-month (daily) queries — MATCHED PRODUCTS ──────────────────────────
#
# To measure price VARIATION between days, we compare the SAME products
# on both days (matched pairs). This avoids artificial variation from
# different product mixes between days.

# Reemplazar la función get_matched_product_variations en storage/repository.py
# con esta versión que incluye winsorización para divisiones sin estacionalidad

# Divisiones sin estacionalidad — floor de -15% por producto
# Medicamentos, electrónica y electrodomésticos no tienen descuentos reales
# de más del 15% — si bajan más, es casi siempre una promoción temporal

DIVISIONES_SIN_ESTACIONALIDAD = {"05", "06", "09"}
FLOOR_VARIACION_PCT = -15.0  # % máximo de baja permitida por producto


def get_matched_product_variations(fecha_base: date, fecha_comp: date) -> dict[str, float]:
    """
    Compute price variation by division using only products that appear
    on BOTH dates (matched pairs).

    For divisions without seasonality (05, 06, 09), applies a -15% floor
    per product to avoid distortion from temporary discounts/promotions.

    Returns: {"01": 2.3, "02": -0.5, ...} — variation in %
    """
    session = get_session()
    try:
        rows = session.query(
            PrecioRaw.fecha,
            PrecioRaw.producto,
            PrecioRaw.division_coicop,
            PrecioRaw.precio,
        ).filter(
            PrecioRaw.fecha.in_([fecha_base, fecha_comp]),
            PrecioRaw.precio > 0,
            PrecioRaw.division_coicop.isnot(None),
            PrecioRaw.division_coicop != "",
        ).all()

        if not rows:
            return {}

        prices_base = {}
        prices_comp = {}

        for fecha, producto, division, precio in rows:
            key = (producto.strip().lower(), division)
            if fecha == fecha_base:
                if key in prices_base:
                    prices_base[key] = (prices_base[key] + precio) / 2
                else:
                    prices_base[key] = precio
            else:
                if key in prices_comp:
                    prices_comp[key] = (prices_comp[key] + precio) / 2
                else:
                    prices_comp[key] = precio

        matched_keys = set(prices_base.keys()) & set(prices_comp.keys())

        if not matched_keys:
            log.warning("db.no_matched_products",
                        base=str(fecha_base), comp=str(fecha_comp),
                        n_base=len(prices_base), n_comp=len(prices_comp))
            return {}

        relatives_by_div = defaultdict(list)
        winsorized_count = defaultdict(int)

        for key in matched_keys:
            producto, division = key
            p_base = prices_base[key]
            p_comp = prices_comp[key]

            if p_base > 0 and p_comp > 0:
                relative = p_comp / p_base
                var_pct = (relative - 1) * 100

                # Winsorización para divisiones sin estacionalidad
                # Si baja más del floor, asumimos descuento promocional → tratamos como 0%
                if division in DIVISIONES_SIN_ESTACIONALIDAD:
                    if var_pct < FLOOR_VARIACION_PCT:
                        log.debug(
                            "db.winsorized_product",
                            producto=producto,
                            division=division,
                            var_original=round(var_pct, 2),
                            floor=FLOOR_VARIACION_PCT,
                        )
                        relative = 1.0  # sin variación
                        winsorized_count[division] += 1

                relatives_by_div[division].append(relative)

        result = {}
        for div, relatives in relatives_by_div.items():
            if relatives:
                geo_mean_relative = float(np.exp(np.mean(np.log(relatives))))
                result[div] = (geo_mean_relative - 1) * 100

        if any(winsorized_count.values()):
            log.info(
                "db.winsorization_summary",
                base=str(fecha_base),
                comp=str(fecha_comp),
                winsorized=dict(winsorized_count),
            )

        log.info("db.matched_variations",
                 base=str(fecha_base), comp=str(fecha_comp),
                 n_matched=len(matched_keys),
                 divisions=list(result.keys()))

        return result

    except Exception as e:
        log.error("db.matched_variations_error", error=str(e))
        return {}
    finally:
        session.close()


def get_matched_daily_series(mes: str) -> list[dict]:
    """
    Build daily variation series using matched products.
    Each day is compared to the FIRST day of the month (base day).
    """
    session = get_session()
    try:
        year, month = int(mes[:4]), int(mes[5:7])
        fecha_inicio = date(year, month, 1)
        if month == 12:
            fecha_fin = date(year + 1, 1, 1)
        else:
            fecha_fin = date(year, month + 1, 1)

        dates = session.query(distinct(PrecioRaw.fecha)).filter(
            PrecioRaw.fecha >= fecha_inicio,
            PrecioRaw.fecha < fecha_fin,
        ).order_by(PrecioRaw.fecha).all()

        dates = sorted([d[0] for d in dates])

        if len(dates) < 2:
            if len(dates) == 1:
                return [{"fecha": dates[0].isoformat(), "var_acumulada": 0.0,
                         "var_por_division": {}, "n_matched": 0}]
            return []

        base_date = dates[0]
        pesos = None

        serie = [{"fecha": base_date.isoformat(), "var_acumulada": 0.0,
                  "var_por_division": {}, "n_matched": 0}]

        for comp_date in dates[1:]:
            vars_div = get_matched_product_variations(base_date, comp_date)

            if vars_div:
                if pesos is None:
                    from config.canasta import get_all_weights, EXCLUIDAS
                    pesos = get_all_weights()

                peso_total = sum(pesos.get(k, 0) for k in vars_div if k not in EXCLUIDAS)
                if peso_total > 0:
                    var_acum = sum(
                        vars_div[k] * (pesos.get(k, 0) / peso_total)
                        for k in vars_div
                        if k not in EXCLUIDAS
                    )
                else:
                    var_acum = 0.0
            else:
                var_acum = 0.0

            serie.append({
                "fecha": comp_date.isoformat(),
                "var_acumulada": round(var_acum, 3),
                "var_por_division": {k: round(v, 2) for k, v in vars_div.items()},
                "n_matched": len(vars_div),
            })

        return serie

    except Exception as e:
        log.error("db.matched_daily_series_error", mes=mes, error=str(e))
        return []
    finally:
        session.close()


def get_daily_avg_by_division(fecha: date) -> dict[str, float]:
    """Geometric mean of prices per division for a specific day."""
    session = get_session()
    try:
        rows = session.query(
            PrecioRaw.division_coicop,
            PrecioRaw.precio,
        ).filter(
            PrecioRaw.fecha == fecha,
            PrecioRaw.precio > 0,
            PrecioRaw.division_coicop.isnot(None),
            PrecioRaw.division_coicop != "",
        ).all()

        if not rows:
            return {}

        by_division = defaultdict(list)
        for div, precio in rows:
            by_division[div].append(precio)

        result = {}
        for div, precios in by_division.items():
            if precios:
                result[div] = float(np.exp(np.mean(np.log(precios))))
        return result
    except Exception as e:
        log.error("db.daily_avg_error", fecha=str(fecha), error=str(e))
        return {}
    finally:
        session.close()


def get_first_day_of_month_with_data(mes: str) -> date | None:
    """Get the earliest date with price data in a given month."""
    session = get_session()
    try:
        year, month = int(mes[:4]), int(mes[5:7])
        fecha_inicio = date(year, month, 1)
        fecha_fin = date(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
        return session.query(func.min(PrecioRaw.fecha)).filter(
            PrecioRaw.fecha >= fecha_inicio, PrecioRaw.fecha < fecha_fin,
        ).scalar()
    except Exception:
        return None
    finally:
        session.close()


def get_last_day_of_month_with_data(mes: str) -> date | None:
    """Get the latest date with price data in a given month."""
    session = get_session()
    try:
        year, month = int(mes[:4]), int(mes[5:7])
        fecha_inicio = date(year, month, 1)
        fecha_fin = date(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
        return session.query(func.max(PrecioRaw.fecha)).filter(
            PrecioRaw.fecha >= fecha_inicio, PrecioRaw.fecha < fecha_fin,
        ).scalar()
    except Exception:
        return None
    finally:
        session.close()


def get_all_daily_avgs_in_month(mes: str) -> dict[str, dict[str, float]]:
    """Get geometric mean prices per division for each day in a month."""
    session = get_session()
    try:
        year, month = int(mes[:4]), int(mes[5:7])
        fecha_inicio = date(year, month, 1)
        fecha_fin = date(year + (1 if month == 12 else 0), (month % 12) + 1, 1)

        rows = session.query(
            PrecioRaw.fecha, PrecioRaw.division_coicop, PrecioRaw.precio,
        ).filter(
            PrecioRaw.fecha >= fecha_inicio, PrecioRaw.fecha < fecha_fin,
            PrecioRaw.precio > 0, PrecioRaw.division_coicop.isnot(None),
            PrecioRaw.division_coicop != "",
        ).all()

        if not rows:
            return {}

        by_day_div = defaultdict(lambda: defaultdict(list))
        for fecha, div, precio in rows:
            by_day_div[fecha.isoformat()][div].append(precio)

        result = {}
        for day_str, divs in sorted(by_day_div.items()):
            result[day_str] = {}
            for div, precios in divs.items():
                if precios:
                    result[day_str][div] = float(np.exp(np.mean(np.log(precios))))
        return result
    except Exception as e:
        log.error("db.all_daily_avgs_error", mes=mes, error=str(e))
        return {}
    finally:
        session.close()
