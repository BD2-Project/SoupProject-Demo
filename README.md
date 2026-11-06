# SoupProject Demo

Demo dockerizada de **SoupDB**: gestor + cliente web **SoupChef** (SSR) listos
para usarse con un solo comando. Las imágenes están publicadas y son públicas
en GHCR.

## Servicios

| Servicio   | Imagen                                      | Puerto host | Qué hace |
|------------|---------------------------------------------|-------------|----------|
| `engine`   | `ghcr.io/bd2-project/soupdb:0.7.1`         | `55432`     | Gestor SoupDB (protocolo binario v2) |
| `soupchef` | `ghcr.io/bd2-project/soupchef:0.3.0`       | `8080`      | Cliente web SSR; el servidor Node habla TCP con el motor |
| `seed`     | `ghcr.io/bd2-project/soupdb:0.7.1`         | —           | Siembra datos y activa INVERTED + IVF + HNSW |
| `plugins`  | `python:3.12-slim`                          | —           | Instala todos los plugins desde PyPI (`soupdb-inverted` + `soupdb-vector`) |
| `vector-dataset` | `python:3.12-slim`                    | —           | Genera 40 imágenes sintéticas y entrena el codebook (K=16) |

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

El arranque sigue este orden: `plugins` → `seed` → `engine` (healthy) → `soupchef`.
La primera vez se crean las tablas `accounts` y `lugares` con datos de ejemplo;
en arranques posteriores el seed detecta los datos y no hace nada.

### Con la extensión vectorial (IVF/HNSW)

```bash
export SOUPDB_EXTRA_PLUGINS=soupdb-vector
docker compose down -v      # opcional: empezar de cero
docker compose up -d
```

El servicio `plugins` instala `soupdb-vector` desde PyPI y el seed activa
`IVF`/`HNSW` automáticamente (misma configuración, requisito de v0.7.1).

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

Se instalan **todos los plugins por defecto**: `soupdb-inverted` (texto) y
`soupdb-vector` (IVF/HNSW). `SOUPDB_EXTRA_PLUGINS` permite sumar más paquetes.

El **seed activa** las extensiones por SQL en el primer arranque (idempotente):

```sql
CREATE EXTENSION inverted WITH (storage_root = '/app/data/plugins/inverted');
CREATE EXTENSION ivf  WITH (storage_root = '/app/data/plugins/vector',
  profiles = '{"img-v1": {"kind": "image", "root": "/app/data/vector-dataset/img",
                          "codebook": "/app/data/vector-dataset/codebook.npz"}}');
CREATE EXTENSION hnsw WITH (storage_root = '/app/data/plugins/vector', profiles = '...');
```

La configuración queda en `SysPlugins` y el motor la reaplica al abrir.

- **Texto**: `docs` + índice `idx_docs USING INVERTED`.
- **Vectorial**: el servicio `vector-dataset` genera 40 imágenes sintéticas,
  entrena un codebook K=16 y el seed crea `imagenes` con dos índices
  (`idx_img_ivf` y `idx_img_hnsw`).

Verificación:

```bash
docker compose logs plugins        # entry points: hnsw, inverted, ivf
docker compose logs vector-dataset # "40 imagenes sinteticas creadas"
docker compose logs seed           # indices de texto y vectoriales creados
```

Consultas listas para probar desde el cliente web:

```sql
-- texto (full-text)
SELECT id, SCORE() AS score FROM docs
WHERE SEARCH(contenido, 'espaciales') USING INVERTED LIMIT 10;

-- vectorial (similitud de imágenes; las rutas son relativas al dataset)
SELECT id, archivo, SCORE() AS score FROM imagenes
WHERE SEARCH(archivo, 'img_000.png') USING IVF WITH (metric = 'cosine', k = 5)
ORDER BY score DESC;

SELECT id, archivo, SCORE() AS score FROM imagenes
WHERE SEARCH(archivo, 'img_000.png') USING HNSW WITH (metric = 'cosine', k = 5)
ORDER BY score DESC;
```

Para usar un dataset real, monta tus imágenes/codebook en el volumen
`engine-data` (o un bind mount) y ajusta `root`/`codebook` en el `profiles` del
`CREATE EXTENSION`; el resto del flujo es idéntico.

### Vectorial (IVF/HNSW)

El paquete `soupdb-vector` agrega los plugins **IVF** y **HNSW**. Para
instalarlo y activarlo:

```bash
export SOUPDB_EXTRA_PLUGINS=soupdb-vector
docker compose up -d --force-recreate plugins seed
docker compose restart engine   # el motor descubre los plugins al abrir
```

El seed detecta que el paquete está instalado y activa ambos con la **misma
configuración** (en v0.7.1, si IVF y HNSW están activos deben compartir el
vectorizer):

```sql
CREATE EXTENSION ivf WITH (storage_root = '/app/data/plugins/vector');
CREATE EXTENSION hnsw WITH (storage_root = '/app/data/plugins/vector');
```

Verificación:

```bash
docker compose logs seed   # "seed: extensiones vectoriales IVF/HNSW activadas"
```

```sql
SELECT plugin_name FROM SysPlugins;   -- INVERTED, IVF, HNSW
```

> La activación deja las extensiones listas, pero **crear un índice vectorial
> requiere un perfil multimedia** (`profiles`) con un `codebook.npz` y el
> dataset de imágenes/audio montado en el contenedor. Ese flujo no viene
> incluido en la demo. Para configurarlo (desde `soupdb-vector 0.1.1`):
>
> ```sql
> CREATE EXTENSION ivf WITH (
>   storage_root = '/app/data/plugins/vector',
>   profiles = '{"img-v1": {"kind": "image", "root": "/datasets/img", "codebook": "/codebooks/img.npz"}}'
> );
> CREATE EXTENSION hnsw WITH (
>   storage_root = '/app/data/plugins/vector',
>   profiles = '{"img-v1": {"kind": "image", "root": "/datasets/img", "codebook": "/codebooks/img.npz"}}'
> );
> ```
>
> Ambos deben repetir **exactamente** la misma configuración. Como el seed no
> pisa una extensión ya activa, esta configuración persiste entre arranques.
> Ver `docs/plugins.md` y `docs/sql_texto_multimedia.md` del repo del gestor.

## Persistencia y reinicio

Los datos viven en el volumen `engine-data` y los plugins instalados en
`plugin-site`. Para empezar de cero:

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

- `ghcr.io/bd2-project/soupdb:0.7.1` — gestor; pin explícito por
  reproducibilidad. Manifiesto multi-arch (`linux/amd64` + `linux/arm64`);
  `latest` también se publica en cada release `v*`. Incluye el fix de v0.7.1:
  `CREATE EXTENSION ivf WITH (storage_root = ...)` ya no choca con los plugins
  vectoriales solo descubiertos, y `profiles` acepta JSON.
- `ghcr.io/bd2-project/soupchef:0.3.0` — cliente SSR con driver del protocolo
  v1.1 en el servidor; multi-arch (`linux/amd64` + `linux/arm64`).
