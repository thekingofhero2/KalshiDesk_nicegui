# -*- coding: utf-8 -*-
"""本地 DuckDB 存储：所有 Kalshi 数据增量落库，界面统一从库中读取。

设计：
- 账户余额：每次同步插入一条快照（balance_snapshots），界面取最新一条并展示同步时间；
- 持仓 / 子账户余额：按主键 upsert，本次快照里已不存在的记录会被删除；
- 订单 / 成交 / 结算 / 转账：按业务主键 upsert，只新增或更新，不删除历史。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Optional
from uuid import uuid4

import duckdb

from .store import DATA_DIR

DB_PATH = DATA_DIR / "kalshi.duckdb"

_lock = threading.RLock()
_conn: Optional[duckdb.DuckDBPyConnection] = None

_SCHEMA = """
CREATE TABLE IF NOT EXISTS balance_snapshots (
    env VARCHAR, key_id VARCHAR, ts TIMESTAMP,
    available DOUBLE, portfolio_value DOUBLE, payout DOUBLE, shards VARCHAR,
    PRIMARY KEY (env, key_id, ts)
);
CREATE TABLE IF NOT EXISTS positions (
    env VARCHAR, ticker VARCHAR, position DOUBLE, yes_qty DOUBLE, no_qty DOUBLE,
    exposure DOUBLE, realized_pnl DOUBLE, fees DOUBLE, total_traded DOUBLE,
    resting INTEGER, exchange_index INTEGER, updated_ts VARCHAR,
    PRIMARY KEY (env, ticker)
);
CREATE TABLE IF NOT EXISTS orders (
    env VARCHAR, order_id VARCHAR, client_order_id VARCHAR, ticker VARCHAR,
    side VARCHAR, side_txt VARCHAR, price DOUBLE, count DOUBLE, filled DOUBLE,
    remaining DOUBLE, status VARCHAR, tif VARCHAR, fees DOUBLE,
    subaccount DOUBLE, exchange_index INTEGER, created VARCHAR, updated_ts TIMESTAMP,
    action VARCHAR, position_side VARCHAR,
    PRIMARY KEY (env, order_id)
);
CREATE TABLE IF NOT EXISTS fills (
    env VARCHAR, fill_id VARCHAR, order_id VARCHAR, ticker VARCHAR, side VARCHAR,
    action VARCHAR, price DOUBLE, count DOUBLE, is_taker BOOLEAN, fees DOUBLE,
    created VARCHAR, subaccount DOUBLE, exchange_index INTEGER,
    PRIMARY KEY (env, fill_id)
);
CREATE TABLE IF NOT EXISTS subaccount_balances (
    env VARCHAR, exchange_index INTEGER, subaccount DOUBLE, balance DOUBLE,
    updated_ts VARCHAR, updated_at TIMESTAMP,
    PRIMARY KEY (env, exchange_index, subaccount)
);
CREATE TABLE IF NOT EXISTS settlements (
    env VARCHAR, ticker VARCHAR, exchange_index INTEGER, event_ticker VARCHAR,
    market_result VARCHAR, yes_count DOUBLE, yes_cost DOUBLE, no_count DOUBLE,
    no_cost DOUBLE, revenue DOUBLE, fee DOUBLE, settled_time VARCHAR,
    PRIMARY KEY (env, ticker, exchange_index)
);
CREATE TABLE IF NOT EXISTS transfers (
    env VARCHAR, transfer_id VARCHAR, amount DOUBLE, from_subaccount DOUBLE,
    to_subaccount DOUBLE, created_ts VARCHAR,
    PRIMARY KEY (env, transfer_id)
);
-- 实时成交（WebSocket trade 频道订阅落库）
CREATE TABLE IF NOT EXISTS market_trades (
    env VARCHAR, trade_id VARCHAR, ticker VARCHAR,
    price DOUBLE, count DOUBLE, side VARCHAR, ts BIGINT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (env, trade_id)
);
CREATE INDEX IF NOT EXISTS idx_market_trades_ticker ON market_trades(env, ticker, ts);
-- Perps（Kalshi Invest）实时成交：独立 margin WS 频道，与预测市场分开存
CREATE TABLE IF NOT EXISTS perps_trades (
    env VARCHAR, trade_id VARCHAR, ticker VARCHAR,
    price DOUBLE, count DOUBLE, side VARCHAR, ts BIGINT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (env, trade_id)
);
CREATE INDEX IF NOT EXISTS idx_perps_trades_ticker ON perps_trades(env, ticker, ts);
-- 市场目录（series 级）：几乎不变，只在用户手动刷新时才全量同步，
-- 打开下单框直接读本地库，避免每次都拉 1.5 万条 /series
CREATE TABLE IF NOT EXISTS series_catalog (
    env VARCHAR, ticker VARCHAR, title VARCHAR, category VARCHAR,
    frequency VARCHAR, updated_at TIMESTAMP,
    PRIMARY KEY (env, ticker)
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id VARCHAR PRIMARY KEY, env VARCHAR, username VARCHAR, body VARCHAR,
    image VARCHAR, created TIMESTAMP
);
-- CF Benchmarks 实时/日线行情 tick（Kalshi 代理转发 cfbenchmarks.com）
CREATE TABLE IF NOT EXISTS cfb_ticks (
    env        VARCHAR,
    index_id   VARCHAR,              -- BTCUSD_RTI / SOLUSD_RTI / ETHUSD_RR ...
    value      DOUBLE,
    time_ms    BIGINT,               -- CF server time 毫秒时间戳（用于去重主键）
    server_time VARCHAR,             -- CF 原始 ISO 字符串（留着调试）
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (env, index_id, time_ms)
);
CREATE INDEX IF NOT EXISTS idx_cfb_ticks_hist ON cfb_ticks(env, index_id, ingested_at);
-- 动量机器人：运行日志（每次扫描、下单、止盈都记一条）
CREATE TABLE IF NOT EXISTS mo_log (
    id VARCHAR PRIMARY KEY,
    env VARCHAR, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level VARCHAR, message VARCHAR, ticker VARCHAR,
    detail VARCHAR   -- JSON：direction / delta / buy_px / sell_px / order_id / error 等
);
-- 动量机器人：已完成的动量单（含状态：buy_placed / buy_filled / tp_placed / tp_filled / canceled / failed）
CREATE TABLE IF NOT EXISTS mo_trades (
    env VARCHAR, buy_order_id VARCHAR,
    ticker VARCHAR, direction VARCHAR,    -- yes / no
    series VARCHAR,                       -- 所属系列（如 KXBTC15M）；同系列互斥开单
    delta DOUBLE,                         -- 触发时的动量强度 Δ
    buy_px DOUBLE, buy_count INTEGER, buy_tif VARCHAR, buy_status VARCHAR,
    sell_order_id VARCHAR, sell_px DOUBLE, sell_status VARCHAR,
    state VARCHAR,                        -- buy_placed / buy_filled / tp_placed / tp_filled / canceled / failed
    pnl DOUBLE, fees DOUBLE,
    subaccount DOUBLE,
    created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (env, buy_order_id)
);
CREATE INDEX IF NOT EXISTS idx_mo_trades_ticker ON mo_trades(env, ticker, created_ts DESC);
"""

# 订单视图单独定义：依赖 orders.action / position_side 列，
# 旧库需要先 ALTER 补列再建视图，故不能放在 _SCHEMA 里一起执行。
_VIEW_SQL = """
CREATE OR REPLACE VIEW orders_view AS
SELECT
    o.env, o.order_id, o.client_order_id, o.ticker, o.side, o.action,
    o.position_side, o.side_txt, o.price, o.count, o.filled, o.remaining,
    o.status, o.tif, o.fees, o.subaccount, o.exchange_index, o.created, o.updated_ts,
    -- created_utc 必须显式转回 UTC 墙上时间：TIMESTAMPTZ 由 Python 读出时
    -- 会被转成本地时区（北京），导致 UTC 列显示成北京时间
    timezone('UTC', TRY_CAST(o.created AS TIMESTAMPTZ))               AS created_utc,
    timezone('America/New_York', TRY_CAST(o.created AS TIMESTAMPTZ))   AS created_et,
    timezone('Asia/Shanghai',    TRY_CAST(o.created AS TIMESTAMPTZ))   AS created_bj,
    s.market_result                                                   AS market_result,
    s.settled_time                                                    AS settled_time,
    CASE
        WHEN s.market_result IS NULL THEN NULL
        WHEN s.market_result NOT IN ('yes', 'no') THEN 'n/a'
        -- position_side 已由 api.orders() 按 side+action 还原成真实持仓方向
        -- （卖 YES = 买 NO），这里直接比较即可
        WHEN o.position_side = s.market_result THEN 'win'
        WHEN o.position_side IS NULL THEN NULL
        ELSE 'loss'
    END                                                               AS settle_result
FROM orders o
LEFT JOIN (
    SELECT env, ticker, MAX(market_result) AS market_result,
           MAX(settled_time) AS settled_time
    FROM settlements GROUP BY env, ticker
) s ON o.env = s.env AND o.ticker = s.ticker
"""


def init() -> None:
    """应用启动时调用：建立全局共享连接，后续所有线程复用同一连接（内部加锁串行化）。"""
    conn()


def _migrate(c: duckdb.DuckDBPyConnection) -> None:
    """旧库兼容迁移：补列 + 建视图。在首次建连接时执行一次。"""
    for stmt in (
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS action VARCHAR",
        "ALTER TABLE orders ADD COLUMN IF NOT EXISTS position_side VARCHAR",
    ):
        try:
            c.execute(stmt)
        except Exception:
            pass
    # 视图依赖上面两列，必须在 ALTER 之后创建
    try:
        c.execute(_VIEW_SQL)
    except Exception:
        pass
    # mo_trades 早期版本把 buy_order_id 单列作主键，与 upsert 的
    # ON CONFLICT (env, buy_order_id) 不匹配。这里补一个唯一索引；
    # 若因旧数据重复而失败，则重建该表（动量单记录无长期价值，可重建）。
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_mo_trades_env_order "
                  "ON mo_trades(env, buy_order_id)")
    except Exception:
        try:
            c.execute("DROP TABLE IF EXISTS mo_trades")
            c.execute(
                "CREATE TABLE mo_trades ("
                " env VARCHAR, buy_order_id VARCHAR,"
                " ticker VARCHAR, direction VARCHAR, series VARCHAR, delta DOUBLE,"
                " buy_px DOUBLE, buy_count INTEGER, buy_tif VARCHAR, buy_status VARCHAR,"
                " sell_order_id VARCHAR, sell_px DOUBLE, sell_status VARCHAR,"
                " state VARCHAR, pnl DOUBLE, fees DOUBLE, subaccount DOUBLE,"
                " created_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                " updated_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                " PRIMARY KEY (env, buy_order_id))")
            c.execute("CREATE INDEX IF NOT EXISTS idx_mo_trades_ticker "
                      "ON mo_trades(env, ticker, created_ts DESC)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_mo_trades_series "
                      "ON mo_trades(env, series, created_ts DESC)")
        except Exception:
            pass
    # 老库补 series 列（同系列互斥开单依赖它）
    try:
        c.execute("ALTER TABLE mo_trades ADD COLUMN IF NOT EXISTS series VARCHAR")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mo_trades_series "
                  "ON mo_trades(env, series, created_ts DESC)")
    except Exception:
        pass


def conn() -> duckdb.DuckDBPyConnection:
    global _conn
    with _lock:
        if _conn is None:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _conn = duckdb.connect(str(DB_PATH))
            _conn.execute(_SCHEMA)
            _migrate(_conn)     # 旧库补列 + 建 orders_view
        return _conn


def _exec(sql: str, params=None) -> None:
    with _lock:
        conn().execute(sql, params or [])


def _query(sql: str, params=None) -> list:
    with _lock:
        cur = conn().execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ================= 写入 =================
def save_balance(env: str, key_id: str, b: dict) -> None:
    if not b:
        return
    ts = datetime.now()
    shards = json.dumps(b.get("shards") or [], ensure_ascii=False)
    _exec(
        "INSERT OR REPLACE INTO balance_snapshots "
        "(env, key_id, ts, available, portfolio_value, payout, shards) VALUES (?,?,?,?,?,?,?)",
        [env, key_id, ts, b.get("available"), b.get("portfolio_value"),
         b.get("payout"), shards],
    )


def save_positions(env: str, rows: list) -> None:
    with _lock:
        c = conn()
        tickers = []
        for p in rows or []:
            tickers.append(p["ticker"])
            c.execute(
                "INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [env, p.get("ticker"), p.get("position"), p.get("yes_qty"),
                 p.get("no_qty"), p.get("exposure"), p.get("realized_pnl"),
                 p.get("fees"), p.get("total_traded"), int(p.get("resting") or 0),
                 p.get("exchange_index"), p.get("updated_ts")],
            )
        if tickers:
            marks = ",".join("?" * len(tickers))
            c.execute(f"DELETE FROM positions WHERE env=? AND ticker NOT IN ({marks})",
                      [env, *tickers])
        else:
            c.execute("DELETE FROM positions WHERE env=?", [env])


def save_orders(env: str, rows: list) -> None:
    if not rows:
        return
    now = datetime.now()
    with _lock:
        conn().executemany(
            "INSERT OR REPLACE INTO orders "
            "(env, order_id, client_order_id, ticker, side, side_txt, price, count, "
            " filled, remaining, status, tif, fees, subaccount, exchange_index, "
            " created, updated_ts, action, position_side) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [[env, o.get("order_id"), o.get("client_order_id"), o.get("ticker"),
              o.get("side"), o.get("side_txt"), o.get("price"), o.get("count"),
              o.get("filled"), o.get("remaining"), o.get("status"), o.get("tif"),
              o.get("fees"), o.get("subaccount"), o.get("exchange_index"),
              o.get("created"), now, o.get("action"), o.get("position_side")]
             for o in rows],
        )


def last_order_ts(env: str, status: Optional[str] = None,
                  ticker: Optional[str] = None) -> Optional[int]:
    """该查询范围内最晚订单创建时间（Unix 秒），作为增量拉取水位。"""
    sql = "SELECT created FROM orders WHERE env=? AND created IS NOT NULL"
    params: list = [env]
    if status:
        sql += " AND status=?"
        params.append(status)
    if ticker:
        sql += " AND ticker=?"
        params.append(ticker)
    sql += " ORDER BY created DESC LIMIT 50"
    values = []
    from datetime import timezone
    for row in _query(sql, params):
        raw = row.get("created")
        if raw is None or raw == "":
            continue
        try:
            if isinstance(raw, datetime):
                dt = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
                values.append(int(dt.timestamp()))
                continue
            if isinstance(raw, (int, float)):
                ts = float(raw)
            else:
                text = str(raw).strip()
                try:
                    ts = float(text)
                except ValueError:
                    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                    if not dt.tzinfo:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts = dt.timestamp()
            values.append(int(ts / 1000 if ts > 2e10 else ts))
        except (TypeError, ValueError, OverflowError):
            continue
    return max(values) if values else None


def last_fill_ts(env: str) -> Optional[int]:
    """该环境已存成交中，最晚成交时间的时间戳（秒，UTC）。"""
    rows = _query("SELECT created FROM fills WHERE env=? AND created IS NOT NULL "
                  "ORDER BY created DESC LIMIT 1", [env])
    if not rows:
        return None
    s = rows[0]["created"]
    if not s:
        return None
    try:
        import re as _re
        m = _re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", s)
        if m:
            from datetime import timezone
            y, mo, d, h, mi, se = (int(x) for x in m.groups())
            return int(datetime(y, mo, d, h, mi, se, tzinfo=timezone.utc).timestamp())
    except Exception:
        pass
    return None


def save_fills(env: str, rows: list) -> None:
    if not rows:
        return
    with _lock:
        conn().executemany(
            "INSERT OR REPLACE INTO fills VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [[env, f.get("fill_id"), f.get("order_id"), f.get("ticker"),
              f.get("side"), f.get("action"), f.get("price"), f.get("count"),
              f.get("is_taker"), f.get("fees"), f.get("created"),
              f.get("subaccount"), f.get("exchange_index")] for f in rows],
        )


def save_subaccounts(env: str, rows: list) -> None:
    now = datetime.now()
    with _lock:
        c = conn()
        c.execute("DELETE FROM subaccount_balances WHERE env=?", [env])
        if rows:
            c.executemany(
                "INSERT OR REPLACE INTO subaccount_balances VALUES (?,?,?,?,?,?)",
                [[env, s.get("exchange_index"), s.get("subaccount"),
                  s.get("balance"), s.get("updated_ts"), now] for s in rows],
            )


def save_settlements(env: str, rows: list) -> None:
    if not rows:
        return
    with _lock:
        conn().executemany(
            "INSERT OR REPLACE INTO settlements VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [[env, s.get("ticker"), s.get("exchange_index"), s.get("event_ticker"),
              s.get("market_result"), s.get("yes_count"), s.get("yes_cost"),
              s.get("no_count"), s.get("no_cost"), s.get("revenue"),
              s.get("fee"), s.get("settled_time")] for s in rows],
        )


def save_transfers(env: str, rows: list) -> None:
    if not rows:
        return
    with _lock:
        conn().executemany(
            "INSERT OR REPLACE INTO transfers VALUES (?,?,?,?,?,?)",
            [[env, r.get("transfer_id"), r.get("amount"), r.get("from_subaccount"),
              r.get("to_subaccount"), r.get("created_ts")] for r in rows],
        )


# ================= 实时成交（WebSocket trades） =================
def save_market_trades(env: str, rows: list) -> None:
    """批量写入实时成交（INSERT OR IGNORE 按 trade_id 去重）。"""
    if not rows:
        return
    with _lock:
        conn().executemany(
            "INSERT OR IGNORE INTO market_trades "
            "(env, trade_id, ticker, price, count, side, ts) VALUES (?,?,?,?,?,?,?)",
            [[env, r.get("trade_id"), r.get("ticker"), r.get("price"),
              r.get("count"), r.get("side"), r.get("ts")] for r in rows],
        )


def market_trades(env: str, ticker: str, limit: int = 200,
                  since_ts: Optional[int] = None) -> list:
    """某 ticker 的成交，按时间升序返回（画图用）。since_ts 用于增量拉取。"""
    sql = ("SELECT trade_id, ticker, price, count, side, ts FROM market_trades "
           "WHERE env=? AND ticker=?")
    params: list = [env, ticker]
    if since_ts is not None:
        sql += " AND ts > ?"
        params.append(int(since_ts))
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(int(limit))
    rows = _query(sql, params)
    rows.reverse()          # 转成时间升序
    return rows


def market_trades_range(env: str, ticker: str,
                        start_ts: Optional[int] = None,
                        end_ts: Optional[int] = None,
                        limit: int = 200000) -> list:
    """某 ticker 在指定时间区间内的全部成交，按时间升序返回（按秒聚合用）。"""
    sql = ("SELECT trade_id, ticker, price, count, side, ts FROM market_trades "
           "WHERE env=? AND ticker=?")
    params: list = [env, ticker]
    if start_ts is not None:
        sql += " AND ts >= ?"
        params.append(int(start_ts))
    if end_ts is not None:
        sql += " AND ts <= ?"
        params.append(int(end_ts))
    sql += " ORDER BY ts ASC LIMIT ?"
    params.append(int(limit))
    return _query(sql, params)


def market_trades_latest(env: str, tickers: Optional[list] = None) -> dict:
    """每个 ticker 最新一笔成交 → {ticker: row}，用于订阅列表展示。"""
    sql = ("SELECT ticker, price, count, side, ts FROM market_trades WHERE env=?")
    params: list = [env]
    if tickers:
        marks = ",".join("?" * len(tickers))
        sql += f" AND ticker IN ({marks})"
        params.extend(tickers)
    sql += " QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY ts DESC) = 1"
    try:
        rows = _query(sql, params)
    except Exception:
        # QUALIFY 在某些 DuckDB 版本写法受限，退化为 Python 侧取最新
        rows = []
        base = ("SELECT ticker, price, count, side, ts FROM market_trades WHERE env=?")
        p: list = [env]
        if tickers:
            marks = ",".join("?" * len(tickers))
            base += f" AND ticker IN ({marks})"
            p.extend(tickers)
        base += " ORDER BY ts DESC"
        seen = set()
        for r in _query(base, p):
            if r["ticker"] not in seen:
                seen.add(r["ticker"])
                rows.append(r)
    return {r["ticker"]: r for r in rows}


def market_trades_count(env: str) -> int:
    rows = _query("SELECT COUNT(*) AS n FROM market_trades WHERE env=?", [env])
    return int(rows[0]["n"]) if rows else 0


# ================= Perps（Kalshi Invest）实时成交 =================
def save_perps_trades(env: str, rows: list) -> None:
    """批量写入 perps 实时成交（按 trade_id 去重）。"""
    if not rows:
        return
    with _lock:
        conn().executemany(
            "INSERT OR IGNORE INTO perps_trades "
            "(env, trade_id, ticker, price, count, side, ts) VALUES (?,?,?,?,?,?,?)",
            [[env, r.get("trade_id"), r.get("ticker"), r.get("price"),
              r.get("count"), r.get("side"), r.get("ts")] for r in rows],
        )


def perps_trades_recent(env: str, ticker: str, limit: int = 20) -> list:
    """某 perps 市场最近的成交，按时间倒序返回（界面表格用）。"""
    rows = _query(
        "SELECT trade_id, ticker, price, count, side, ts FROM perps_trades "
        "WHERE env=? AND ticker=? ORDER BY ts DESC LIMIT ?",
        [env, ticker, int(limit)],
    )
    return rows


def perps_trades_since(env: str, ticker: str, since_ts: int,
                       limit: int = 3000) -> list:
    """某 perps 市场在 since_ts 之后的成交，按时间正序返回（画价差图用）。"""
    rows = _query(
        "SELECT trade_id, ticker, price, count, side, ts FROM perps_trades "
        "WHERE env=? AND ticker=? AND ts>=? ORDER BY ts DESC LIMIT ?",
        [env, ticker, int(since_ts), int(limit)],
    )
    return list(reversed(rows))


def perps_trades_count(env: str) -> int:
    rows = _query("SELECT COUNT(*) AS n FROM perps_trades WHERE env=?", [env])
    return int(rows[0]["n"]) if rows else 0


# ================= 市场目录（series 缓存） =================
def save_series_catalog(env: str, rows: list) -> None:
    """整包替换该环境的市场目录（已下架的系列会被清掉）。"""
    now = datetime.now()
    with _lock:
        c = conn()
        c.execute("DELETE FROM series_catalog WHERE env=?", [env])
        if rows:
            c.executemany(
                "INSERT OR REPLACE INTO series_catalog "
                "(env, ticker, title, category, frequency, updated_at) "
                "VALUES (?,?,?,?,?,?)",
                [[env, r.get("ticker"), r.get("title"), r.get("category"),
                  r.get("frequency"), now] for r in rows],
            )


def series_catalog(env: str) -> list:
    """本地缓存的市场目录；空列表表示还没同步过。"""
    return _query(
        "SELECT ticker, title, category, frequency, updated_at "
        "FROM series_catalog WHERE env=? ORDER BY ticker", [env])


def categories(env: str) -> list[str]:
    """该环境已缓存的所有 category（去重，按字母序）。"""
    rows = _query(
        "SELECT DISTINCT category FROM series_catalog "
        "WHERE env=? AND category IS NOT NULL AND category <> '' "
        "ORDER BY category", [env])
    return [r["category"] for r in rows if r.get("category")]


def series_by_category(env: str, category: str = "") -> list[dict]:
    """某品类下的系列列表（KXBTC15M / KXETH15M ...）。

    category 为空时返回全部系列。按周期 + ticker 排序。
    """
    if category:
        return _query(
            "SELECT ticker, title, category, frequency FROM series_catalog "
            "WHERE env=? AND category=? ORDER BY frequency, ticker",
            [env, category])
    return _query(
        "SELECT ticker, title, category, frequency FROM series_catalog "
        "WHERE env=? ORDER BY category, frequency, ticker", [env])


def tickers_by_category(env: str, category: str) -> list[str]:
    """取指定 category 下的所有 ticker（series 级市场名）。"""
    if not category:
        return []
    rows = _query(
        "SELECT ticker FROM series_catalog WHERE env=? AND category=? "
        "ORDER BY frequency, ticker",
        [env, category])
    return [r["ticker"] for r in rows if r.get("ticker")]


def recent_active_tickers(env: str, min_window_sec: int = 900) -> list[str]:
    """近 min_window_sec 秒内有成交的 ticker（market_trades / perps_trades 都算）。"""
    since_ts = int(time.time()) - min_window_sec
    try:
        rows = _query(
            "SELECT DISTINCT ticker FROM market_trades WHERE env=? AND ts>=?"
            " UNION "
            "SELECT DISTINCT ticker FROM perps_trades WHERE env=? AND ts>=? "
            "ORDER BY ticker",
            [env, since_ts, env, since_ts])
        return [r["ticker"] for r in rows if r.get("ticker")]
    except Exception:
        return []


# ================= CF Benchmarks =================
def save_cfb_ticks(env: str, rows: list) -> None:
    """一批 CF Benchmarks tick 落库（批量 INSERT OR IGNORE 避免重复 server_time）。"""
    if not rows:
        return
    with _lock:
        conn().executemany(
            "INSERT OR IGNORE INTO cfb_ticks "
            "(env, index_id, value, time_ms, server_time) VALUES (?,?,?,?,?)",
            [[env, r.get("index_id"), r.get("value"), r.get("time_ms"),
              r.get("server_time")] for r in rows],
        )


def cfb_latest(env: str, index_ids: Optional[list[str]] = None) -> dict:
    """每个 index_id 取最新一条 tick → {index_id: {value, ingested_at}}。

    不传 index_ids 时返回库里所有 index_id 的最新快照。
    """
    sql = (
        "WITH ranked AS (SELECT index_id, value, ingested_at, "
        "ROW_NUMBER() OVER (PARTITION BY index_id ORDER BY ingested_at DESC) AS rn "
        "FROM cfb_ticks WHERE env=?"
    )
    params: list = [env]
    if index_ids:
        marks = ",".join("?" * len(index_ids))
        sql += f" AND index_id IN ({marks})"
        params.extend(index_ids)
    sql += ") SELECT index_id, value, ingested_at FROM ranked WHERE rn=1"
    out = {}
    for r in _query(sql, params):
        out[r["index_id"]] = r
    return out


def cfb_history(env: str, index_id: str, hours: float = 24.0,
                limit: int = 500) -> list[dict]:
    """拉某个 CF index 最近 N 小时的 tick，按时间正序返回（画曲线用）。"""
    cutoff = datetime.fromtimestamp(
        datetime.now().timestamp() - hours * 3600)
    rows = _query(
        "SELECT index_id, value, time_ms, server_time, ingested_at "
        "FROM cfb_ticks WHERE env=? AND index_id=? AND ingested_at >= ? "
        "ORDER BY ingested_at DESC LIMIT ?",
        [env, index_id, cutoff, int(limit)])
    rows.reverse()          # 取最近 limit 条，再转成时间正序
    return rows


def persist(env: str, key_id: str, *, balance=None, positions=None, orders=None,
            subs=None, fills=None, settlements=None, transfers=None) -> None:
    """一次同步的所有结果落库（在 io 线程中调用）。"""
    if balance is not None:
        save_balance(env, key_id, balance)
    if positions is not None:
        save_positions(env, positions)
    if orders is not None:
        save_orders(env, orders)
    if subs is not None:
        save_subaccounts(env, subs)
    if fills is not None:
        save_fills(env, fills)
    if settlements is not None:
        save_settlements(env, settlements)
    if transfers is not None:
        save_transfers(env, transfers)


# ================= 读取 =================
def latest_balance(env: str, key_id: Optional[str] = None) -> dict:
    sql = "SELECT * FROM balance_snapshots WHERE env=?"
    params = [env]
    if key_id:
        sql += " AND key_id=?"
        params.append(key_id)
    rows = _query(sql + " ORDER BY ts DESC LIMIT 1", params)
    if not rows:
        return {}
    r = rows[0]
    try:
        shards = json.loads(r.get("shards") or "[]")
    except ValueError:
        shards = []
    return {
        "available": r.get("available") or 0.0,
        "portfolio_value": r.get("portfolio_value"),
        "payout": r.get("payout"),
        "shards": shards,
        "synced_at": r.get("ts"),
    }


def positions(env: str) -> list:
    rows = _query(
        "SELECT * FROM positions WHERE env=? ORDER BY ABS(COALESCE(exposure,0)) DESC", [env])
    for r in rows:
        r["resting"] = int(r.get("resting") or 0)
    return rows


def reconcile_resting(env: str, keep_ids: list, ticker: Optional[str] = None) -> int:
    """用在挂订单的权威快照校正本地库。

    本地 orders 是历史累积表，某些订单可能因到期/撤单早已不是 resting，
    但由于不在增量拉取窗口内，本地状态仍是陈旧的 'resting'，会错误地
    出现在"在挂"列表里。调用方拿到 API 的最新 resting 列表后，把本地
    不在该列表中的 resting 订单标记为 'canceled'。

    :param keep_ids: API 返回的当前 resting 订单 id 集合（权威）
    :param ticker: 若本次只拉了某个 ticker，则只校正该 ticker，避免误伤其他
    :return: 被标记的行数
    """
    sql = "UPDATE orders SET status='canceled' WHERE env=? AND status='resting'"
    params: list = [env]
    if ticker:
        sql += " AND ticker=?"
        params.append(ticker)
    if keep_ids:
        marks = ",".join("?" * len(keep_ids))
        sql += f" AND order_id NOT IN ({marks})"
        params.extend(keep_ids)
    try:
        with _lock:
            # DuckDB 无 changes()，用 RETURNING 精确拿受影响行数
            rows = conn().execute(sql + " RETURNING order_id", params).fetchall()
        return len(rows)
    except Exception:
        return 0


def orders(env: str, status: Optional[str] = None, ticker: Optional[str] = None,
           limit: int = 1000) -> list:
    """从 orders_view 读订单：额外带 created_utc / created_et / created_bj
    三时区列以及 settle_result（win / loss / n/a / NULL）。"""
    sql = "SELECT * FROM orders_view WHERE env=?"
    params = [env]
    if status:
        sql += " AND status=?"
        params.append(status)
    if ticker:
        sql += " AND ticker=?"
        params.append(ticker)
    sql += " ORDER BY created DESC NULLS LAST LIMIT ?"
    params.append(int(limit))
    return _query(sql, params)


def fills(env: str, ticker: Optional[str] = None, days: Optional[int] = None,
          limit: int = 1000) -> list:
    sql = "SELECT * FROM fills WHERE env=?"
    params = [env]
    if ticker:
        sql += " AND ticker=?"
        params.append(ticker)
    if days:
        cutoff = datetime.fromtimestamp(
            datetime.now().timestamp() - days * 86400).isoformat(timespec="seconds")
        sql += " AND created >= ?"
        params.append(cutoff)
    sql += " ORDER BY created DESC NULLS LAST LIMIT ?"
    params.append(int(limit))
    return _query(sql, params)


def subaccounts(env: str) -> list:
    return _query(
        "SELECT * FROM subaccount_balances WHERE env=? "
        "ORDER BY exchange_index NULLS FIRST, subaccount NULLS FIRST", [env])


def settlements(env: str, ticker: Optional[str] = None) -> list:
    sql = "SELECT * FROM settlements WHERE env=?"
    params = [env]
    if ticker:
        sql += " AND ticker=?"
        params.append(ticker)
    return _query(sql + " ORDER BY settled_time DESC NULLS LAST", params)


def transfers(env: str, limit: int = 50) -> list:
    return _query(
        "SELECT * FROM transfers WHERE env=? ORDER BY created_ts DESC NULLS LAST LIMIT ?",
        [env, int(limit)])


def load_state(env: str, key_id: Optional[str] = None, status: Optional[str] = None,
               ticker: Optional[str] = None, fill_ticker: Optional[str] = None,
               fill_days: Optional[int] = None, with_fills: bool = True) -> dict:
    """界面渲染用的整包数据（全部来自本地库）。"""
    state = {
        "balance": latest_balance(env, key_id),
        "positions": positions(env),
        "orders": orders(env, status, ticker),
        "subs": subaccounts(env),
    }
    if with_fills:
        state["fills"] = fills(env, fill_ticker, fill_days)
    return state


# ================= 分析聚合 =================
def analytics(env: str, days: int = 30) -> dict:
    """供「分析」页与 AI 问答使用的本地库汇总。"""
    cutoff = datetime.fromtimestamp(datetime.now().timestamp() - days * 86400)
    fills_row = _query(
        "SELECT COUNT(*) AS n, COALESCE(SUM(count),0) AS contracts, "
        "COALESCE(SUM(count * price),0) AS volume, COALESCE(SUM(fees),0) AS fees "
        "FROM fills WHERE env=? AND TRY_CAST(created AS TIMESTAMP) >= ?",
        [env, cutoff])
    orders_row = _query(
        "SELECT status, COUNT(*) AS n FROM orders WHERE env=? GROUP BY status", [env])
    settle_rows = _query(
        "SELECT ticker, market_result, yes_count, yes_cost, no_count, no_cost, "
        "revenue, fee, settled_time FROM settlements WHERE env=? "
        "ORDER BY settled_time DESC NULLS LAST LIMIT 200", [env])
    payout = 0.0
    cost = 0.0
    for s in settle_rows:
        result = (s.get("market_result") or "").lower()
        payout += (s.get("yes_count") or 0) if result == "yes" else 0
        payout += (s.get("no_count") or 0) if result == "no" else 0
        cost += (s.get("yes_cost") or 0) + (s.get("no_cost") or 0) + (s.get("fee") or 0)
    top = _query(
        "SELECT ticker, COUNT(*) AS fills, COALESCE(SUM(count),0) AS contracts, "
        "COALESCE(SUM(count * price),0) AS volume FROM fills WHERE env=? "
        "GROUP BY ticker ORDER BY volume DESC LIMIT 10", [env])
    pos = positions(env)
    return {
        "days": days,
        "fills": fills_row[0] if fills_row else {},
        "orders": {r["status"]: r["n"] for r in orders_row},
        "settlements": {
            "count": len(settle_rows), "payout": payout, "cost": cost,
            "net": payout - cost, "recent": settle_rows[:10],
        },
        "top_markets": top,
        "balance": latest_balance(env),
        "position_count": len(pos),
        "exposure": sum((p.get("exposure") or 0) for p in pos),
        "realized_pnl": sum((p.get("realized_pnl") or 0) for p in pos),
    }


# ================= 聊天室 =================
def add_chat_message(env: str, username: str, body: str, image: str = "") -> dict:
    msg = {
        "id": uuid4().hex,
        "env": env,
        "username": username,
        "body": body or "",
        "image": image or "",
        "created": datetime.now(),
    }
    _exec("INSERT INTO chat_messages VALUES (?,?,?,?,?,?)",
          [msg["id"], env, username, msg["body"], msg["image"], msg["created"]])
    return msg


def chat_messages(env: str, limit: int = 100) -> list:
    rows = _query(
        "SELECT * FROM (SELECT * FROM chat_messages WHERE env=? "
        "ORDER BY created DESC LIMIT ?) ORDER BY created ASC", [env, int(limit)])
    return rows


def clear_chat(env: str) -> None:
    _exec("DELETE FROM chat_messages WHERE env=?", [env])


# ================= 动量机器人 =================
def mo_log(env: str, level: str, message: str,
           ticker: str = "", detail: Optional[dict] = None) -> None:
    """追加一条动量机器人运行日志。"""
    with _lock:
        conn().execute(
            "INSERT INTO mo_log (id, env, level, message, ticker, detail) "
            "VALUES (?,?,?,?,?,?)",
            [str(uuid4()), env, level, message, ticker or "",
             json.dumps(detail or {}, default=str)])


def mo_log_recent(env: str, limit: int = 100) -> list:
    return _query(
        "SELECT ts, level, message, ticker, detail FROM mo_log "
        "WHERE env=? ORDER BY ts DESC LIMIT ?", [env, limit])


def mo_upsert_trade(env: str, buy_order_id: str, **fields) -> None:
    """upsert 一条动量单（用于 watcher 状态回写）。

    注意：updated_ts 不能用 SQL 里的 CURRENT_TIMESTAMP ——DuckDB 在
    ON CONFLICT DO UPDATE 的 SET 子句里会把它当列名解析（Binder Error），
    所以统一用参数传 datetime。
    """
    data = dict(fields)
    data["updated_ts"] = datetime.now()
    cols = ",".join(data.keys())
    marks = ",".join(["?"] * len(data))
    updates = ",".join([f"{k}=excluded.{k}" for k in data])
    values = [env, buy_order_id, *data.values()]
    with _lock:
        conn().execute(
            f"INSERT INTO mo_trades (env, buy_order_id, {cols}) VALUES (?,?,{marks}) "
            f"ON CONFLICT (env, buy_order_id) DO UPDATE SET {updates}", values)


def mo_trades(env: str, only_open: bool = False, limit: int = 200) -> list:
    sql = "SELECT * FROM mo_trades WHERE env=?"
    params: list = [env]
    if only_open:
        sql += " AND state NOT IN ('tp_filled','canceled','failed')"
    sql += " ORDER BY created_ts DESC LIMIT ?"
    params.append(limit)
    return _query(sql, params)


def mo_trade_by_buy_order(env: str, buy_order_id: str) -> Optional[dict]:
    rows = _query(
        "SELECT * FROM mo_trades WHERE env=? AND buy_order_id=?",
        [env, buy_order_id])
    return rows[0] if rows else None


def mo_open_by_series(env: str, series: str,
                      window_min: int = 60) -> list:
    """同系列是否还有未完成的动量单（buy_placed / buy_filled / tp_placed）。

    这是「一局没结束不开下一局」的兜底判据：即使内存里的 watcher 因为异常
    丢失，DB 里的未完成记录也能阻止同系列重复开单。
    窗口限制避免历史脏数据永久阻塞（15 分钟系列 60 分钟足够覆盖）。
    """
    if not series:
        return []
    h = max(1, int(window_min))
    return _query(
        "SELECT * FROM mo_trades WHERE env=? AND series=? "
        "AND state IN ('buy_placed','buy_filled','tp_placed') "
        f"AND created_ts >= NOW() - INTERVAL {h} MINUTE "
        "ORDER BY created_ts DESC", [env, series])


def mo_open_by_ticker(env: str, ticker: str,
                      window_min: int = 60) -> list:
    """同 ticker 是否还有未完成的动量单（series 为空时的兜底判据）。

    例外：state='buy_filled' 且还没有 sell_order_id 的行走的是「刚成交、正在挂
    止盈」的瞬时窗口，只给 120 秒宽限。超过仍未挂上止盈说明是异常残行（例如
    post_only 被拒导致止盈挂单失败），放行以免永久锁死该 ticker。
    """
    if not ticker:
        return []
    h = max(1, int(window_min))
    return _query(
        "SELECT * FROM mo_trades WHERE env=? AND ticker=? "
        "AND (state IN ('buy_placed','tp_placed') "
        "     OR (state='buy_filled' AND (sell_order_id IS NOT NULL "
        "         OR COALESCE(updated_ts, created_ts) >= NOW() - INTERVAL 120 SECOND))) "
        f"AND created_ts >= NOW() - INTERVAL {h} MINUTE "
        "ORDER BY created_ts DESC", [env, ticker])


def mo_stats(env: str, since_hours: float = 24.0) -> dict:
    """汇总近 N 小时动量单统计：总数 / 成交 / 止盈 / 胜率 / pnl / 平均 Δ。"""
    try:
        h = float(since_hours)
    except (TypeError, ValueError):
        h = 24.0
    sql = (f"SELECT COUNT(*) AS total, "
           f"COUNT(CASE WHEN state='tp_filled' THEN 1 END) AS wins, "
           f"COUNT(CASE WHEN state='buy_filled' THEN 1 END) AS buys_filled, "
           f"COUNT(CASE WHEN state='tp_placed' THEN 1 END) AS tps_resting, "
           f"COUNT(CASE WHEN state='canceled' THEN 1 END) AS canceled, "
           f"SUM(CASE WHEN state='tp_filled' THEN pnl ELSE 0 END) AS total_pnl, "
           f"AVG(delta) AS avg_delta "
           f"FROM mo_trades WHERE env=? AND created_ts >= NOW() - INTERVAL {h} HOUR")
    rows = _query(sql, [env])
    r = rows[0] if rows else {}
    return {
        "total": int(r.get("total") or 0),
        "wins": int(r.get("wins") or 0),
        "buys_filled": int(r.get("buys_filled") or 0),
        "tps_resting": int(r.get("tps_resting") or 0),
        "canceled": int(r.get("canceled") or 0),
        "pnl": float(r.get("total_pnl") or 0),
        "avg_delta": float(r.get("avg_delta") or 0),
    }
