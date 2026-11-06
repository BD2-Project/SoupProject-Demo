# SoupProject Demo

Demo mínima del gestor **SoupDB** usando la imagen publicada en GHCR.

## Prerrequisitos

- Docker con Compose v2.
- Acceso al paquete GHCR. **El paquete es privado**, así que hay que autenticarse
  una vez:

  ```bash
  echo "$GITHUB_TOKEN" | docker login ghcr.io -u <tu-usuario> --password-stdin
  ```

  > Alternativa para la demo pública: hacer visible el paquete
  > `ghcr.io/bd2-project/soupdb` desde Settings de la organización (Opción A del
  > Plan A). Mientras siga privado, el `docker login` es obligatorio.

## Arrancar

```bash
docker compose pull
docker compose up -d
```

El gestor queda escuchando en `127.0.0.1:55432` (protocolo binario de SoupDB).
Los datos persisten en el volumen `engine-data`.

## Smoke test

Con el repositorio `rsoup` a mano:

```bash
cargo run --bin soup_tui -- --scenario ping
```

El escenario `ping` abre una conexión TCP, hace heartbeat y sale con código 0.
Escenarios disponibles: `ping`, `select`, `commit`, `rollback`, `error`,
`spatial`, `prepared`, `vector` (los de v1.1 requieren `RSOUP_E2E_V11=true`).

## Consultas de ejemplo

Una vez conectado con `soup_tui` (TUI interactiva) o con el cliente SSR:

```sql
CREATE TABLE papers (id INT PRIMARY KEY, titulo TEXT, pos POINT);
INSERT INTO papers VALUES (1, 'Bases de datos espaciales', POINT(-12.05, -77.04));
SELECT id, titulo FROM papers WHERE INTERSECTS(pos, POLYGON(...));
SELECT id, titulo FROM papers WHERE SEARCH(titulo, 'espaciales') USING INVERTED LIMIT 10;
```

## Plugins (opcional)

Para habilitar full-text/vectorial, colocar los wheels en `./plugins` y arrancar
con `SOUPDB_PLUGINS=1`:

```bash
mkdir -p plugins
# copiar soupdb_inverted-*.whl y/o soupdb_vector-*.whl
SOUPDB_PLUGINS=1 docker compose up -d
```

## Estado

- `engine`: imagen `ghcr.io/BD2-Project/soupdb:v0.6.1` (pin explícito).
- `soupchef`: pendiente de la imagen SSR (Plan C); el servicio está comentado en
  el compose.
