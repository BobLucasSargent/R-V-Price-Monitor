# R&V IPC — Guía de Deploy

## Cómo funciona la automatización

El sistema tiene 3 ciclos automáticos:

| Frecuencia | Cuándo | Qué hace |
|---|---|---|
| **Diaria** | 6am, 12pm, 8pm | Collectors scrapeán precios de todas las fuentes |
| **Semanal** | Lunes 7am | Calcula índice semanal R&V IPC con todos los precios de la semana |
| **Mensual** | Día 1, 8am | Calcula índice mensual + compara con dato INDEC cuando sale |

Una vez deployadeo, **no tenés que hacer nada**. El scheduler corre solo y los datos se van acumulando en la DB.

---

## Opción recomendada: Railway (backend) + Vercel (dashboard)

### Costo estimado: ~$5-10 USD/mes
- Railway: ~$5/mes (backend + PostgreSQL)
- Vercel: gratis (dashboard React)

---

## Paso 1: Deploy del backend en Railway

### 1.1 Crear cuenta
1. Ir a [railway.app](https://railway.app)
2. Registrarse con GitHub

### 1.2 Crear el proyecto
1. "New Project" → "Deploy from GitHub repo"
2. Conectar tu repo de GitHub donde subiste `rv-ipc/`
3. Railway detecta el Dockerfile automáticamente

### 1.3 Agregar PostgreSQL
1. En el proyecto, click "New" → "Database" → "PostgreSQL"
2. Railway crea la DB y genera la variable `DATABASE_URL` automáticamente

### 1.4 Configurar variables de entorno
En el servicio de la app, ir a "Variables" y agregar:

```
DATABASE_URL_SYNC=postgresql+psycopg2://... (copiar de la DB de Railway, cambiar asyncpg por psycopg2)
LOG_LEVEL=INFO
```

Railway ya inyecta `DATABASE_URL` automáticamente.

### 1.5 Deploy
Railway hace deploy automático con cada push a GitHub.

### 1.6 Crear las tablas
En Railway → tu servicio → "Shell":
```bash
python -c "from storage.models import create_tables; import os; create_tables(os.environ['DATABASE_URL_SYNC'])"
```

### 1.7 Verificar
Tu API queda en: `https://tu-proyecto.up.railway.app/docs`

---

## Paso 2: Lanzar el scheduler

El scheduler necesita correr como un **proceso separado** del API.

### En Railway: agregar un segundo servicio
1. En tu proyecto → "New" → "Service" → mismo repo
2. Cambiar el "Start Command" a:
```
python -m scheduler.daily
```
3. Esto corre el APScheduler 24/7

### Alternativa: usar Railway Cron Jobs
Si preferís no tener un proceso corriendo 24/7:
1. Railway soporta Cron Jobs
2. Crear un cron job con: `python -c "from engine.pipeline import run_pipeline; print(run_pipeline())"`
3. Configurar schedule: `0 6,12,20 * * *` (diario) y `0 7 * * 1` (semanal lunes)

---

## Paso 3: Deploy del dashboard en Vercel

### 3.1 Crear proyecto React
```bash
npm create vite@latest rv-ipc-dashboard -- --template react
cd rv-ipc-dashboard
npm install recharts
```

### 3.2 Copiar el dashboard
Copiar el archivo `ipc-dashboard.jsx` como `src/App.jsx`

### 3.3 Conectar con la API
En el dashboard, reemplazar los datos hardcodeados por fetch:
```javascript
// En vez de const RAW = {...datos...}
const [data, setData] = useState(null);
useEffect(() => {
  fetch('https://tu-proyecto.up.railway.app/api/v1/index/nivel-general')
    .then(r => r.json())
    .then(setData);
}, []);
```

### 3.4 Deploy en Vercel
1. Push a GitHub
2. Ir a [vercel.com](https://vercel.com)
3. "Import Project" → seleccionar el repo
4. Vercel detecta Vite automáticamente
5. Deploy automático

Dashboard queda en: `https://rv-ipc-dashboard.vercel.app`

---

## Paso 4: Primera corrida manual

Una vez todo deployadeo, trigger manual del pipeline:

```bash
# Desde la shell de Railway, o via API:
curl -X POST https://tu-proyecto.up.railway.app/api/v1/index/run?periodo=diario
```

O desde el navegador: `https://tu-proyecto.up.railway.app/api/v1/index/run?periodo=diario`

---

## Alternativa más simple: todo en Railway

Si no querés Vercel por separado, podés servir el dashboard directamente desde FastAPI como archivos estáticos:

```python
# En api/main.py agregar:
from fastapi.staticfiles import StaticFiles
app.mount("/app", StaticFiles(directory="static", html=True), name="static")
```

Build del React → copiar `dist/` a `static/` → todo en un solo servicio.

---

## Monitoreo

### Ver logs en Railway
Railway tiene logs en tiempo real en el dashboard.

### API de status
- `GET /health` — healthcheck
- `GET /api/v1/status/collectors` — estado de todos los collectors
- `GET /api/v1/index/cobertura` — cobertura de la canasta

### Comparación con INDEC
Cuando el INDEC publica el dato mensual (generalmente día 12-15 del mes siguiente):
1. Actualizar `config/ipc_oficial.py` con el nuevo dato
2. El pipeline automáticamente compara R&V vs INDEC
3. La tabla `comparacion_indec` en la DB guarda el histórico

---

## Resumen de URLs finales

| Qué | URL |
|---|---|
| API docs | `https://rv-ipc.up.railway.app/docs` |
| Dashboard | `https://rv-ipc-dashboard.vercel.app` |
| Healthcheck | `https://rv-ipc.up.railway.app/health` |
| Trigger manual | `POST /api/v1/index/run?periodo=semanal` |
| Ver collectors | `GET /api/v1/status/collectors` |
| Ejecutar 1 collector | `GET /api/v1/prices/collect-now?collector_id=jumbo` |
