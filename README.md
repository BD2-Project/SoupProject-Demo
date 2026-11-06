# SoupProject Demo

Demo dockerizada de **SoupDB**: gestor + cliente web **SoupChef** (SSR) listos
para usarse con un solo comando. Las imágenes están publicadas y son públicas
en GHCR.

## Servicios

| Servicio   | Imagen                                      | Puerto host | Qué hace |
|------------|---------------------------------------------|-------------|----------|
| `engine`   | `ghcr.io/BD2-Project/soupdb:0.6.1`         | `55432`     | Gestor SoupDB (protocolo binario v2) |
| `soupchef` | `ghcr.io/BD2-Project/soupchef:0.3.0`       | `8080`      | Cliente web SSR; el servidor Node habla TCP con el motor |
| `seed`     | `ghcr.io/BD2-Project/soupdb:0.6.1`         | —           | Siembra idempotente de datos de ejemplo y termina |
| `plugins`  | `python:3.12-slim`                          | —           | Instala `soupdb-inverted` (y extras) desde PyPI y termina |

## Prerrequisitos

- Docker con Compose v2.
- No hace falta `docker login`: los paquetes son públicos.
- Ambas imágenes son **multi-arch** (`linux/amd64` + `linux/arm64`): en Apple
  Silicon Docker descarga la variante **arm64 nativa**, sin emulación.

## Arrancar

```bash
docker compose pull
docker compose up -d
```

- Cliente web: <http://localhost:8080>
- Gestor (protocolo binario): `127.0.0.1:55432`

El arranque sigue este orden: `seed` → `engine` (healthy) → `soupchef`.
La primera vez se crean las tablas `accounts` y `lugares` con datos de ejemplo;
en arranques posteriores el seed detecta los datos y no hace nada.

## Verificación rápida

```bash
docker compose ps                 # engine/soupchef healthy; seed exited (0)
docker compose logs seed          # "seed: tablas accounts y lugares creadas"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/   # 200
```

## Datos de ejemplo

```sql
SELECT * FROM accounts;          -- (1, 100), (2, 200)
SELECT id, nombre FROM lugares;  -- Lima, Cusco, Arequipa
```

## Smoke test del gestor

Con el repositorio [`rsoup`](https://github.com/BD2-Project/rsoup) a mano:

```bash
cargo run --bin soup_tui -- --host 127.0.0.1 --port 55432 --scenario ping
```

El escenario `ping` abre una conexión TCP, hace heartbeat y sale con código 0.
Otros escenarios: `select`, `commit`, `rollback`, `error`, `spatial`,
`prepared`, `vector`.

Para la TUI interactiva:

```bash
cargo run --bin soup_tui
```

## Consultas de ejemplo

Desde el cliente web o con `soup_tui`:

```sql
CREATE TABLE papers (id INT PRIMARY KEY, titulo TEXT, pos POINT);
INSERT INTO papers VALUES (1, 'Bases de datos espaciales', POINT(-12.05, -77.04));
SELECT id, titulo FROM papers;
SELECT id, titulo FROM papers WHERE INTERSECTS(pos, POLYGON(...));
```

## Plugins

El servicio `plugins` instala los paquetes **desde PyPI** en el volumen
`plugin-site` antes de que arranque el motor. El motor los descubre solo por
sus entry points `soupdb.plugins`.

- Por defecto se instala **`soupdb-inverted`** (full-text, ligero).
- El **seed activa** el plugin en el primer arranque: registra `INVERTED` con
  `storage_root=/app/data/plugins/inverted`, crea la tabla `docs`, siembra tres
  filas y ejecuta `CREATE INDEX idx_docs ... USING INVERTED`. Ese `CREATE INDEX`
  persiste la configuración en `SysPlugins`, así que el motor la reaplica solo
  cada vez que abre la base (no hace falta reconfigurar nada).
- Verificación:

  ```bash
  docker compose logs plugins   # lista el entry point INVERTED
  docker compose logs seed      # "plugin INVERTED activado e indice idx_docs creado"
  ```

Búsqueda lista para probar desde el cliente web:

```sql
SELECT id, SCORE() FROM docs WHERE SEARCH(contenido, 'espaciales') USING INVERTED LIMIT 10;
```

### Vectorial (opcional, activación manual)

Se instala con:

```bash
SOUPDB_EXTRA_PLUGINS=soupdb-vector docker compose up -d
```

Sus entry points (`IVF`, `HNSW`) quedan visibles, pero **no se activan solos**:
crear un índice vectorial requiere un codebook/perfil entrenado sobre un dataset
multimedia. Ese flujo queda fuera de la demo; ver `docs/plugins.md` y
`docs/vectores.md` del repositorio del gestor.

## Persistencia y reinicio

Los datos viven en el volumen `engine-data`. Para empezar de cero:

```bash
docker compose down -v
docker compose up -d
```

## Variables de entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DRIVER_PORT` | `55432` | Puerto host del gestor |
| `SOUPCHEF_PORT` | `8080` | Puerto host del cliente web |
| `SOUPDB_WIRE_VERSION` | `2` | Versión del protocolo que usa el cliente |
| `SOUPDB_TIMEOUT_MS` | `15000` | Timeout de conexión del cliente |
| `MAX_CONNECTIONS` | `100` | Conexiones simultáneas del gestor |
| `PAGE_SIZE` | `4096` | Tamaño de página del motor |
| `BUFFER_POOL_SIZE` | `1024` | Páginas en el buffer pool |

## Estado de las imágenes

- `ghcr.io/BD2-Project/soupdb:0.6.1` — gestor; pin explícito por reproducibilidad.
  Manifiesto multi-arch (`linux/amd64` + `linux/arm64`); `latest` también se
  publica en cada release `v*`.
- `ghcr.io/BD2-Project/soupchef:0.3.0` — cliente SSR con driver del protocolo
  v1.1 en el servidor; multi-arch (`linux/amd64` + `linux/arm64`).
