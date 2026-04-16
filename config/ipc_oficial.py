"""
R&V IPC — Datos oficiales INDEC para empalme y comparación.

Fuente: INDEC, IPC GBA Base Diciembre 2016=100
Última actualización: Abril 2026 (datos marzo 2026 publicados)
"""

# ─── Empalme: febrero 2026 (punto de partida del sistema R&V) ────────────────
# Estos son los índices a los que se ancla la serie R&V.
# Base: Diciembre 2016 = 100

EMPALME_NIVEL_GENERAL = 10714.63
EMPALME_FECHA = "2026-02"

IPC_DIVISIONES_FEB2026 = {
    "01": 11624.98,   # Alimentos y bebidas no alcohólicas
    "02": 7659.91,    # Bebidas alcohólicas y tabaco
    "04": 11614.19,   # Vivienda, agua, electricidad y gas
    "05": 8811.54,    # Equipamiento y mantenimiento del hogar
    "06": 11886.50,   # Salud
    "07": 11124.88,   # Transporte
    "08": 9784.56,    # Comunicación
    "09": 9427.94,    # Recreación y cultura
    "10": 9010.40,    # Educación
    "11": 13228.65,   # Restaurantes y hoteles
    "12": 10476.99,   # Bienes y servicios varios
}

VAR_DIVISIONES_FEB2026 = {
    "01": 2.9,
    "02": 2.8,
    "04": 3.4,
    "05": 1.5,
    "06": 2.3,
    "07": 2.0,
    "08": 3.6,
    "09": 1.3,
    "10": 1.7,
    "11": 4.1,
    "12": 2.9,
    "nivel_general": 2.9,
}

# ─── Marzo 2026 (primer mes con datos oficiales INDEC post-empalme) ──────────
# Variaciones mensuales GBA — fuente: INDEC sh_ipc_04_26.xls
# Publicado: abril 2026

IPC_NIVEL_GENERAL_MAR2026 = 11078.93

IPC_DIVISIONES_MAR2026 = {
    "01": 11962.10,   # Alimentos y bebidas no alcohólicas  (+2.9%)
    "02": 7820.77,    # Bebidas alcohólicas y tabaco         (+2.1%)
    "04": 12032.30,   # Vivienda, agua, electricidad y gas  (+3.6%)
    "05": 8926.09,    # Equipamiento y mantenimiento hogar  (+1.3%)
    "06": 12243.10,   # Salud                               (+3.0%)
    "07": 11647.75,   # Transporte                          (+4.7%)
    "08": 10078.10,   # Comunicación                        (+3.0%)
    "09": 9729.63,    # Recreación y cultura                (+3.2%)
    "10": 9974.51,    # Educación                           (+10.7%)
    "11": 13665.20,   # Restaurantes y hoteles              (+3.3%)
    "12": 10665.58,   # Bienes y servicios varios           (+1.8%)
}

VAR_DIVISIONES_MAR2026 = {
    "01": 2.9,
    "02": 2.1,
    "04": 3.6,
    "05": 1.3,
    "06": 3.0,
    "07": 4.7,
    "08": 3.0,
    "09": 3.2,
    "10": 10.7,
    "11": 3.3,
    "12": 1.8,
    "nivel_general": 3.4,
    "nucleo": 3.0,
    "regulados": 5.4,
}
