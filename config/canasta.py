"""
R&V IPC — Canasta COICOP con ponderadores GBA (dic 2016).

Fuente: INDEC Metodología N°32, Cuadro 7 — Anexo II.
Ponderadores regionales del IPC, región GBA.
"""
from dataclasses import dataclass, field


@dataclass
class Variedad:
    """Menor agrupación con ponderador asignado."""
    codigo: str
    nombre: str
    peso: float  # % dentro de la división
    keywords: list[str] = field(default_factory=list)  # Para matchear productos scrapeados


@dataclass
class Division:
    codigo: str
    nombre: str
    nombre_corto: str
    peso_gba: float  # % del nivel general
    variedades: list[Variedad] = field(default_factory=list)
    collector_ids: list[str] = field(default_factory=list)


# ─── 12 DIVISIONES COICOP — PESOS GBA ───────────────────────────────────
DIVISIONES: list[Division] = [
    Division(
        codigo="01", nombre="Alimentos y bebidas no alcohólicas",
        nombre_corto="Alimentos", peso_gba=23.44,
        collector_ids=["jumbo", "coto", "carrefour"],
        variedades=[
            Variedad("01.1.1", "Pan y cereales", 4.05,
                     ["pan", "galletitas", "harina", "arroz", "fideos", "cereales"]),
            Variedad("01.1.2", "Carnes y derivados", 6.98,
                     ["carne", "pollo", "cerdo", "milanesa", "hamburguesa", "salchicha"]),
            Variedad("01.1.3", "Pescados y mariscos", 0.51,
                     ["merluza", "atún", "salmón"]),
            Variedad("01.1.4", "Leche, productos lácteos y huevos", 3.45,
                     ["leche", "yogur", "queso", "manteca", "huevos", "crema"]),
            Variedad("01.1.5", "Aceites, grasas y manteca", 0.55,
                     ["aceite", "girasol", "oliva", "manteca"]),
            Variedad("01.1.6", "Frutas", 1.27,
                     ["manzana", "banana", "naranja", "mandarina", "uva", "frutilla"]),
            Variedad("01.1.7", "Verduras, tubérculos y legumbres", 2.23,
                     ["tomate", "papa", "cebolla", "lechuga", "zanahoria", "zapallo"]),
            Variedad("01.1.8", "Azúcar, dulces, chocolate, golosinas", 1.01,
                     ["azúcar", "dulce de leche", "chocolate", "mermelada", "golosinas"]),
            Variedad("01.1.9", "Otros alimentos", 0.29,
                     ["sal", "mayonesa", "mostaza", "ketchup", "especias"]),
            Variedad("01.2.1", "Café, té, yerba y cacao", 0.68,
                     ["yerba", "café", "té", "cacao"]),
            Variedad("01.2.2", "Aguas minerales, bebidas gaseosas y jugos", 2.43,
                     ["agua mineral", "gaseosa", "coca", "jugo", "soda"]),
        ],
    ),
    Division(
        codigo="02", nombre="Bebidas alcohólicas y tabaco",
        nombre_corto="Bebidas y tabaco", peso_gba=3.27,
        collector_ids=["jumbo", "coto"],
        variedades=[
            Variedad("02.1.2", "Vinos", 1.07, ["vino", "tinto", "malbec"]),
            Variedad("02.1.3", "Cerveza", 0.29, ["cerveza", "quilmes", "brahma"]),
            Variedad("02.1.1", "Bebidas espirituosas", 0.06, ["fernet", "whisky", "vodka"]),
            Variedad("02.2", "Tabaco", 1.85, ["cigarrillos", "marlboro"]),
        ],
    ),
    Division(
        codigo="03", nombre="Prendas de vestir y calzado",
        nombre_corto="Indumentaria", peso_gba=8.49,
        collector_ids=[],  # Difícil de cubrir online
        variedades=[
            Variedad("03.1.2", "Prendas de vestir", 5.76, ["remera", "pantalón", "camisa"]),
            Variedad("03.2.1", "Zapatos y otros calzados", 2.09, ["zapatillas", "zapatos"]),
        ],
    ),
    Division(
        codigo="04", nombre="Vivienda, agua, electricidad, gas y otros combustibles",
        nombre_corto="Vivienda y servicios", peso_gba=10.46,
        collector_ids=["zonaprop", "tarifas_electricidad", "tarifas_gas", "tarifas_agua"],
        variedades=[
            Variedad("04.1.1", "Alquiler de la vivienda", 3.48, ["alquiler"]),
            Variedad("04.1.3", "Gastos comunes / expensas", 2.32, ["expensas"]),
            Variedad("04.4", "Suministro de agua", 0.89, ["agua", "aysa"]),
            Variedad("04.5.1", "Electricidad", 1.03, ["electricidad", "edenor", "edesur"]),
            Variedad("04.5.2", "Gas", 1.51, ["gas natural", "metrogas"]),
            Variedad("04.3", "Mantenimiento y reparación vivienda", 1.23, ["pintura", "cemento"]),
        ],
    ),
    Division(
        codigo="05", nombre="Equipamiento y mantenimiento del hogar",
        nombre_corto="Equipamiento hogar", peso_gba=6.27,
        collector_ids=["fravega", "jumbo", "coto"],
        variedades=[
            Variedad("05.3", "Artefactos para el hogar", 1.14,
                     ["heladera", "lavarropas", "microondas", "horno"]),
            Variedad("05.6.1", "Bienes para el hogar no durables", 1.67,
                     ["detergente", "lavandina", "papel higiénico", "servilletas"]),
            Variedad("05.6.2", "Servicios domésticos", 1.99, ["servicio doméstico"]),
        ],
    ),
    Division(
        codigo="06", nombre="Salud",
        nombre_corto="Salud", peso_gba=8.80,
        collector_ids=["farmacity", "prepagas"],
        variedades=[
            Variedad("06.1.1", "Productos farmacéuticos", 3.53,
                     ["ibuprofeno", "paracetamol", "tafirol", "aspirina"]),
            Variedad("06.4", "Gastos de prepagas y obras sociales", 3.18,
                     ["osde", "swiss medical", "galeno", "prepaga"]),
            Variedad("06.2", "Servicios para pacientes externos", 1.68,
                     ["consulta médica", "odontólogo"]),
        ],
    ),
    Division(
        codigo="07", nombre="Transporte",
        nombre_corto="Transporte", peso_gba=11.59,
        collector_ids=["combustibles", "transporte_publico"],
        variedades=[
            Variedad("07.2.2", "Combustibles y lubricantes", 3.78,
                     ["nafta", "gasoil", "super", "premium", "diesel"]),
            Variedad("07.3.1", "Servicios de transporte automotor", 3.32,
                     ["colectivo", "sube"]),
            Variedad("07.3.2", "Servicios de transporte ferroviario", 0.40,
                     ["tren", "subte"]),
            Variedad("07.1.1", "Vehículos a motor", 2.45, ["auto", "0km"]),
            Variedad("07.2.1", "Funcionamiento equipos transporte", 0.56,
                     ["estacionamiento", "seguro auto"]),
        ],
    ),
    Division(
        codigo="08", nombre="Comunicación",
        nombre_corto="Comunicación", peso_gba=2.81,
        collector_ids=["comunicaciones"],
        variedades=[
            Variedad("08.3.1", "Servicio de teléfonos fijos", 0.58, ["telefonía fija"]),
            Variedad("08.3.2", "Servicio de telefonía móvil", 1.39,
                     ["plan celular", "personal", "claro", "movistar"]),
            Variedad("08.3.3", "Servicio de internet", 0.76,
                     ["internet", "fibra", "flow", "telecentro"]),
        ],
    ),
    Division(
        codigo="09", nombre="Recreación y cultura",
        nombre_corto="Recreación y cultura", peso_gba=7.46,
        collector_ids=["fravega"],
        variedades=[
            Variedad("09.1", "Equipos audiovisuales y procesamiento", 1.34,
                     ["tv", "smart tv", "notebook", "celular"]),
            Variedad("09.4.2", "Servicios culturales", 2.19,
                     ["cable", "streaming", "netflix", "spotify"]),
            Variedad("09.5", "Periódicos, libros y papelería", 1.49,
                     ["libro", "cuaderno", "diario"]),
        ],
    ),
    Division(
        codigo="10", nombre="Educación",
        nombre_corto="Educación", peso_gba=3.02,
        collector_ids=[],  # No disponible sistemáticamente online
        variedades=[
            Variedad("10.1", "Educación preescolar y primaria", 1.30, ["colegio"]),
            Variedad("10.3", "Educación postsecundaria", 0.63, ["universidad"]),
        ],
    ),
    Division(
        codigo="11", nombre="Restaurantes y hoteles",
        nombre_corto="Restaurantes y hoteles", peso_gba=10.84,
        collector_ids=["pedidosya"],
        variedades=[
            Variedad("11.1", "Restaurantes y comidas fuera del hogar", 10.31,
                     ["pizza", "empanada", "milanesa", "hamburguesa", "menú"]),
        ],
    ),
    Division(
        codigo="12", nombre="Bienes y servicios varios",
        nombre_corto="Bienes y serv. varios", peso_gba=3.55,
        collector_ids=["jumbo", "coto", "farmacity"],
        variedades=[
            Variedad("12.1.1", "Salones de peluquería", 0.85, ["peluquería", "corte"]),
            Variedad("12.1.3", "Artículos cuidado personal", 1.97,
                     ["shampoo", "desodorante", "jabón", "crema", "pasta dental"]),
        ],
    ),
]


# ─── DIVISIONES EXCLUIDAS ───────────────────────────────────────────────────
# Indumentaria (03) y Educación (10) no se pueden cubrir online.
# Se excluyen y se redistribuye su peso proporcionalmente al resto.
EXCLUIDAS = {"03", "10"}


# ─── HELPERS ────────────────────────────────────────────────────────────────
def get_division(codigo: str) -> Division | None:
    return next((d for d in DIVISIONES if d.codigo == codigo), None)


def get_divisiones_activas() -> list[Division]:
    """Returns only divisions with data coverage (excluding 03 and 10)."""
    return [d for d in DIVISIONES if d.codigo not in EXCLUIDAS]


def get_all_weights_raw() -> dict[str, float]:
    """Returns original INDEC weights (sum ~100%)."""
    return {d.codigo: d.peso_gba for d in DIVISIONES}


def get_all_weights() -> dict[str, float]:
    """
    Returns adjusted weights with 03 and 10 excluded.
    Redistributes their weight proportionally to remaining divisions.
    Sum of returned weights = 100%.
    """
    activas = get_divisiones_activas()
    peso_activas = sum(d.peso_gba for d in activas)
    # Rescale so active divisions sum to 100%
    factor = 100.0 / peso_activas
    return {d.codigo: round(d.peso_gba * factor, 4) for d in activas}


def total_weight() -> float:
    """Original INDEC weights (should sum ~100%)."""
    return sum(d.peso_gba for d in DIVISIONES)


def active_weight() -> float:
    """Sum of adjusted active weights (should be exactly 100%)."""
    return sum(get_all_weights().values())


def covered_weight() -> float:
    """% of original GBA basket that has collectors."""
    return sum(d.peso_gba for d in DIVISIONES if d.collector_ids)


# Verify original weights sum ~100%
assert 99.5 < total_weight() < 100.5, f"Weights sum = {total_weight()}"

# Verify adjusted weights sum to 100%
_adj = active_weight()
assert 99.9 < _adj < 100.1, f"Adjusted weights sum = {_adj}"
