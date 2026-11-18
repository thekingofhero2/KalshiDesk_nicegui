# -*- coding: utf-8 -*-
"""Kalshi WebSocket 实时成交（trade 频道）订阅客户端。

- 认证：与 REST 相同的 RSA-PSS 签名，签名 path 固定为 /trade-api/ws/v2
- 订阅：{"cmd":"subscribe","params":{"channels":["trade"],"market_tickers":[...]}}
- 数据：收到 trade 消息后批量写入 DuckDB market_trades 表
- 生命周期：按 series 每 15 秒发现 open/unopened ticker，自动切换并自动重连
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from . import db

log = logging.getLogger("kalshi.ws")

WS_ENDPOINTS = {
    "prod": "wss://api.elections.kalshi.com/trade-api/ws/v2",
    "demo": "wss://demo-api.kalshi.co/trade-api/ws/v2",
}

# Kalshi Perps（Invest）是独立交易所：REST/WS 域名与预测市场不同
PERPS_REST_ENDPOINTS = {
    "prod": "https://external-api.kalshi.com/trade-api/v2",
    "demo": "https://external-api.demo.kalshi.co/trade-api/v2",
}
PERPS_WS_ENDPOINTS = {
    "prod": "wss://external-api-margin-ws.kalshi.com/trade-api/ws/v2/margin",
    "demo": "wss://external-api-margin-ws.demo.kalshi.co/trade-api/ws/v2/margin",
}
PERPS_WS_PATH = "/trade-api/ws/v2/margin"
PERPS_CHANNELS = ("ticker", "trade")

# CF Benchmarks 实时指数值（Kalshi 转发频道）
CFB_WS_ENDPOINTS = {
    "prod": "wss://external-api-ws.kalshi.com/trade-api/ws/v2",
    "demo": "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2",
}
CFB_WS_PATH = "/trade-api/ws/v2"
CFB_CHANNEL = "cfbenchmarks_value"


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class TradeSubscriber:
    """单个环境一个实例，管理 trades 频道的订阅与落库。"""

    def __init__(self, key_id: str, pem_path: str, env: str = "prod",
                 proxy: Optional[str] = None):
        self.key_id = key_id
        self.env = env if env in WS_ENDPOINTS else "prod"
        self.url = WS_ENDPOINTS[self.env]
        self.proxy = proxy
        self._pem_path = pem_path
        self._private_key = None

        self.series: set[str] = set()       # 用户选择的市场（series）
        self.tickers: set[str] = set()      # 自动发现的当前/即将开盘 ticker
        self._series_tickers: dict[str, set[str]] = {}
        self.last_market_refresh: float = 0.0
        self.last_market_error: str = ""
        self._rest = None
        self.status: str = "stopped"        # stopped / connecting / connected / error
        self.last_error: str = ""
        self.last_msg_ts: float = 0.0       # 最近一次收到任何消息的时间
        self.msg_count: int = 0             # 累计收到的 trade 条数
        self.saved_count: int = 0           # 累计落库条数

        self._task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._market_task: Optional[asyncio.Task] = None
        self._market_lock = asyncio.Lock()
        self._ws = None
        self._running = False
        self._cmd_seq = 0
        # === WS 订阅状态（对齐 myk/sources/kalshi_ws.py 的 sid 管理）===
        # subscribe() 只返回命令 id，服务端真实 sid 要等 subscribed 控制帧回填；
        # 拿到 sid 后增量订阅必须用 update_subscription(sids=[sid], add_markets)，
        # 否则会累积多条 subscribe 命令、或触发 code 7（Unknown subscription ID）。
        self._sub_sid: Optional[int] = None   # trade 频道的真实 sid
        self._sub_cid: Optional[int] = None   # 尚未回填 sid 的命令 id
        self._sub_pending: set[str] = set()   # 首次 subscribe 里已带上、等回填的 ticker
        self._subscribed: set[str] = set()    # 已确认发出订阅的 ticker（增量判据）
        self._buf: list[dict] = []          # 待落库缓冲
        self._buf_lock = asyncio.Lock()

    # ---------------- 签名 ----------------
    def _load_key(self):
        if self._private_key is None:
            from cryptography.hazmat.primitives import serialization
            with open(self._pem_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(), password=None)
        return self._private_key

    def _headers(self) -> dict:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        ts_ms = str(int(time.time() * 1000))
        message = (ts_ms + "GET" + "/trade-api/ws/v2").encode("utf-8")
        signature = self._load_key().sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }

    # ---------------- 生命周期 ----------------
    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"kalshi-ws-{self.env}")
        self._flush_task = asyncio.create_task(
            self._flush_periodically(), name=f"kalshi-ws-flush-{self.env}")
        self._market_task = asyncio.create_task(
            self._refresh_markets_periodically(), name=f"kalshi-markets-{self.env}")

    async def stop(self) -> None:
        self._running = False
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except (asyncio.CancelledError, Exception):
                pass
            self._flush_task = None
        if self._market_task:
            self._market_task.cancel()
            try:
                await self._market_task
            except (asyncio.CancelledError, Exception):
                pass
            self._market_task = None
        self.status = "stopped"
        self._reset_subscription_state()
        await self._flush()

    # ---------------- 市场级订阅管理 ----------------
    def _rest_api(self):
        if self._rest is None:
            from .api import DeskAPI
            self._rest = DeskAPI(self.key_id, self._pem_path, self.env, proxy=self.proxy)
        return self._rest

    async def set_series(self, series: set[str]) -> None:
        """设置目标市场；ticker 完全由 REST 自动发现，无需手工维护。"""
        series = {s.strip().upper() for s in series if s and s.strip()}
        if series == self.series:
            return
        self.series = series
        await self.refresh_markets()

    async def add_series(self, series_ticker: str) -> None:
        if series_ticker:
            await self.set_series(self.series | {series_ticker})

    async def refresh_markets(self) -> None:
        """刷新所有市场的活跃 ticker；单市场失败时保留该市场上轮结果。"""
        async with self._market_lock:
            discovered: dict[str, set[str]] = {}
            errors = []
            for series in sorted(self.series):
                try:
                    rows = await asyncio.to_thread(
                        self._rest_api().subscription_markets, series)
                    discovered[series] = set(rows)
                except Exception as ex:
                    discovered[series] = set(self._series_tickers.get(series, set()))
                    errors.append(f"{series}: {ex}")
                    log.warning("%s 活跃市场刷新失败：%s", series, ex)
            self._series_tickers = discovered
            tickers = set().union(*discovered.values()) if discovered else set()
            self.last_market_refresh = time.time()
            self.last_market_error = "；".join(errors)[:300]
            await self._apply_tickers(tickers)

    async def _apply_tickers(self, tickers: set[str]) -> None:
        """把最新发现的市场 ticker 应用到 WS 订阅。

        只增不减：Kalshi 的 remove_markets 会被服务端拒绝，且 15 分钟市场
        滚场后旧 ticker 很快关闭、不再产生成交，留着不影响数据正确性。
        旧实现遇到 removed 就整条重连，导致滚场时反复断线、新 ticker 漏订阅。
        """
        self.tickers = set(tickers)
        if self._ws is None or self.status != "connected":
            # 连接未就绪：不清任何状态，等 _run 连上后按 self.tickers 全量补订
            return
        await self._ensure_subscription()

    async def _refresh_markets_periodically(self) -> None:
        # 15 分钟市场需要及时跟随滚场，30 秒刷新一次（myk 用 60s，
        # 这里缩短以覆盖短周期；失败只影响本轮，下轮自动重试）。
        while self._running:
            await asyncio.sleep(30.0)
            if self.series:
                try:
                    await self.refresh_markets()
                except asyncio.CancelledError:
                    raise
                except Exception as ex:
                    log.warning("市场刷新失败（下轮重试）：%s", ex)

    async def _reconnect(self) -> None:
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass
        self._reset_subscription_state()

    def _reset_subscription_state(self) -> None:
        self._sub_sid = None
        self._sub_cid = None
        self._sub_pending.clear()
        self._subscribed.clear()

    # ---------------- 主循环 ----------------
    async def _run(self) -> None:
        import websockets
        backoff = 1.0
        while self._running:
            self.status = "connecting"
            try:
                kwargs = {
                    "additional_headers": self._headers(),
                    "ping_interval": 20,
                    "ping_timeout": 20,
                    "max_size": 4 * 1024 * 1024,
                }
                if self.proxy:
                    kwargs["proxy"] = self.proxy
                async with websockets.connect(self.url, **kwargs) as ws:
                    self._ws = ws
                    self.status = "connected"
                    self.last_error = ""
                    backoff = 1.0
                    # 重连后服务端 sid 从 1 重新分配，旧订阅全部失效
                    self._reset_subscription_state()
                    if self.tickers:
                        await self._ensure_subscription()
                    async for raw in ws:
                        if not self._running:
                            break
                        await self._on_message(raw)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                self.status = "error"
                self.last_error = str(ex)[:300]
                log.warning("ws 连接异常：%s", ex)
            finally:
                self._ws = None
                self._reset_subscription_state()
                await self._flush()
            if not self._running:
                break
            self.status = "connecting"
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        self.status = "stopped"

    async def _ensure_subscription(self) -> None:
        """确保 self.tickers 全部在订阅里（首次 subscribe / 之后 add_markets）。

        对齐 myk 的订阅逻辑：
          - 首次：subscribe(channels=["trade"], market_tickers=[全量])，等 subscribed
            帧回填真实 sid 才能增量
          - 之后：update_subscription(sids=[sid], action="add_markets", market_tickers=新增)
          - 只增不减（remove_markets 会被服务端拒绝）
        """
        if self._ws is None:
            return
        want = sorted(t for t in self.tickers if t)
        if not want:
            return

        # ① 已在等 sid 回填：不要重复 subscribe（会产生多余订阅 sid）
        if self._sub_sid is None and self._sub_cid is not None:
            return

        # ② 还没有 sid：发起一次全新订阅（带上当前全部 ticker）
        if self._sub_sid is None:
            self._cmd_seq += 1
            cid = self._cmd_seq
            msg = {
                "id": cid,
                "cmd": "subscribe",
                "params": {"channels": ["trade"], "market_tickers": want},
            }
            try:
                await self._ws.send(json.dumps(msg))
            except Exception as ex:
                log.warning("ws 订阅发送失败：%s", ex)
                return
            self._sub_cid = cid
            self._sub_pending = set(want)
            log.info("ws 发起首次订阅 %d 个 ticker（等待 sid 回填）", len(want))
            return

        # ③ 已有 sid：只对新出现的 ticker 做 add_markets 增量
        new = [t for t in want if t not in self._subscribed]
        if not new:
            return
        self._cmd_seq += 1
        msg = {
            "id": self._cmd_seq,
            "cmd": "update_subscription",
            # 官方协议是数组字段 sids（不是 sid）
            "params": {"sids": [self._sub_sid], "action": "add_markets",
                       "market_tickers": new},
        }
        try:
            await self._ws.send(json.dumps(msg))
            self._subscribed.update(new)
            log.info("ws 增量订阅 %d 个新 ticker：%s", len(new), new[:3])
        except Exception as ex:
            log.warning("ws 增量订阅失败（下轮重试）：%s", ex)

    async def _ensure_subscription_safe(self) -> None:
        """控制帧回调里调用 _ensure_subscription 的异常保护版本。"""
        try:
            await self._ensure_subscription()
        except Exception as ex:
            log.warning("ws 订阅补全失败：%s", ex)

    async def _send_subscribe(self, tickers: list[str]) -> None:
        """兼容旧调用点：把 tickers 并入期望集合后走统一订阅流程。"""
        self.tickers.update(tickers)
        await self._ensure_subscription()

    # ---------------- 消息处理 ----------------
    async def _on_message(self, raw) -> None:
        self.last_msg_ts = time.time()
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        mtype = data.get("type")
        # === 订阅控制帧：回填真实 sid，后续增量 add_markets 才能生效 ===
        if mtype == "subscribed":
            msg = data.get("msg") or {}
            sid = msg.get("sid")
            cid = data.get("id")
            if sid is not None and (self._sub_cid is None or cid == self._sub_cid):
                self._sub_sid = int(sid)
                self._subscribed.update(self._sub_pending)
                self._sub_pending.clear()
                self._sub_cid = None
                log.info("ws 订阅已确认 sid=%s，已订阅 %d 个 ticker",
                         self._sub_sid, len(self._subscribed))
                # 回填期间可能又出现了新 ticker，这里补一次增量
                await self._ensure_subscription_safe()
            return
        if mtype == "unsubscribed":
            return
        if mtype == "error":
            msg = data.get("msg") or {}
            code = msg.get("code")
            self.last_error = str(msg or data)[:300]
            # code 7 = Unknown subscription ID：重连后旧 sid 全部失效，
            # 必须重置订阅状态，否则增量订阅永远失败、新窗口市场漏订阅。
            if code == 7:
                log.warning("ws 订阅 sid 失效（code 7），重置后重建订阅")
                self._reset_subscription_state()
                await self._ensure_subscription_safe()
            return
        if mtype != "trade":
            return
        msg = data.get("msg") or {}
        row = self._parse_trade(msg)
        if not row:
            return
        self.msg_count += 1
        async with self._buf_lock:
            self._buf.append(row)
            need_flush = len(self._buf) >= 50
        if need_flush:
            await self._flush()

    def _parse_trade(self, msg: dict) -> Optional[dict]:
        """解析官方 trade 消息，价格统一为美元、时间统一为 Unix 秒。"""
        ticker = msg.get("ticker") or msg.get("market_ticker")
        if not ticker:
            return None
        # 当前官方字段是 yes_price_dollars / yes_price；旧消息可能只有 price。
        price = _num(msg.get("yes_price_dollars"))
        if price is None and msg.get("yes_price") is not None:
            price = (_num(msg.get("yes_price")) or 0.0) / 100.0
        if price is None:
            price = _num(msg.get("price"))
            if price is not None and price > 1.0:
                price = price / 100.0
        count = _num(msg.get("count"))
        if count is None:
            count = _num(msg.get("count_fp"))
        raw_ts = msg.get("created_time") or msg.get("ts") or msg.get("created_ts")
        ts = None
        if isinstance(raw_ts, str) and ("-" in raw_ts or "T" in raw_ts):
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
        if ts is None:
            try:
                ts = float(raw_ts)
            except (TypeError, ValueError):
                ts = time.time()
        if ts > 2e10:  # 毫秒时间戳
            ts /= 1000.0
        trade_id = (msg.get("trade_id") or msg.get("id")
                    or f"{ticker}-{ts}-{price}-{count}")
        return {
            "trade_id": str(trade_id),
            "ticker": ticker,
            "price": price,
            "count": count or 0.0,
            "side": (msg.get("taker_side") or msg.get("side") or "").lower(),
            "ts": int(ts),
        }

    async def _flush_periodically(self) -> None:
        """低频市场也至少每秒刷盘一次，让图表及时看到新成交。"""
        while self._running:
            await asyncio.sleep(1.0)
            await self._flush()

    async def _flush(self) -> None:
        async with self._buf_lock:
            if not self._buf:
                return
            batch, self._buf = self._buf, []
        try:
            await asyncio.to_thread(db.save_market_trades, self.env, batch)
            self.saved_count += len(batch)
        except Exception as ex:
            async with self._buf_lock:
                self._buf = batch + self._buf
            log.warning("trades 落库失败：%s", ex)

    # ---------------- 状态快照（UI 用） ----------------
    def snapshot(self) -> dict:
        return {
            "env": self.env,
            "status": self.status,
            "running": self._running,
            "series": sorted(self.series),
            "tickers": sorted(self.tickers),
            "series_tickers": {s: sorted(ts) for s, ts in self._series_tickers.items()},
            "last_market_refresh": self.last_market_refresh,
            "last_market_error": self.last_market_error,
            "subscribed": sorted(self._subscribed),
            "sub_sid": self._sub_sid,
            "sub_pending": sorted(self._sub_pending),
            "msg_count": self.msg_count,
            "saved_count": self.saved_count,
            "last_msg_ts": self.last_msg_ts,
            "last_error": self.last_error,
        }


class PerpsSubscriber:
    """Kalshi Perps（Invest）实时行情订阅：ticker + trade 两个频道。

    与预测市场订阅完全独立：
    - REST: external-api.kalshi.com /trade-api/v2/margin/*
    - WS:   external-api-margin-ws.kalshi.com /trade-api/ws/v2/margin
    """

    def __init__(self, key_id: str, pem_path: str, env: str = "prod",
                 proxy: Optional[str] = None):
        self.key_id = key_id
        self.env = env if env in PERPS_REST_ENDPOINTS else "prod"
        self.rest_url = PERPS_REST_ENDPOINTS[self.env]
        self.url = PERPS_WS_ENDPOINTS[self.env]
        self.proxy = proxy
        self._pem_path = pem_path
        self._private_key = None
        self._rest = None

        self.tickers: set[str] = set()      # 订阅的 perps 市场，如 KXBTCPERP
        self.status: str = "stopped"
        self.last_error: str = ""
        self.last_msg_ts: float = 0.0
        self.msg_count: int = 0             # 收到的 ticker+trade 消息数
        self.ticker_count: int = 0
        self.trade_count: int = 0
        self.saved_count: int = 0
        self.latest: dict[str, dict] = {}   # ticker -> 最新 ticker 快照
        self._recent: list[dict] = []       # 最近成交，最新在前

        self._task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._ws = None
        self._running = False
        self._cmd_seq = 0
        self._subscribed: set[str] = set()
        self._buf: list[dict] = []
        self._buf_lock = asyncio.Lock()

    # ---------------- 签名 ----------------
    def _load_key(self):
        if self._private_key is None:
            from cryptography.hazmat.primitives import serialization
            with open(self._pem_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(), password=None)
        return self._private_key

    def _headers(self) -> dict:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        ts_ms = str(int(time.time() * 1000))
        message = (ts_ms + "GET" + PERPS_WS_PATH).encode("utf-8")
        signature = self._load_key().sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }

    # ---------------- 市场列表（REST） ----------------
    def _rest_api(self):
        if self._rest is None:
            from .client import KalshiClient
            self._rest = KalshiClient(self.key_id, self._pem_path,
                                      base_url=self.rest_url, proxy=self.proxy)
        return self._rest

    def markets(self) -> list:
        """GET /margin/markets，返回可订阅的 perps 市场。"""
        data = self._rest_api().request("GET", "/margin/markets")
        rows = data.get("markets") or data.get("margin_markets") or []
        out = []
        for m in rows:
            ticker = (m.get("ticker") or "").strip()
            if not ticker:
                continue
            out.append({
                "ticker": ticker,
                "title": m.get("title") or "",
                "asset_class": m.get("asset_class") or "",
                "status": m.get("status") or "",
            })
        out.sort(key=lambda r: r["ticker"])
        return out

    # ---------------- 生命周期 ----------------
    @property
    def running(self) -> bool:
        return self._running

    async def set_tickers(self, tickers) -> None:
        new = {t.strip().upper() for t in tickers if t and t.strip()}
        if new == self.tickers:
            return
        self.tickers = new
        if self._ws is not None and self.status == "connected":
            await self._reconnect()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"kalshi-perps-ws-{self.env}")
        self._flush_task = asyncio.create_task(
            self._flush_periodically(), name=f"kalshi-perps-flush-{self.env}")

    async def stop(self) -> None:
        self._running = False
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass
        for task in (self._task, self._flush_task):
            if task is not None:
                task.cancel()
        self._task = None
        self._flush_task = None
        self.status = "stopped"
        self._subscribed.clear()
        await self._flush()

    async def _reconnect(self) -> None:
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass
        self._subscribed.clear()

    # ---------------- 主循环 ----------------
    async def _run(self) -> None:
        import websockets
        backoff = 1.0
        while self._running:
            self.status = "connecting"
            try:
                kwargs = {
                    "additional_headers": self._headers(),
                    "ping_interval": 20,
                    "ping_timeout": 20,
                    "max_size": 4 * 1024 * 1024,
                }
                if self.proxy:
                    kwargs["proxy"] = self.proxy
                async with websockets.connect(self.url, **kwargs) as ws:
                    self._ws = ws
                    self.status = "connected"
                    self.last_error = ""
                    backoff = 1.0
                    self._subscribed.clear()
                    if self.tickers:
                        await self._send_subscribe(sorted(self.tickers))
                    async for raw in ws:
                        if not self._running:
                            break
                        await self._on_message(raw)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                self.status = "error"
                self.last_error = str(ex)[:300]
                log.warning("perps ws 连接异常：%s", ex)
            finally:
                self._ws = None
                self._subscribed.clear()
                await self._flush()
            if not self._running:
                break
            self.status = "connecting"
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        self.status = "stopped"

    async def _send_subscribe(self, tickers: list[str]) -> None:
        if self._ws is None or not tickers:
            return
        self._cmd_seq += 1
        msg = {
            "id": self._cmd_seq,
            "cmd": "subscribe",
            "params": {"channels": list(PERPS_CHANNELS),
                       "market_tickers": tickers},
        }
        try:
            await self._ws.send(json.dumps(msg))
            self._subscribed.update(tickers)
        except Exception as ex:
            log.warning("perps ws 订阅失败：%s", ex)

    # ---------------- 消息处理 ----------------
    async def _on_message(self, raw) -> None:
        self.last_msg_ts = time.time()
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        mtype = data.get("type")
        if mtype == "error":
            self.last_error = str(data.get("msg") or data)[:300]
            return
        msg = data.get("msg") or {}
        if mtype == "ticker":
            self.msg_count += 1
            self._on_ticker(msg)
        elif mtype == "trade":
            self.msg_count += 1
            row = self._parse_trade(msg)
            if not row:
                return
            self.trade_count += 1
            self._recent.insert(0, row)
            del self._recent[200:]
            async with self._buf_lock:
                self._buf.append(row)
                need_flush = len(self._buf) >= 50
            if need_flush:
                await self._flush()

    def _on_ticker(self, msg: dict) -> None:
        ticker = msg.get("market_ticker") or msg.get("ticker") or ""
        if not ticker:
            return
        funding = msg.get("funding_rate")
        if not isinstance(funding, dict):
            funding = {}
        ts_ms = _num(msg.get("ts_ms")) or 0.0
        self.latest[ticker] = {
            "ticker": ticker,
            "price": _num(msg.get("price")),
            "bid": _num(msg.get("bid")),
            "ask": _num(msg.get("ask")),
            "bid_size": _num(msg.get("bid_size_fp")),
            "ask_size": _num(msg.get("ask_size_fp")),
            "last_size": _num(msg.get("last_trade_size_fp")),
            "volume": _num(msg.get("volume")),
            "volume_24h": _num(msg.get("volume_24h")),
            "open_interest": _num(msg.get("open_interest")),
            "funding_rate": _num(funding.get("rate")),
            "next_funding_time": funding.get("next_funding_time_ms"),
            "ts": ts_ms / 1000.0 if ts_ms else time.time(),
        }
        self.ticker_count += 1

    def _parse_trade(self, msg: dict) -> Optional[dict]:
        ticker = msg.get("market_ticker") or msg.get("ticker")
        if not ticker:
            return None
        ts_ms = _num(msg.get("ts_ms"))
        ts = int(ts_ms / 1000.0) if ts_ms else int(time.time())
        return {
            "trade_id": str(msg.get("trade_id") or
                            f"{ticker}-{ts_ms}-{msg.get('price')}-{msg.get('count')}"),
            "ticker": ticker,
            "price": _num(msg.get("price")),
            "count": _num(msg.get("count")),
            "side": (msg.get("taker_side") or msg.get("side") or "").lower(),
            "ts": ts,
        }

    async def _flush_periodically(self) -> None:
        while self._running:
            await asyncio.sleep(1.0)
            await self._flush()

    async def _flush(self) -> None:
        async with self._buf_lock:
            if not self._buf:
                return
            batch, self._buf = self._buf, []
        try:
            await asyncio.to_thread(db.save_perps_trades, self.env, batch)
            self.saved_count += len(batch)
        except Exception as ex:
            async with self._buf_lock:
                self._buf = batch + self._buf
            log.warning("perps 成交落库失败：%s", ex)

    # ---------------- 状态快照（UI 用） ----------------
    def snapshot(self) -> dict:
        return {
            "env": self.env,
            "status": self.status,
            "running": self._running,
            "tickers": sorted(self.tickers),
            "subscribed": sorted(self._subscribed),
            "latest": dict(self.latest),
            "recent": list(self._recent[:50]),
            "msg_count": self.msg_count,
            "ticker_count": self.ticker_count,
            "trade_count": self.trade_count,
            "saved_count": self.saved_count,
            "last_msg_ts": self.last_msg_ts,
            "last_error": self.last_error,
        }


class CfbSubscriber:
    """CF Benchmarks 实时指数值订阅（cfbenchmarks_value 频道）。

    - WS: wss://external-api-ws.kalshi.com/trade-api/ws/v2
    - 订阅参数：{"channels":["cfbenchmarks_value"],"index_ids":["BRTI",...]}
    - 消息 data 是 JSON 字符串：{"type":"value","time":ms,"id":"BRTI","value":"..."}
    - 每个 index 每秒一条，批量写入 DuckDB cfb_ticks
    """

    def __init__(self, key_id: str, pem_path: str, env: str = "prod",
                 proxy: Optional[str] = None):
        self.key_id = key_id
        self.env = env if env in CFB_WS_ENDPOINTS else "prod"
        self.url = CFB_WS_ENDPOINTS[self.env]
        self.proxy = proxy
        self._pem_path = pem_path
        self._private_key = None

        self.indices: set[str] = set()
        self.status: str = "stopped"
        self.last_error: str = ""
        self.last_msg_ts: float = 0.0
        self.msg_count: int = 0
        self.value_count: int = 0
        self.saved_count: int = 0
        self.latest: dict[str, dict] = {}

        self._task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._ws = None
        self._running = False
        self._cmd_seq = 0
        self._buf: list[dict] = []
        self._buf_lock = asyncio.Lock()

    def _load_key(self):
        if self._private_key is None:
            from cryptography.hazmat.primitives import serialization
            with open(self._pem_path, "rb") as f:
                self._private_key = serialization.load_pem_private_key(
                    f.read(), password=None)
        return self._private_key

    def _headers(self) -> dict:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        ts_ms = str(int(time.time() * 1000))
        message = (ts_ms + "GET" + CFB_WS_PATH).encode("utf-8")
        signature = self._load_key().sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode(),
        }

    @property
    def running(self) -> bool:
        return self._running

    async def set_indices(self, indices) -> None:
        new = {str(i).strip() for i in indices if i and str(i).strip()}
        if new == self.indices:
            return
        self.indices = new
        if self._ws is not None and self.status == "connected":
            await self._reconnect()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run(), name=f"kalshi-cfb-ws-{self.env}")
        self._flush_task = asyncio.create_task(
            self._flush_periodically(), name=f"kalshi-cfb-flush-{self.env}")

    async def stop(self) -> None:
        self._running = False
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass
        for task in (self._task, self._flush_task):
            if task is not None:
                task.cancel()
        self._task = None
        self._flush_task = None
        self.status = "stopped"
        await self._flush()

    async def _reconnect(self) -> None:
        try:
            if self._ws is not None:
                await self._ws.close()
        except Exception:
            pass

    async def _run(self) -> None:
        import websockets
        backoff = 1.0
        while self._running:
            self.status = "connecting"
            try:
                kwargs = {
                    "additional_headers": self._headers(),
                    "ping_interval": 20,
                    "ping_timeout": 20,
                    "max_size": 4 * 1024 * 1024,
                }
                if self.proxy:
                    kwargs["proxy"] = self.proxy
                async with websockets.connect(self.url, **kwargs) as ws:
                    self._ws = ws
                    self.status = "connected"
                    self.last_error = ""
                    backoff = 1.0
                    if self.indices:
                        await self._send_subscribe(sorted(self.indices))
                    async for raw in ws:
                        if not self._running:
                            break
                        await self._on_message(raw)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                self.status = "error"
                self.last_error = str(ex)[:300]
                log.warning("cfb ws 连接异常：%s", ex)
            finally:
                self._ws = None
                await self._flush()
            if not self._running:
                break
            self.status = "connecting"
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
        self.status = "stopped"

    async def _send_subscribe(self, indices: list[str]) -> None:
        if self._ws is None or not indices:
            return
        self._cmd_seq += 1
        msg = {
            "id": self._cmd_seq,
            "cmd": "subscribe",
            "params": {"channels": [CFB_CHANNEL], "index_ids": indices},
        }
        try:
            await self._ws.send(json.dumps(msg))
        except Exception as ex:
            log.warning("cfb ws 订阅失败：%s", ex)

    async def _on_message(self, raw) -> None:
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return
        if not isinstance(data, dict):
            return
        mtype = data.get("type")
        if mtype == "error":
            self.last_error = str(data.get("msg") or data)[:300]
            return
        if mtype != CFB_CHANNEL:
            return
        self.last_msg_ts = time.time()
        msg = data.get("msg") or {}
        payload = msg.get("data")
        try:
            parsed = json.loads(payload) if isinstance(payload, str) else (payload or {})
        except (TypeError, ValueError):
            parsed = {}
        index_id = (msg.get("index_id") or parsed.get("id") or "").strip()
        value = _num(parsed.get("value"))
        if not index_id or value is None:
            return
        time_ms = _num(parsed.get("time")) or _num(msg.get("received_at"))
        time_ms = int(time_ms) if time_ms else int(time.time() * 1000)
        received = _num(msg.get("received_at")) or time_ms
        avg = msg.get("avg_60s_data")
        if not isinstance(avg, dict):
            avg = {}
        self.msg_count += 1
        self.value_count += 1
        self.latest[index_id] = {
            "index_id": index_id,
            "value": value,
            "time_ms": time_ms,
            "ts": time_ms / 1000.0,
            "received_at": int(received),
            "avg_60s": _num(avg.get("value")),
            "avg_60s_window": avg.get("window_size"),
        }
        row = {
            "index_id": index_id,
            "value": value,
            "time_ms": time_ms,
            "server_time": datetime.fromtimestamp(
                received / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        }
        async with self._buf_lock:
            self._buf.append(row)
            need_flush = len(self._buf) >= 50
        if need_flush:
            await self._flush()

    async def _flush_periodically(self) -> None:
        while self._running:
            await asyncio.sleep(1.0)
            await self._flush()

    async def _flush(self) -> None:
        async with self._buf_lock:
            if not self._buf:
                return
            batch, self._buf = self._buf, []
        try:
            await asyncio.to_thread(db.save_cfb_ticks, self.env, batch)
            self.saved_count += len(batch)
        except Exception as ex:
            async with self._buf_lock:
                self._buf = batch + self._buf
            log.warning("cfb 落库失败：%s", ex)

    def snapshot(self) -> dict:
        return {
            "env": self.env,
            "status": self.status,
            "running": self._running,
            "indices": sorted(self.indices),
            "latest": dict(self.latest),
            "msg_count": self.msg_count,
            "value_count": self.value_count,
            "saved_count": self.saved_count,
            "last_msg_ts": self.last_msg_ts,
            "last_error": self.last_error,
        }


# 按 (env, key_id) 缓存订阅器，避免页面切换时重复建连
_SUBSCRIBERS: dict[tuple[str, str], TradeSubscriber] = {}
_PERPS_SUBSCRIBERS: dict[tuple[str, str], PerpsSubscriber] = {}
_CFB_SUBSCRIBERS: dict[tuple[str, str], CfbSubscriber] = {}


def get_subscriber(key_id: str, pem_path: str, env: str,
                   proxy: Optional[str] = None) -> TradeSubscriber:
    key = (env, key_id)
    sub = _SUBSCRIBERS.get(key)
    if sub is None:
        sub = TradeSubscriber(key_id, pem_path, env, proxy)
        _SUBSCRIBERS[key] = sub
    return sub


def get_perps_subscriber(key_id: str, pem_path: str, env: str,
                         proxy: Optional[str] = None) -> PerpsSubscriber:
    key = (env, key_id)
    sub = _PERPS_SUBSCRIBERS.get(key)
    if sub is None:
        sub = PerpsSubscriber(key_id, pem_path, env, proxy)
        _PERPS_SUBSCRIBERS[key] = sub
    return sub


def get_cfb_subscriber(key_id: str, pem_path: str, env: str,
                       proxy: Optional[str] = None) -> CfbSubscriber:
    key = (env, key_id)
    sub = _CFB_SUBSCRIBERS.get(key)
    if sub is None:
        sub = CfbSubscriber(key_id, pem_path, env, proxy)
        _CFB_SUBSCRIBERS[key] = sub
    return sub


async def stop_all() -> None:
    for sub in list(_SUBSCRIBERS.values()):
        await sub.stop()
    for sub in list(_PERPS_SUBSCRIBERS.values()):
        await sub.stop()
    for sub in list(_CFB_SUBSCRIBERS.values()):
        await sub.stop()
    _SUBSCRIBERS.clear()
    _PERPS_SUBSCRIBERS.clear()
    _CFB_SUBSCRIBERS.clear()
