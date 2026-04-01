# R&V IPC — Handoff v3 (30 marzo 2026)

## Cambios realizados en esta sesión

### Bug crítico resuelto: collectors nunca se registraban
Los `__init__.py` de cada subcarpeta de collectors estaban **vacíos**. El decorator `@register_collector` solo se ejecuta al importar el módulo, pero nadie los importaba. Resultado: `get_all_collectors()` devolvía lista vacía → "No se obtuvieron precios".

**Fix**: Todos los `__init__.py` ahora importan explícitamente su collector. `collectors/__init__.py` importa todos los sub-paquetes. `engine/pipeline.py` importa `collectors` al inicio.

### Collectors completamente reescritos (9 total)

| Collector | Estrategia | Fuente | Estado |
|-----------|-----------|--------|--------|
| `supermercados` | API pública | Precios Claros CloudFront API → Jumbo VTEX fallback | NUEVO — reemplaza jumbo+coto |
| `combustibles` | API pública | datos.energia.gob.ar CKAN + auto-discovery | REESCRITO |
| `dolar` | API pública | ArgentinaDatos → DolarAPI fallback | REESCRITO |
| `farmacity` | Playwright | farmacity.com (VTEX SPA) | REESCRITO |
| `fravega` | Playwright | fravega.com (VTEX SPA) | REESCRITO |
| `pedidosya` | Playwright | pedidosya.com.ar (React SPA) | REESCRITO |
| `alquileres` | Playwright | zonaprop.com.ar | REESCRITO |
| `comunicaciones` | Playwright | Personal, Claro, Movistar, Telecentro | REESCRITO |
| `tarifas` | Playwright + fallback | Edenor/Metrogas/AySA → valores referencia | REESCRITO |

### Infraestructura actualizada
- `Dockerfile`: instala dependencias de Chromium + `playwright install chromium`
- `requirements.txt`: agrega `playwright>=1.49.0`
- `config/canasta.py`: `collector_ids` actualizados a nombres nuevos

### Arquitectura de collectors

```
collectors/
├── __init__.py              ← importa todos los sub-paquetes (CRÍTICO)
├── base.py                  ← BaseCollector (httpx) + PlaywrightCollector (nuevo)
├── registry.py              ← sin cambios
├── supermercados/
│   ├── __init__.py          ← importa SupermercadosCollector
│   └── supermercados.py     ← Precios Claros API + Jumbo VTEX
├── combustibles/
│   ├── __init__.py
│   └── combustibles.py      ← datos.energia.gob.ar CKAN
├── financieros/
│   ├── __init__.py
│   └── dolar.py             ← ArgentinaDatos + DolarAPI
├── medicamentos/
│   ├── __init__.py
│   └── farmacity.py         ← Playwright
├── electronica/
│   ├── __init__.py
│   └── fravega.py           ← Playwright
├── delivery/
│   ├── __init__.py
│   └── pedidosya.py         ← Playwright
├── alquileres/
│   ├── __init__.py
│   └── zonaprop.py          ← Playwright
├── comunicacion/
│   ├── __init__.py
│   └── planes.py            ← Playwright
└── tarifas/
    ├── __init__.py
    └── servicios.py          ← Playwright + valores referencia
```

## Estado actual

### Funciona
- API responde en todos los endpoints GET
- Dashboard muestra datos INDEC históricos (110 meses)
- Empalme con IPC oficial feb 2026 = 10.714,63
- 45 tests passing
- **9 collectors registrados y importando correctamente**
- Pipeline completo: collect → aggregate → Laspeyres → empalme

### Pendiente de verificar en producción
1. **Deploy en Railway**: El Dockerfile ahora instala Chromium (~400MB extra). Verificar que Railway lo banca en tu plan.
2. **Test en vivo de cada collector**: Hacer `POST /api/v1/index/run` y revisar cuáles devuelven datos.
3. **Selectores CSS de Playwright**: Los selectores son estimaciones basadas en estructura típica VTEX/React. Puede haber que ajustar después de ver el HTML real.
4. **API key de Precios Claros**: La API key pública incluida puede haberse rotado. Si `supermercados` falla con 401/403, hay que buscar la key actualizada.

### Plan B si Railway no banca Chromium
Mover los Playwright collectors a un **GitHub Actions job** separado que:
1. Corre en schedule (diario)
2. Ejecuta los collectors con Playwright
3. POST los resultados a la API de Railway

Esto separa la infra pesada (Chromium) del servidor liviano (FastAPI).

## Cómo aplicar los cambios

### Opción 1: Copiar archivos manualmente
Descargar la carpeta `R-V-Price-Monitor-updated` y copiar todo sobre tu repo local.

### Opción 2: Usar el script
```bash
cd /path/to/R-V-Price-Monitor
bash /path/to/R-V-Price-Monitor-updated/apply-changes.sh
```

### Después del push
```bash
git add -A
git commit -m "feat: rewrite collectors — Precios Claros API + Playwright"
git push origin main

# Railway auto-deploys, luego testar:
curl -X POST https://r-v-price-monitor-production.up.railway.app/api/v1/index/run
```
