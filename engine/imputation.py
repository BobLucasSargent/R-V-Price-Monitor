"""
R&V IPC — Imputación de precios faltantes.

Replica la sección 7.1 de la Metodología INDEC N°32:
- Si >50% de precios válidos → imputar por variación de la misma variedad
- Si 20-50% válidos → imputar por variación del agrupamiento superior
- Si <20% válidos → descartar todos, imputar por agrupamiento superior
"""
import numpy as np
from dataclasses import dataclass


@dataclass
class ImputationResult:
    precio_imputado: float
    metodo: str  # "observado", "variacion_variedad", "variacion_superior", "descartado"
    confianza: float  # 0-1


def imputar_faltantes(
    precios_actuales: list[float | None],
    precios_anteriores: list[float],
    variacion_superior: float | None = None,
) -> list[ImputationResult]:
    """
    Imputa precios faltantes según metodología INDEC.

    Args:
        precios_actuales: Lista con precios observados (None = faltante)
        precios_anteriores: Precios del período anterior (misma posición)
        variacion_superior: Variación % del agrupamiento superior (fallback)

    Returns:
        Lista de ImputationResult con precio y método usado.
    """
    n_total = len(precios_actuales)
    if n_total == 0:
        return []

    # Count valid observations
    validos = [(i, p) for i, p in enumerate(precios_actuales) if p is not None and p > 0]
    n_validos = len(validos)
    ratio = n_validos / n_total if n_total > 0 else 0

    results = []

    if ratio > 0.5:
        # Caso i: >50% válidos → imputar por variación de la variedad
        variacion_variedad = _calcular_variacion_observados(validos, precios_anteriores)

        for i in range(n_total):
            if precios_actuales[i] is not None and precios_actuales[i] > 0:
                results.append(ImputationResult(
                    precio_imputado=precios_actuales[i],
                    metodo="observado",
                    confianza=1.0,
                ))
            else:
                # Imputar: precio anterior × variación observada
                p_ant = precios_anteriores[i] if i < len(precios_anteriores) else 0
                if p_ant > 0 and variacion_variedad is not None:
                    results.append(ImputationResult(
                        precio_imputado=p_ant * (1 + variacion_variedad),
                        metodo="variacion_variedad",
                        confianza=0.7,
                    ))
                elif variacion_superior is not None and p_ant > 0:
                    results.append(ImputationResult(
                        precio_imputado=p_ant * (1 + variacion_superior / 100),
                        metodo="variacion_superior",
                        confianza=0.4,
                    ))
                else:
                    results.append(ImputationResult(
                        precio_imputado=p_ant if p_ant > 0 else 0,
                        metodo="repetido",
                        confianza=0.2,
                    ))

    elif ratio >= 0.2:
        # Caso ii: 20-50% válidos → imputar por agrupamiento superior
        for i in range(n_total):
            if precios_actuales[i] is not None and precios_actuales[i] > 0:
                results.append(ImputationResult(
                    precio_imputado=precios_actuales[i],
                    metodo="observado",
                    confianza=1.0,
                ))
            else:
                p_ant = precios_anteriores[i] if i < len(precios_anteriores) else 0
                if variacion_superior is not None and p_ant > 0:
                    results.append(ImputationResult(
                        precio_imputado=p_ant * (1 + variacion_superior / 100),
                        metodo="variacion_superior",
                        confianza=0.4,
                    ))
                else:
                    results.append(ImputationResult(
                        precio_imputado=p_ant,
                        metodo="repetido",
                        confianza=0.2,
                    ))

    else:
        # Caso iii: <20% válidos → descartar todos, usar variación superior
        for i in range(n_total):
            p_ant = precios_anteriores[i] if i < len(precios_anteriores) else 0
            if variacion_superior is not None and p_ant > 0:
                results.append(ImputationResult(
                    precio_imputado=p_ant * (1 + variacion_superior / 100),
                    metodo="descartado_imputado_superior",
                    confianza=0.2,
                ))
            else:
                results.append(ImputationResult(
                    precio_imputado=p_ant,
                    metodo="descartado_repetido",
                    confianza=0.1,
                ))

    return results


def _calcular_variacion_observados(
    validos: list[tuple[int, float]],
    precios_anteriores: list[float],
) -> float | None:
    """Calculate average variation from observed prices vs previous period."""
    variaciones = []
    for idx, precio_actual in validos:
        if idx < len(precios_anteriores) and precios_anteriores[idx] > 0:
            var = (precio_actual - precios_anteriores[idx]) / precios_anteriores[idx]
            variaciones.append(var)

    if variaciones:
        return float(np.mean(variaciones))
    return None
