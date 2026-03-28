"""
R&V IPC — Datos oficiales del IPC-INDEC para empalme.

Fuente: sh_ipc_03_26.xls (INDEC), hoja 'Índices IPC Cobertura Nacional'.
Último dato disponible: febrero 2026.
"""

# Nivel general del IPC Nacional (base dic 2016 = 100)
# Usamos los últimos 3 meses para tener referencia de variaciones
IPC_OFICIAL = {
    "2025-12": 10121.37,
    "2026-01": 10413.03,
    "2026-02": 10714.63,  # ← Punto de empalme
}

# Variaciones mensuales oficiales (%)
VAR_MENSUAL_OFICIAL = {
    "2025-12": 2.8,
    "2026-01": 2.9,
    "2026-02": 2.9,
}

# Variaciones interanuales oficiales (%)
VAR_INTERANUAL_OFICIAL = {
    "2026-01": 32.4,
    "2026-02": 33.1,
}

# Índices por división COICOP — febrero 2026 (para empalme por división)
IPC_DIVISIONES_FEB2026 = {
    "01": 11624.98,   # Alimentos y bebidas no alcohólicas
    "02": 7659.91,    # Bebidas alcohólicas y tabaco
    "03": 7824.45,    # Prendas de vestir y calzado
    "04": 11614.19,   # Vivienda, agua, electricidad, gas
    "05": 8811.54,    # Equipamiento y mantenimiento hogar
    "06": 11886.50,   # Salud
    "07": 11124.88,   # Transporte
    "08": 9784.56,    # Comunicación
    "09": 9427.94,    # Recreación y cultura
    "10": 9010.40,    # Educación
    "11": 13228.65,   # Restaurantes y hoteles
    "12": 10476.99,   # Bienes y servicios varios
}

# Variaciones mensuales por división — febrero 2026 (%)
VAR_DIVISIONES_FEB2026 = {
    "01": 3.3,
    "02": 0.6,
    "03": 0.0,
    "04": 6.8,
    "05": 2.6,
    "06": 2.5,
    "07": 2.0,
    "08": 1.8,
    "09": 2.3,
    "10": 1.2,
    "11": 3.0,
    "12": 3.3,
}

EMPALME_FECHA = "2026-02-01"
EMPALME_NIVEL_GENERAL = 10714.63
