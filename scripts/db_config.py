"""数据库连接参数：优先读环境变量，缺省值对应本机开发环境（PG 15 便携版，端口 5433）。"""
import os
from urllib.parse import urlparse

_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres123@localhost:5433/yunnan_mine_gis")
_u = urlparse(_url)

DB_CONFIG = {
    "host": _u.hostname or "localhost",
    "port": _u.port or 5433,
    "user": _u.username or "postgres",
    "password": _u.password or "postgres123",
    "dbname": (_u.path or "/yunnan_mine_gis").lstrip("/"),
}
