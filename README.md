# R&V IPC — Proxy de Inflación Argentina

Índice de precios al consumidor proxy con frecuencia **semanal**, basado en scraping de precios online y empalme con el IPC oficial del INDEC.

## Qué es

Un sistema que recolecta precios de fuentes públicas online (supermercados, estaciones de servicio, farmacias, delivery, etc.), los pondera según la metodología oficial del INDEC (Metodología N°32), y genera un índice de inflación con mayor frecuencia que el dato mensual del INDEC.

## Metodología

- **Fórmula**: Laspeyres con media geométrica para índices elementales
- **Ponderadores**: GBA del Anexo II, Metodología INDEC N°32 (ENGHo 2004/05, actualizado a dic 2016)
- **Empalme**: Arranca desde el último IPC oficial (feb 2026 = 10.714,63) y aplica variaciones propias
- **Cobertura**: 10 de 12 divisiones COICOP (64.5% del peso GBA)
- **Imputación de faltantes**: Misma metodología INDEC sección 7.1

## Stack técnico

```
Python 3.12 + FastAPI + PostgreSQL 16
httpx + BeautifulSoup (scraping)
APScheduler (automatización)
React + Recharts (dashboard)
Docker Compose (desarrollo local)
```

## Quick start

```bash
# Levantar DB y app
docker compose up -d

# Crear tablas
docker compose exec app python -c "from storage.models import create_tables; create_tables('postgresql+psycopg2://rv_ipc:rv_ipc_dev@db:5432/rv_ipc')"

# Correr tests
docker compose exec app python -m pytest tests/ -v

# Ver API docs
open http://localhost:8000/docs
```

## Endpoints principales

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/v1/index/nivel-general` | Último índice R&V IPC |
| `GET /api/v1/index/divisiones` | Desglose por 12 divisiones COICOP |
| `GET /api/v1/index/cobertura` | Stats de cobertura |
| `POST /api/v1/index/run` | Trigger manual del pipeline |
| `GET /api/v1/prices/collect-now?collector_id=jumbo` | Ejecutar un collector |
| `GET /api/v1/status/collectors` | Estado de los collectors |

## Collectors

| Collector | Fuente | División COICOP | Método |
|-----------|--------|-----------------|--------|
| `jumbo` | Jumbo (VTEX API) | 01, 02, 05, 12 | API JSON |
| `combustibles` | Sec. Energía | 07 | API datos.gob.ar |
| `dolar` | ArgentinaDatos | — (auxiliar) | API pública |
| `pedidosya` | PedidosYa | 11 | HTML scraping |
| `farmacity` | Farmacity | 06 | HTML scraping |

## Estructura

```
rv-ipc/
├── config/          # Canasta COICOP, ponderadores, datos empalme
├── collectors/      # Módulos de scraping por fuente
├── engine/          # Motor de cálculo (Laspeyres, imputación)
├── storage/         # SQLAlchemy models, DB
├── api/             # FastAPI REST API
├── scheduler/       # Automatización de corridas
└── tests/           # 41 tests passing
```

## Pipeline de cálculo

```
Collectors → Precios crudos
    ↓
Media geométrica por variedad COICOP
    ↓
Variaciones % vs período anterior
    ↓
Laspeyres con pesos GBA
    ↓
Empalme con IPC oficial
    ↓
Persistencia en PostgreSQL
    ↓
API REST → Dashboard React
```

## Próximos pasos

1. Ajustar selectores CSS de cada collector contra sitios reales
2. Primer corrida real del pipeline
3. Conectar dashboard React a la API
4. Deploy Railway (backend) + Vercel (frontend)
5. Fase 2: módulo econométrico de proyección

---

*R&V IPC — Pipeline Capital*
