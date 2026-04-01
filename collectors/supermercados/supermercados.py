"""
R&V IPC — Supermercados collector (Precios Claros / SEPA).

PRIMARY SOURCE: Precios Claros API (CloudFront CDN) — government mandated prices
from 3,600+ supermarkets across Argentina, updated daily.

FALLBACK: SEPA open data CSVs from datos.produccion.gob.ar

TERTIARY: Jumbo VTEX API (direct e-commerce API, JSON, no scraping)

Covers COICOP:
- 01 Alimentos y bebidas no alcohólicas (~26.5%)
- 02 Bebidas alcohólicas y tabaco (~3.7%)
- 05.6 Bienes y servicios para el mantenimiento del hogar (cleaning)
- 12.1 Cuidado personal (hygiene products)
"""
from collectors.base import BaseCollector, PriceObservation, parse_price_ar
from collectors.registry import register_collector
import structlog
import re

log = structlog.get_logger()

# Precios Claros CloudFront API
PC_CDN = "https://d3e6htiiul5ek9.cloudfront.net/prod"
PC_API_KEY = "qfcNgctUb27Qw5w07u0sA5pNfp51Q9mo9XhIuZpwResponderEliminar"  # Public API key from community

# GBA sucursales IDs — representative sample (Jumbo, Coto, Carrefour, Disco, Walmart/Changomas)
# Format: "cadena_id-banner_id-sucursal_id"
GBA_SUCURSALES = [
    "9-1-485",   # Jumbo GBA
    "15-1-1060", # Coto GBA
    "2-1-1",     # Carrefour
    "10-1-1",    # Disco
]

# Representative basket — EAN codes for canasta básica products
# Mapped to COICOP subdivisions
CANASTA_PRODUCTOS = {
    "01.1.1": {  # Pan y cereales
        "terms": ["arroz", "fideos", "pan lactal", "harina", "galletitas"],
    },
    "01.1.2": {  # Carnes
        "terms": ["carne picada", "pollo", "nalga", "milanesa"],
    },
    "01.1.4": {  # Leche, queso y huevos
        "terms": ["leche entera", "yogur", "queso cremoso"],
    },
    "01.1.5": {  # Aceites y grasas
        "terms": ["aceite girasol", "aceite oliva"],
    },
    "01.1.7": {  # Frutas y verduras
        "terms": ["tomate", "papa", "cebolla", "lechuga", "banana"],
    },
    "01.1.8": {  # Azúcar, dulces
        "terms": ["azucar", "dulce de leche", "mermelada"],
    },
    "01.2.1": {  # Café y mate
        "terms": ["yerba mate", "cafe"],
    },
    "01.2.2": {  # Bebidas sin alcohol
        "terms": ["coca cola", "agua mineral", "jugo"],
    },
    "02.1.2": {  # Vinos
        "terms": ["vino tinto", "vino malbec"],
    },
    "02.1.3": {  # Cerveza
        "terms": ["cerveza"],
    },
    "05.6.1": {  # Limpieza hogar
        "terms": ["detergente", "lavandina", "papel higienico"],
    },
    "12.1.3": {  # Higiene personal
        "terms": ["shampoo", "desodorante", "jabon", "pasta dental"],
    },
}

# Jumbo VTEX API as tertiary fallback
VTEX_BASE = "https://www.jumbo.com.ar/api/catalog_system/pub/products/search"


@register_collector
class SupermercadosCollector(BaseCollector):
    collector_id = "supermercados"
    division_coicop = "01"  # Primary
    description = "Supermercados — Precios Claros / SEPA / Jumbo VTEX"

    def collect(self) -> list[PriceObservation]:
        # Strategy 1: Precios Claros API
        obs = self._try_precios_claros()
        if obs:
            return obs

        # Strategy 2: Jumbo VTEX API (JSON, no scraping)
        obs = self._try_jumbo_vtex()
        if obs:
            return obs

        log.warning("supermercados.all_sources_failed")
        return []

    def _try_precios_claros(self) -> list[PriceObservation]:
        """Use Precios Claros CloudFront API to get supermarket prices."""
        observations = []

        # First get nearby sucursales for GBA
        try:
            # San Isidro coords as center point for GBA
            sucursales_data = self.fetch_json(
                f"{PC_CDN}/sucursales",
                params={"lat": "-34.47", "lng": "-58.53", "limit": "30"},
                headers={**self.client.headers, "x-api-key": PC_API_KEY},
            )

            sucursales = sucursales_data if isinstance(sucursales_data, list) else \
                sucursales_data.get("sucursales", []) if isinstance(sucursales_data, dict) else []

            if not sucursales:
                log.debug("supermercados.pc_no_sucursales")
                return []

            # Build array of sucursal IDs
            suc_ids = []
            for s in sucursales[:10]:
                sid = s.get("id", "")
                if sid:
                    suc_ids.append(str(sid))

            if not suc_ids:
                return []

            suc_array = ",".join(suc_ids)
            log.info("supermercados.pc_sucursales_found", n=len(suc_ids))

        except Exception as e:
            log.debug("supermercados.pc_sucursales_error", error=str(e))
            return []

        # Now search products
        for coicop_code, config in CANASTA_PRODUCTOS.items():
            division = coicop_code.split(".")[0]
            for term in config["terms"]:
                try:
                    data = self.fetch_json(
                        f"{PC_CDN}/productos",
                        params={
                            "string": term,
                            "array_sucursales": suc_array,
                            "offset": "0",
                            "limit": "10",
                        },
                        headers={**self.client.headers, "x-api-key": PC_API_KEY},
                    )

                    productos = data if isinstance(data, list) else \
                        data.get("productos", []) if isinstance(data, dict) else []

                    for prod in productos[:5]:
                        nombre = prod.get("nombre", "") or prod.get("descripcion", "")
                        marca = prod.get("marca", "")
                        full_name = f"{marca} {nombre}".strip() if marca else nombre

                        # Get best price across sucursales
                        precio_raw = (
                            prod.get("precioMin", None) or
                            prod.get("precio", None) or
                            prod.get("precioLista", None)
                        )

                        if precio_raw is None:
                            # Try nested precio structure
                            precios_suc = prod.get("preciosSucursal", [])
                            if precios_suc:
                                vals = [p.get("precioLista", 0) for p in precios_suc if p.get("precioLista")]
                                if vals:
                                    precio_raw = sum(vals) / len(vals)

                        if precio_raw and float(precio_raw) > 0:
                            observations.append(PriceObservation(
                                producto=full_name,
                                precio=float(precio_raw),
                                categoria_coicop=coicop_code,
                                division_coicop=division,
                                fuente="Precios Claros",
                                url="https://www.preciosclaros.gob.ar",
                                metadata={"term": term},
                            ))

                except Exception as e:
                    log.debug("supermercados.pc_product_error", term=term, error=str(e))

        if observations:
            log.info("supermercados.precios_claros_ok", n=len(observations))

        return observations

    def _try_jumbo_vtex(self) -> list[PriceObservation]:
        """Fallback: Jumbo VTEX ecommerce API (JSON, no HTML scraping)."""
        observations = []

        for coicop_code, config in CANASTA_PRODUCTOS.items():
            division = coicop_code.split(".")[0]
            for term in config["terms"]:
                try:
                    products = self.fetch_json(
                        VTEX_BASE,
                        params={"ft": term, "_from": 0, "_to": 4},
                        headers={**self.client.headers, "Accept": "application/json"},
                    )

                    if not isinstance(products, list):
                        continue

                    for p in products[:3]:
                        name = p.get("productName", "")
                        items = p.get("items", [])
                        if not items:
                            continue

                        seller = items[0].get("sellers", [{}])[0]
                        offer = seller.get("commertialOffer", {})
                        price = offer.get("Price", 0)

                        if price and price > 0:
                            link = p.get("link", "")
                            if link and not link.startswith("http"):
                                link = f"https://www.jumbo.com.ar{link}"

                            observations.append(PriceObservation(
                                producto=name,
                                precio=price,
                                categoria_coicop=coicop_code,
                                division_coicop=division,
                                fuente="Jumbo (VTEX)",
                                url=link,
                                metadata={"term": term},
                            ))
                except Exception as e:
                    log.debug("supermercados.vtex_error", term=term, error=str(e))

        if observations:
            log.info("supermercados.jumbo_vtex_ok", n=len(observations))

        return observations
