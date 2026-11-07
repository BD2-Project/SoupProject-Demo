#!/usr/bin/env python3
"""Carga datos de prueba en una demo SoupDB en ejecución.

Uso:
    pip install soupdb                     # solo el core (protocolo)
    python scripts/load_demo_data.py       # productos=120, ventas=600, estaciones=80
    python scripts/load_demo_data.py --products 5000 --sales 20000 --stations 2000
    python scripts/load_demo_data.py --docs 200   # suma documentos al full-text

Habla el protocolo binario v2 contra el gestor (127.0.0.1:55432 por defecto).
Es idempotente: si una tabla ya tiene filas, no la vuelve a sembrar.
"""

from __future__ import annotations

import argparse
import random
import socket

from engine.transactions import protocol as proto

CATEGORIAS = ["electronica", "hogar", "deporte", "libros", "juguetes"]
PALABRAS = [
    "bases", "datos", "indice", "invertido", "busqueda", "vector", "espacial",
    "motor", "consulta", "plan", "pagina", "disco", "hash", "arbol", "texto",
]


class Client:
    def __init__(self, host: str, port: int) -> None:
        self.sock = socket.create_connection((host, port), timeout=60)

    def _simple(self, frame: bytes, expected: int) -> None:
        self.sock.sendall(frame)
        _version, opcode, payload = proto.recv_frame_versioned(self.sock)
        if opcode == proto.OP_ERROR:
            code, message = proto.decode_error(payload)
            raise RuntimeError(f"[{code}] {message}")
        if opcode != expected:
            raise RuntimeError(f"opcode inesperado {opcode}")

    def begin(self) -> None:
        self._simple(proto.encode_frame(proto.OP_BEGIN), proto.OP_OK)

    def commit(self) -> None:
        self._simple(proto.encode_frame(proto.OP_COMMIT), proto.OP_OK)

    def query(self, sql: str):
        self.sock.sendall(proto.encode_frame(proto.OP_QUERY, proto.encode_query(sql)))
        version, opcode, payload = proto.recv_frame_versioned(self.sock)
        if opcode == proto.OP_ERROR:
            code, message = proto.decode_error(payload)
            raise RuntimeError(f"[{code}] {message}\nSQL: {sql[:160]}")
        if opcode == proto.OP_RESULT:
            return proto.decode_resultset(payload, version=version)
        return proto.decode_ok(payload)

    def close(self) -> None:
        self.sock.close()


def tables(client: Client) -> set[str]:
    return {row[0] for row in client.query("SELECT table_name FROM SysTables").rows}


def row_count(client: Client, table: str) -> int:
    return client.query(f"SELECT COUNT(*) FROM {table}").rows[0][0]


def indexes(client: Client) -> set[str]:
    return {row[0] for row in client.query("SELECT index_name FROM SysIndexes").rows}


def batched_insert(client: Client, sql_prefix: str, rows: list[str], size: int = 200) -> None:
    client.begin()
    try:
        for start in range(0, len(rows), size):
            chunk = rows[start : start + size]
            client.query(sql_prefix + ",".join(chunk))
    except BaseException:
        raise
    else:
        client.commit()


def seed_productos(client: Client, count: int, rng: random.Random) -> None:
    if "productos" not in tables(client):
        client.query(
            "CREATE TABLE productos (id INT PRIMARY KEY, nombre VARCHAR(40), "
            "precio FLOAT, stock INT, categoria TEXT)"
        )
    if row_count(client, "productos") > 0:
        print("productos: ya tiene filas; se omite")
        return
    rows = [
        f"({i}, 'Producto {i:04d}', {round(rng.uniform(5, 500), 2)}, "
        f"{rng.randint(0, 500)}, '{rng.choice(CATEGORIAS)}')"
        for i in range(1, count + 1)
    ]
    batched_insert(client, "INSERT INTO productos (id, nombre, precio, stock, categoria) VALUES ", rows)
    if "idx_prod_nombre" not in indexes(client):
        client.query("CREATE INDEX idx_prod_nombre ON productos (nombre) TYPE HASH")
    print(f"productos: {count} filas")


def seed_ventas(client: Client, count: int, productos: int, rng: random.Random) -> None:
    if "ventas" not in tables(client):
        client.query(
            "CREATE TABLE ventas (id INT PRIMARY KEY, producto_id INT, cantidad INT, total FLOAT)"
        )
    if row_count(client, "ventas") > 0:
        print("ventas: ya tiene filas; se omite")
        return
    rows = []
    for i in range(1, count + 1):
        cantidad = rng.randint(1, 5)
        rows.append(
            f"({i}, {rng.randint(1, productos)}, {cantidad}, {round(cantidad * rng.uniform(5, 500), 2)})"
        )
    batched_insert(client, "INSERT INTO ventas (id, producto_id, cantidad, total) VALUES ", rows)
    if "idx_ventas_prod" not in indexes(client):
        client.query("CREATE INDEX idx_ventas_prod ON ventas (producto_id) TYPE BTREE")
    print(f"ventas: {count} filas")


def seed_estaciones(client: Client, count: int, rng: random.Random) -> None:
    if "estaciones" not in tables(client):
        client.query(
            "CREATE TABLE estaciones (id INT PRIMARY KEY, nombre TEXT, ubicacion POINT)"
        )
    if row_count(client, "estaciones") > 0:
        print("estaciones: ya tiene filas; se omite")
        return
    rows = [
        f"({i}, 'Estacion {i:04d}', POINT({round(rng.uniform(-12.20, -11.80), 5)}, "
        f"{round(rng.uniform(-77.20, -76.80), 5)}))"
        for i in range(1, count + 1)
    ]
    batched_insert(client, "INSERT INTO estaciones (id, nombre, ubicacion) VALUES ", rows)
    if "idx_estaciones_rtree" not in indexes(client):
        client.query("CREATE INDEX idx_estaciones_rtree ON estaciones (ubicacion) TYPE RTREE")
    print(f"estaciones: {count} filas")


def seed_docs(client: Client, count: int, rng: random.Random) -> None:
    if "docs" not in tables(client):
        print("docs: no existe (la crea el seed de la demo); se omite")
        return
    max_id = client.query("SELECT MAX(id) FROM docs").rows[0][0] or 0
    rows = [
        f"({max_id + i}, '{' '.join(rng.choices(PALABRAS, k=12))}')"
        for i in range(1, count + 1)
    ]
    batched_insert(client, "INSERT INTO docs (id, contenido) VALUES ", rows)
    print(f"docs: +{count} filas (índice invertido actualizado)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=55432)
    parser.add_argument("--products", type=int, default=120)
    parser.add_argument("--sales", type=int, default=600)
    parser.add_argument("--stations", type=int, default=80)
    parser.add_argument("--docs", type=int, default=0)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    client = Client(args.host, args.port)
    try:
        print("conectado:", client.query("SELECT COUNT(*) FROM SysTables").rows[0][0], "tablas de sistema")
        seed_productos(client, args.products, rng)
        seed_ventas(client, args.sales, args.products, rng)
        seed_estaciones(client, args.stations, rng)
        if args.docs:
            seed_docs(client, args.docs, rng)

        print(
            "totales:",
            {
                "productos": row_count(client, "productos"),
                "ventas": row_count(client, "ventas"),
                "estaciones": row_count(client, "estaciones"),
            },
        )
        print("\nConsultas de prueba:")
        print("  SELECT categoria, COUNT(*), AVG(precio) FROM productos GROUP BY categoria;")
        print("  SELECT producto_id, COUNT(*) AS n, SUM(total) FROM ventas GROUP BY producto_id ORDER BY n DESC LIMIT 10;")
        print("  SELECT * FROM productos WHERE nombre = 'Producto 0042';")
        print("  SELECT nombre FROM estaciones WHERE INTERSECTS(ubicacion, POLYGON((-12.1,-77.1),(-12.1,-77.0),(-12.0,-77.0),(-12.0,-77.1)));")
        print("  EXPLAIN ANALYZE (FORMAT JSON) SELECT * FROM ventas WHERE producto_id = 42;")
    finally:
        client.close()


if __name__ == "__main__":
    main()
