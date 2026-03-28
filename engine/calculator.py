"""
R&V IPC — Motor de cálculo del índice.

Replica las fórmulas de la Metodología INDEC N°32:
- Media geométrica para precios promedio por variedad (fórmula 7)
- Relativos de precios (fórmula 9)
- Índices elementales por productoria de relativos (fórmula 10)
- Laspeyres: suma ponderada de índices elementales (fórmula 11)
- Índice nacional como suma ponderada de regiones (fórmula 14)
- Incidencia (fórmula 16)
"""
import numpy as np
from dataclasses import dataclass
from datetime import date
from config.canasta import DIVISIONES, get_all_weights


@dataclass
class IndiceResult:
    """Result of index calculation."""
    fecha: date
    nivel: str  # "nivel_general", "01", "nucleo", etc.
    indice: float
    variacion_periodo: float | None  # % vs previous
    base_anterior: float | None  # Previous index value


def media_geometrica(precios: list[float]) -> float:
    """
    Media geométrica simple (fórmula 7 — Metodología N°32).

    P̄_{g,v} = ∏(p_{g,v,i})^{1/n_g}

    Se usa para calcular el precio promedio de una variedad
    a partir de precios de artículos en distintos puntos de venta.
    """
    if not precios:
        return 0.0
    precios_validos = [p for p in precios if p > 0]
    if not precios_validos:
        return 0.0
    log_mean = np.mean(np.log(precios_validos))
    return float(np.exp(log_mean))


def media_geometrica_ponderada(
    precios_tradicional: float,
    precios_super: float,
    alpha_super: float = 0.4,  # % gasto en supermercados
) -> float:
    """
    Media geométrica ponderada por tipo de negocio (fórmula 8).

    P̄_v = (P̄_{c,v})^{α_c} × (P̄_{s,v})^{α_s}

    donde α_c + α_s = 1
    """
    alpha_trad = 1.0 - alpha_super
    if precios_tradicional <= 0 or precios_super <= 0:
        return precios_tradicional if precios_super <= 0 else precios_super
    return (precios_tradicional ** alpha_trad) * (precios_super ** alpha_super)


def relativo_precios(precio_actual: float, precio_anterior: float) -> float:
    """
    Relativo de precios entre dos períodos (fórmula 9).

    R_{v,r}^{t-1,t} = P̄_{v,r}^t / P̄_{v,r}^{t-1}
    """
    if precio_anterior <= 0:
        return 1.0
    return precio_actual / precio_anterior


def indice_elemental(relativos: list[float], base: float = 100.0) -> float:
    """
    Índice elemental como productoria de relativos (fórmula 10).

    I_{v,r}^{0,t} = R_{v,r}^{0,1} × R_{v,r}^{1,2} × ... × R_{v,r}^{t-1,t} × 100
    """
    result = base
    for r in relativos:
        result *= r
    return result


def laspeyres(
    indices: dict[str, float],
    pesos: dict[str, float],
) -> float:
    """
    Índice tipo Laspeyres — suma ponderada (fórmula 11).

    I_{A,r}^{0,t} = Σ w_{v,r} × I_{v,r}^{0,t}

    Args:
        indices: {division_code: index_value}
        pesos: {division_code: weight (% of total)}

    Returns:
        Weighted aggregate index.
    """
    total_weight = sum(pesos.get(k, 0) for k in indices)
    if total_weight == 0:
        return 0.0

    weighted_sum = sum(
        indices[k] * (pesos.get(k, 0) / total_weight)
        for k in indices
        if k in pesos
    )
    return weighted_sum


def variacion_porcentual(indice_actual: float, indice_anterior: float) -> float:
    """
    Variación porcentual del índice (fórmula 4).

    Δ_{t,t-1} = (I_t - I_{t-1}) / I_{t-1} × 100
    """
    if indice_anterior <= 0:
        return 0.0
    return ((indice_actual - indice_anterior) / indice_anterior) * 100


def incidencia(
    indice_agrup_actual: float,
    indice_agrup_anterior: float,
    indice_ng_anterior: float,
    peso_agrupacion: float,
) -> float:
    """
    Incidencia de una agrupación sobre el nivel general (fórmula 16).

    Incidencia_{A}^{t,t-1} = (I_A^t - I_A^{t-1}) × w_A / I_{NG}^{t-1}

    Returns: puntos porcentuales de contribución al nivel general.
    """
    if indice_ng_anterior <= 0:
        return 0.0
    return ((indice_agrup_actual - indice_agrup_anterior) * peso_agrupacion) / indice_ng_anterior


def inflacion_anualizada(var_mensual_pct: float) -> float:
    """Inflación anualizada compuesta desde tasa mensual."""
    return ((1 + var_mensual_pct / 100) ** 12 - 1) * 100


def calcular_indice_nivel_general(
    variaciones_division: dict[str, float],
    indices_base_division: dict[str, float],
) -> dict:
    """
    Calcula el nivel general a partir de variaciones por división.

    Para divisiones sin datos propios (variación = None),
    se asume variación 0 (se mantiene el índice anterior).

    Args:
        variaciones_division: {"01": 3.2, "02": 0.5, ...} — % mensual
        indices_base_division: {"01": 11624.98, ...} — índices base (empalme)

    Returns:
        dict con indices nuevos por división, nivel general, y variaciones.
    """
    pesos = get_all_weights()
    nuevos_indices = {}

    for div in DIVISIONES:
        cod = div.codigo
        base = indices_base_division.get(cod, 0)
        var = variaciones_division.get(cod)

        if var is not None and base > 0:
            nuevos_indices[cod] = base * (1 + var / 100)
        else:
            # Sin datos → mantener índice anterior
            nuevos_indices[cod] = base

    # Nivel general = Laspeyres de las 12 divisiones
    nivel_general = laspeyres(nuevos_indices, pesos)

    return {
        "indices_division": nuevos_indices,
        "nivel_general": nivel_general,
        "pesos": pesos,
    }
