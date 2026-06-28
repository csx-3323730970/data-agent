"""Initialize the sample PostgreSQL database with sales data.

Requires PostgreSQL running locally with:
  PG_HOST=localhost PG_PORT=5432 PG_USER=postgres PG_PASSWORD=postgres PG_DATABASE=data_agent

Or set environment variables before running.
"""

import os
import sys
import random
import asyncio
import asyncpg

random.seed(42)

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = int(os.environ.get("PG_PORT", "5432"))
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "postgres")
PG_DATABASE = os.environ.get("PG_DATABASE", "data_agent")


async def main():
    # Connect to default 'postgres' database first to create ours
    sys_conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASSWORD, database="postgres"
    )

    # Drop and recreate
    await sys_conn.execute(f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{PG_DATABASE}' AND pid <> pg_backend_pid()
    """)
    await sys_conn.execute(f"DROP DATABASE IF EXISTS {PG_DATABASE}")
    await sys_conn.execute(f"CREATE DATABASE {PG_DATABASE}")
    await sys_conn.close()

    conn = await asyncpg.connect(
        host=PG_HOST, port=PG_PORT, user=PG_USER,
        password=PG_PASSWORD, database=PG_DATABASE
    )

    # ── Products ──
    await conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit_price NUMERIC(10,2) NOT NULL
        )
    """)
    products = [
        (1, "MacBook Pro 14", "电子产品", 14999),
        (2, "iPhone 16 Pro", "电子产品", 8999),
        (3, "AirPods Pro", "电子产品", 1899),
        (4, "办公椅 Pro", "办公家具", 2499),
        (5, "升降桌", "办公家具", 3999),
        (6, "机械键盘 K1", "外设", 699),
        (7, "4K 显示器", "电子产品", 3499),
        (8, "人体工学鼠标", "外设", 399),
        (9, "显示器支架", "办公家具", 599),
        (10, "笔记本支架", "办公家具", 299),
    ]
    await conn.executemany(
        "INSERT INTO products VALUES ($1, $2, $3, $4)", products
    )

    # ── Regions ──
    await conn.execute("""
        CREATE TABLE regions (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    regions = [(1, "华东"), (2, "华南"), (3, "华北"), (4, "西南"), (5, "华中")]
    await conn.executemany("INSERT INTO regions VALUES ($1, $2)", regions)

    # ── Sales (500 rows) ──
    await conn.execute("""
        CREATE TABLE sales (
            id SERIAL PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id),
            region_id INTEGER NOT NULL REFERENCES regions(id),
            quantity INTEGER NOT NULL,
            sale_date DATE NOT NULL
        )
    """)
    sales_rows = []
    for i in range(1, 501):
        pid = random.choice(products)[0]
        rid = random.choice(regions)[0]
        qty = random.randint(1, 30)
        month = random.randint(1, 6)
        day = random.randint(1, 28)
        sales_rows.append((pid, rid, qty, f"2026-{month:02d}-{day:02d}"))
    await conn.executemany(
        "INSERT INTO sales (product_id, region_id, quantity, sale_date) VALUES ($1, $2, $3, $4)",
        sales_rows
    )

    # ── User Actions (1000 rows) ──
    await conn.execute("""
        CREATE TABLE user_actions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            action_type TEXT NOT NULL,
            page TEXT,
            duration_seconds NUMERIC(6,1),
            action_date DATE NOT NULL
        )
    """)
    action_types = ["page_view", "click", "purchase", "add_cart", "search"]
    pages = ["首页", "产品详情", "购物车", "搜索页", "个人中心"]
    ua_rows = []
    for i in range(1, 1001):
        uid = random.randint(1, 50)
        atype = random.choice(action_types)
        page = random.choice(pages)
        duration = round(random.uniform(5, 300), 1) if atype in ("page_view", "search") else None
        month = random.randint(1, 6)
        day = random.randint(1, 28)
        ua_rows.append((uid, atype, page, duration, f"2026-{month:02d}-{day:02d}"))
    await conn.executemany(
        "INSERT INTO user_actions (user_id, action_type, page, duration_seconds, action_date) VALUES ($1, $2, $3, $4, $5)",
        ua_rows
    )

    await conn.close()

    print(f"PostgreSQL 数据库已初始化: {PG_HOST}:{PG_PORT}/{PG_DATABASE}")
    print(f"  products:      {len(products)} 行")
    print(f"  regions:       {len(regions)} 行")
    print(f"  sales:         {len(sales_rows)} 行")
    print(f"  user_actions:  {len(ua_rows)} 行")


if __name__ == "__main__":
    asyncio.run(main())
