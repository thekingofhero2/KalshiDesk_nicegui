# -*- coding: utf-8 -*-
"""Kalshi 私有账户 API 封装。

基于本工程内置的 client.KalshiClient（RSA-PSS 签名），补充本系统需要的
余额分布、子账户、成交、行情与下单语义。
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from .client import KalshiClient, KalshiHTTPError, fp_to_float  # noqa: F401

ENDPOINTS = {
    "prod": "https://api.elections.kalshi.com/trade-api/v2",
    "demo": "https://demo-api.kalshi.co/trade-api/v2",
}
ENV_LABEL = {"prod": "生产", "demo": "模拟"}

ACTION_LABEL = {
    "buy_yes": "买入 YES",
    "sell_yes": "卖出 YES",
    "buy_no": "买入 NO",
    "sell_no": "卖出 NO",
}


# ---------------------------------------------------------------------------
# 数值解析：Kalshi 同时存在 _dollars(FixedPointDollars) / _fp(FixedPointCount)
# 与旧版「整数美分」字段，这里统一转成 float 美元 / 浮点数。
# ---------------------------------------------------------------------------
def dec(v) -> Optional[float]:
    """DollarDecimal / 数字字符串 -> float"""
    if v is None or v == "":
        return None
    if isinstance(v, dict):
        for k in ("dollar", "dollars", "value", "amount"):
            if k in v:
                return dec(v[k])
        return None
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _dollar_value(v) -> Optional[float]:
    """DollarDecimal 字段：dict/字符串按美元；整数按美分。"""
    if isinstance(v, int) and not isinstance(v, bool):
        return v / 100.0
    return dec(v)


def money(obj: dict, key: str) -> Optional[float]:
    """优先 <key>_dollars；否则 <key> 按整数美分。"""
    if not isinstance(obj, dict):
        return None
    if f"{key}_dollars" in obj:
        return dec(obj.get(f"{key}_dollars"))
    if key in obj and obj.get(key) is not None:
        v = obj.get(key)
        if isinstance(v, dict):
            return dec(v)
        try:
            return float(v) / 100.0
        except (TypeError, ValueError):
            return None
    return None


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _count(obj: dict, *keys) -> float:
    for k in keys:
        if obj.get(k) is not None and obj.get(k) != "":
            return _num(obj.get(k)) or 0.0
    return 0.0


class DeskAPI:
    """面向控制台的账户 API。"""

    def __init__(self, key_id: str, pem_path: str, env: str = "prod",
                 proxy: Optional[str] = None):
        self.key_id = key_id
        self.env = env if env in ENDPOINTS else "prod"
        self.base_url = ENDPOINTS[self.env]
        self.cli = KalshiClient(key_id, pem_path, base_url=self.base_url, proxy=proxy)
        self._series_cache: list = []
        self._series_ts = 0.0

    # ==== 账户 ====
    def balance(self) -> dict:
        d = self.cli.request("GET", "/portfolio/balance")
        shards = []
        for it in d.get("balance_breakdown") or []:
            if not isinstance(it, dict):
                continue
            shards.append({
                "exchange_index": it.get("exchange_index"),
                "balance": _dollar_value(it.get("balance")) or 0.0,
            })
        shards.sort(key=lambda x: (x["exchange_index"] is None, x["exchange_index"]))
        return {
            "available": money(d, "balance") or 0.0,
            "portfolio_value": money(d, "portfolio_value"),
            "payout": money(d, "payout"),
            "shards": shards,
            "updated_ts": d.get("updated_ts"),
            "raw": d,
        }

    # ==== 子账户 / shard ====
    def subaccount_balances(self) -> list:
        d = self.cli.request("GET", "/portfolio/subaccounts/balances")
        rows = []
        for it in d.get("subaccount_balances") or []:
            if not isinstance(it, dict):
                continue
            rows.append({
                "subaccount": it.get("subaccount_number"),
                "exchange_index": it.get("exchange_index"),
                "balance": _dollar_value(it.get("balance")) or 0.0,
                "updated_ts": it.get("updated_ts"),
                "raw": it,
            })
        rows.sort(key=lambda x: ((x["exchange_index"] if x["exchange_index"] is not None else 0),
                                 (x["subaccount"] if x["subaccount"] is not None else 0)))
        return rows

    def create_subaccount(self, exchange_index: Optional[int] = None) -> dict:
        body = {}
        if exchange_index is not None:
            body["exchange_index"] = int(exchange_index)
        return self.cli.request("POST", "/portfolio/subaccounts", json_body=body)

    def transfer_subaccounts(self, from_sub: int, to_sub: int, amount: float,
                             exchange_index: Optional[int] = None) -> dict:
        body = {
            "client_transfer_id": str(uuid.uuid4()),
            "from_subaccount": int(from_sub),
            "to_subaccount": int(to_sub),
            "amount_cents": int(round(float(amount) * 100)),
        }
        if exchange_index is not None:
            body["exchange_index"] = int(exchange_index)
        return self.cli.request("POST", "/portfolio/subaccounts/transfer", json_body=body)

    def subaccount_transfers(self, limit: int = 50) -> list:
        d = self.cli.request("GET", "/portfolio/subaccounts/transfers",
                             params={"limit": int(limit)})
        rows = []
        for t in d.get("transfers") or []:
            rows.append({
                "transfer_id": t.get("transfer_id"),
                "amount": (_num(t.get("amount_cents")) or 0.0) / 100.0,
                "from_subaccount": t.get("from_subaccount"),
                "to_subaccount": t.get("to_subaccount"),
                "created_ts": t.get("created_ts"),
                "raw": t,
            })
        return rows

    def intra_exchange_transfers(self, limit: int = 50) -> list:
        """跨 shard（exchange instance）转账记录。

        注意：子账户转账走 /portfolio/subaccounts/transfers，看不到这里的记录，
        必须单独查这个端点。amount 字段是美元字符串（如 "3.0000"）。
        """
        d = self.cli.request("GET", "/portfolio/intra_exchange_instance_transfers",
                             params={"limit": int(limit)})
        rows = []
        for t in d.get("transfers") or []:
            if not isinstance(t, dict):
                continue
            rows.append({
                "transfer_id": t.get("transfer_id"),
                "amount": _num(t.get("amount")) or 0.0,
                "from_shard": t.get("source_exchange_shard"),
                "to_shard": t.get("destination_exchange_shard"),
                "source": t.get("source"),
                "destination": t.get("destination"),
                "status": t.get("status"),
                "created_ts": t.get("created_ts"),
                "raw": t,
            })
        return rows

    def transfer_across_shards(self, from_shard: int, to_shard: int, amount: float,
                               source: str = "event_contract",
                               destination: str = "event_contract",
                               source_subaccount: int = 0,
                               destination_subaccount: int = 0) -> dict:
        """跨 shard（exchange instance）转账；金额单位为 centicents（1 美元=10000）。"""
        body = {
            "source": source,
            "destination": destination,
            "source_exchange_shard": int(from_shard),
            "destination_exchange_shard": int(to_shard),
            "amount": int(round(float(amount) * 10000)),
            "source_subaccount": int(source_subaccount),
            "destination_subaccount": int(destination_subaccount),
        }
        return self.cli.request("POST", "/portfolio/intra_exchange_instance_transfer",
                                json_body=body)

    # ==== 持仓 ====
    def positions(self) -> list:
        out, cursor = [], None
        for _ in range(5):
            params = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            d = self.cli.request("GET", "/portfolio/positions", params=params)
            for p in d.get("market_positions") or d.get("positions") or []:
                pos = _count(p, "position_fp", "position")
                if not pos:
                    continue
                out.append({
                    "ticker": p.get("ticker"),
                    "position": pos,
                    "yes_qty": pos if pos > 0 else 0.0,
                    "no_qty": -pos if pos < 0 else 0.0,
                    "exposure": money(p, "market_exposure") or 0.0,
                    "realized_pnl": money(p, "realized_pnl") or 0.0,
                    "fees": money(p, "fees_paid") or 0.0,
                    "total_traded": money(p, "total_traded") or 0.0,
                    "resting": int(_count(p, "resting_orders_count")),
                    "exchange_index": p.get("exchange_index"),
                    "updated_ts": p.get("last_updated_ts"),
                    "raw": p,
                })
            cursor = d.get("cursor")
            if not cursor:
                break
        out.sort(key=lambda x: abs(x["exposure"]), reverse=True)
        return out

    # ==== 订单 ====
    def orders(self, status: Optional[str] = None, ticker: Optional[str] = None,
               days: Optional[int] = None, max_pages: Optional[int] = 3,
               min_ts: Optional[int] = None) -> list:
        """拉订单列表。

        :param min_ts: 只返回 created_time >= min_ts 的订单（秒级 UTC 时间戳）。
                       传了 min_ts 就忽略 days。
        """
        effective_min_ts = min_ts if min_ts else (
            int(time.time() - days * 86400) if days else None)
        out = []
        for o in self.cli.iter_orders(status=status or None, ticker=ticker or None,
                                      limit=200, max_pages=max_pages,
                                      min_ts=effective_min_ts, timeout=10):
            price = dec(o.get("price"))
            if price is None:
                price = money(o, "yes_price")
            side = (o.get("side") or "").lower()
            action = (o.get("action") or "").lower()

            # Kalshi 二元市场是全额抵押的：只有 YES / NO 两种持仓。
            # 订单用 side + action 两个维度描述，必须组合才能还原真实押注方向：
            #   side=yes action=buy  → 买 YES（押 YES）
            #   side=yes action=sell → 卖 YES = 买 NO（押 NO）★ 用户点"买 NO"实际发的是这个
            #   side=no  action=buy  → 买 NO（押 NO）
            #   side=no  action=sell → 卖 NO = 买 YES（押 YES）
            raw_pos = None
            if side in ("yes", "bid"):
                raw_pos = "yes"
            elif side in ("no", "ask"):
                raw_pos = "no"
            if raw_pos and action == "sell":
                position_side = "no" if raw_pos == "yes" else "yes"
            else:
                position_side = raw_pos
            side_txt = {"yes": "买 YES", "no": "买 NO"}.get(position_side, side or "—")
            out.append({
                "order_id": o.get("order_id"),
                "client_order_id": o.get("client_order_id"),
                "ticker": o.get("ticker"),
                "side": side,
                "action": action,
                "position_side": position_side,
                "side_txt": side_txt,
                "price": price,
                "count": _count(o, "count", "initial_count_fp", "initial_count"),
                "filled": _count(o, "fill_count_fp", "fill_count"),
                "remaining": _count(o, "remaining_count_fp", "remaining_count"),
                "status": o.get("status"),
                "tif": o.get("time_in_force"),
                "fees": (money(o, "taker_fees") or 0.0) + (money(o, "maker_fees") or 0.0),
                "subaccount": o.get("subaccount"),
                "exchange_index": o.get("exchange_index"),
                "created": o.get("created_time") or o.get("created_ts"),
                "raw": o,
            })
        return out

    def get_order(self, order_id: str) -> dict:
        """按 order_id 取订单详情（含 status / fill_count_fp / remaining_count_fp）。"""
        return self.cli.get_order(order_id)

    def cancel(self, order_id: str, ticker: str) -> dict:
        return self.cli.cancel_order(order_id, ticker=ticker)

    def place(self, ticker: str, side: str, yes_price: float, count: int,
              tif: str = "immediate_or_cancel", post_only: bool = False,
              subaccount: Optional[int] = None) -> dict:
        """V2 单 book 下单：side=bid(买 YES)/ask(卖 YES)，price 为 YES 价。"""
        body = {
            "ticker": ticker,
            "client_order_id": str(uuid.uuid4()),
            "side": side,
            "count": str(int(count)),
            "price": f"{float(yes_price):.4f}",
            "self_trade_prevention_type": "taker_at_cross",
            "time_in_force": tif,
        }
        if post_only:
            body["post_only"] = True
        if subaccount is not None:
            body["subaccount"] = int(subaccount)
        return self.cli.request("POST", "/portfolio/events/orders", json_body=body, timeout=15)

    # ==== 成交 ====
    def fills(self, ticker: Optional[str] = None, days: Optional[int] = None,
              max_pages: int = 3, min_ts: Optional[int] = None) -> list:
        """拉成交列表。

        :param min_ts: 只返回 created_time >= min_ts 的成交（秒级 UTC）。
        """
        out, cursor = [], None
        effective_min_ts = min_ts if min_ts else (
            int(time.time() - days * 86400) if days else None)
        for _ in range(max_pages):
            params = {"limit": 200}
            if ticker:
                params["ticker"] = ticker
            if effective_min_ts:
                params["min_ts"] = effective_min_ts
            if cursor:
                params["cursor"] = cursor
            d = self.cli.request("GET", "/portfolio/fills", params=params)
            for f in d.get("fills") or []:
                side = f.get("side")
                price = money(f, "yes_price") if side != "no" else money(f, "no_price")
                if price is None:
                    price = money(f, "yes_price")
                out.append({
                    "fill_id": f.get("fill_id") or f.get("trade_id"),
                    "trade_id": f.get("trade_id"),
                    "order_id": f.get("order_id"),
                    "ticker": f.get("market_ticker") or f.get("ticker"),
                    "side": side,
                    "action": f.get("action"),
                    "price": price,
                    "count": _count(f, "count_fp", "count"),
                    "is_taker": f.get("is_taker"),
                    "fees": dec(f.get("fees_dollars")) or money(f, "fees"),
                    "created": f.get("created_time") or f.get("ts"),
                    "subaccount": f.get("subaccount"),
                    "exchange_index": f.get("exchange_index"),
                    "raw": f,
                })
            cursor = d.get("cursor")
            if not cursor:
                break
        return out

    # ==== 结算 ====
    def settlements(self, ticker: Optional[str] = None, limit: int = 200) -> list:
        """市场结算记录（已结算市场才有；同一 ticker 可能多条，按 shard 区分）。"""
        params = {"limit": int(limit)}
        if ticker:
            params["ticker"] = ticker
        d = self.cli.request("GET", "/portfolio/settlements", params=params)
        out = []
        for s in d.get("settlements") or []:
            if not isinstance(s, dict):
                continue
            out.append({
                "ticker": s.get("ticker"),
                "event_ticker": s.get("event_ticker"),
                "market_result": s.get("market_result"),
                "yes_count": _count(s, "yes_count_fp", "yes_count"),
                "yes_cost": money(s, "yes_total_cost") or 0.0,
                "no_count": _count(s, "no_count_fp", "no_count"),
                "no_cost": money(s, "no_total_cost") or 0.0,
                "revenue": money(s, "revenue") or 0.0,
                "fee": dec(s.get("fee_cost")) or 0.0,
                "settled_time": s.get("settled_time"),
                "exchange_index": s.get("exchange_index"),
                "raw": s,
            })
        return out

    # ==== 市场目录 ====
    def series_catalog(self, force: bool = False) -> list:
        """全部系列（分类 / 周期 / 标题），缓存 10 分钟。

        Kalshi 目前忽略 limit 参数直接返回全部约 1.5 万条（无 cursor），
        但仍按 cursor 做防御性翻页，避免将来服务端收紧 limit 时目录被截断
        导致 Crypto→hourly 这类分类下漏掉 KXBTCD 等系列。
        """
        if not force and self._series_cache and time.time() - self._series_ts < 600:
            return self._series_cache
        out: list = []
        seen: set = set()
        cursor = ""
        for _ in range(50):                       # 安全上限：50 页 × 1000
            params = {"limit": 1000}
            if cursor:
                params["cursor"] = cursor
            d = self.cli.request("GET", "/series", params=params)
            batch = d.get("series") or []
            for s in batch:
                ticker = s.get("ticker")
                if not ticker or ticker in seen:
                    continue
                seen.add(ticker)
                out.append({
                    "ticker": ticker,
                    "title": s.get("title") or ticker,
                    "category": (s.get("category") or "").strip(),
                    "frequency": (s.get("frequency") or "").strip(),
                })
            cursor = d.get("cursor") or ""
            if not cursor or not batch:
                break
        self._series_cache, self._series_ts = out, time.time()
        return out

    # 月份缩写在 Kalshi event_ticker 里的映射（KXBTCD-26NOV1206 → 2026-11-12 06:00）
    _MONTHS = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04", "MAY": "05",
               "JUN": "06", "JUL": "07", "AUG": "08", "SEP": "09", "OCT": "10",
               "NOV": "11", "DEC": "12"}

    @classmethod
    def event_time_label(cls, event_ticker: str) -> str:
        """把 event_ticker 尾部的 YY MON DD HH 解析成可读时间标签。

        KXBTCD-26NOV1206 → "11/12 06:00"；解析不了就原样返回 event_ticker。
        """
        if not event_ticker:
            return ""
        tail = event_ticker.rsplit("-", 1)[-1]
        if len(tail) >= 9:
            yy, mon, dd, hh = tail[:2], tail[2:5], tail[5:7], tail[7:9]
            if mon in cls._MONTHS and dd.isdigit() and hh.isdigit():
                return f"{cls._MONTHS[mon]}/{dd} {hh}:00"
        return event_ticker

    def markets_by_series(self, series_ticker: str, active_only: bool = True,
                          pages: int = 1) -> list:
        """某系列下的市场 ticker。

        关键：`/markets?series_ticker=X` 不带 status 时，历史已结算（finalized）
        市场会把真正的活跃市场挤出 limit 窗口——KXBTCD 系列有上万条历史市场，
        200 条里只有 12 条 active，导致下拉列表几乎为空。

        因此 active_only=True 时必须传 status=open（event 级枚举，实际效果是
        只返回仍处于 open event 下的市场），并把 limit 提到 1000 上限。
        KXBTCD 这类 hourly 系列每小时一个 event，单页 1000 条约覆盖 5–6 个 event。

        :param pages: 拉几页（每页 1000）。默认 1，够覆盖近期 event。
        """
        out: list = []
        seen: set = set()
        cursor, page = "", 0
        while page < max(1, pages):
            params = {"series_ticker": series_ticker, "limit": 1000}
            if active_only:
                params["status"] = "open"
            if cursor:
                params["cursor"] = cursor
            d = self.cli.request("GET", "/markets", params=params)
            markets = d.get("markets") or []
            for m in markets:
                if active_only and m.get("status") != "active":
                    continue
                ticker = m.get("ticker")
                if not ticker or ticker in seen:
                    continue
                seen.add(ticker)
                sub = (m.get("yes_sub_title") or "").strip()
                title = (m.get("title") or m.get("subtitle") or ticker).strip()
                ev = m.get("event_ticker") or ""
                ts = self.event_time_label(ev)
                # 同类 strike 市场 title 完全相同（如 KXBTCD 全是 "Bitcoin price on ..."），
                # 必须带上 event 时间 + strike 才能区分
                label = f"{ts} · {sub}" if sub else f"{ts} · {title}"
                out.append({
                    "ticker": ticker,
                    "event_ticker": ev,
                    "title": title,
                    "label": label.strip(" ·"),
                    "status": m.get("status"),
                })
            cursor = d.get("cursor") or ""
            page += 1
            if not cursor or not markets:
                break
        return out

    def subscription_markets(self, series_ticker: str) -> list:
        """市场级 WS 订阅：当前 open 及 30 分钟内开盘的 unopened tickers。"""
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        out: set[str] = set()

        def parse_time(value):
            if not value:
                return None
            try:
                dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                return None

        for status in ("open", "unopened"):
            cursor = None
            for _ in range(3):
                page = self.cli.get_markets_page(
                    series_ticker, status=status, cursor=cursor, limit=200)
                markets = page.get("markets") or []
                for market in markets:
                    ticker = market.get("ticker")
                    close = parse_time(market.get("close_time"))
                    if not ticker or not close or close < now - timedelta(minutes=1):
                        continue
                    if status == "unopened":
                        open_at = parse_time(market.get("open_time"))
                        # 优先按真实开盘时间；无该字段时沿用短周期市场的收盘时间窗口。
                        too_late = (open_at > now + timedelta(minutes=30)) if open_at else (
                            close - timedelta(minutes=15) > now + timedelta(minutes=30))
                        if too_late:
                            continue
                    out.add(ticker)
                cursor = page.get("cursor") or ""
                if not cursor or not markets:
                    break
        return sorted(out)

    def event_series(self, event_ticker: str) -> str:
        """事件所属系列 ticker。"""
        d = self.cli.request("GET", f"/events/{event_ticker}")
        return ((d.get("event") or {}).get("series_ticker") or "").strip()

    # ==== CF Benchmarks（Kalshi 代理转发）====
    @staticmethod
    def _parse_cf_payload(d) -> Optional[dict]:
        """兼容 Kalshi 转发返回，抽出最新 {index_id, value, time_ms, server_time}。

        新版 Kalshi 返回统一包一层 data：
            {"data": {"serverTime": "...", "payload": [{"value","time"}, ...]}}
        /values 的 payload 是最近一段时间的逐秒数组，取 time 最大的一条；
        /summaries 的 payload 是 {index_id: {"value","time",...}}。
        """
        if not isinstance(d, dict):
            return None
        # 解包 Kalshi data envelope（最多三层，兼容 data.data）
        for _ in range(3):
            if isinstance(d.get("data"), dict) and "serverTime" in d["data"]:
                d = d["data"]
            elif isinstance(d.get("data"), dict) and "payload" in d["data"]:
                d = d["data"]
            else:
                break
        server_time = d.get("serverTime") or d.get("server_time")
        cand = None
        p = d.get("payload")
        if isinstance(p, list):
            items = [x for x in p if isinstance(x, dict) and x.get("value") is not None]
            if items:
                cand = max(items, key=lambda x: _num(x.get("time")) or 0)
        elif isinstance(p, dict):
            if p.get("value") is not None:
                cand = p
            else:
                items = [v for v in p.values()
                         if isinstance(v, dict) and v.get("value") is not None]
                if items:
                    cand = max(items, key=lambda x: _num(x.get("time")) or 0)
        elif d.get("value") is not None:
            cand = d
        elif isinstance(d.get("values"), list) and d["values"]:
            v = d["values"][0]
            cand = v if isinstance(v, dict) else None
        if not isinstance(cand, dict) or cand.get("value") is None:
            return None
        raw_val = cand.get("value")
        try:
            val = float(raw_val)
        except (TypeError, ValueError):
            return None
        tm = cand.get("time", cand.get("time_ms", cand.get("timestamp")))
        try:
            tm = int(tm) if tm is not None else None
        except (TypeError, ValueError):
            tm = None
        return {
            "index_id": cand.get("id") or cand.get("index_id"),
            "value": val,
            "time_ms": tm,
            "server_time": server_time,
        }

    def cf_values(self, index_id: str) -> Optional[dict]:
        """CF Benchmarks 单一 index 当前值。

        Kalshi 路由 GET /trade-api/v2/cfbenchmarks/values?id=<INDEX_ID>
        转发到 https://www.cfbenchmarks.com/api/v1/values?id=<INDEX_ID>。
        失败（503 / 维护中 / 无 license）时返回 None，不抛异常。
        """
        if not index_id:
            return None
        try:
            d = self.cli.request("GET", "/cfbenchmarks/values",
                                 params={"id": index_id})
        except Exception:
            return None
        r = self._parse_cf_payload(d)
        if r:
            r["index_id"] = r.get("index_id") or index_id
        return r

    def cf_probe(self, index_id: str = "BRTI") -> tuple[bool, str]:
        """探测转发端点可用性，返回 (是否可用, 人类可读原因)。

        用于 UI 展示失败原因（503 / 维护中 / 结构不识别），
        避免用户只看到笼统的"等待数据"。
        """
        try:
            d = self.cli.request("GET", "/cfbenchmarks/values",
                                 params={"id": index_id})
        except Exception as ex:
            return False, str(ex)[:200]
        r = self._parse_cf_payload(d)
        if r:
            return True, f"OK value={r['value']}"
        return False, f"返回结构无法解析：{str(d)[:160]}"

    def cf_index_for_series(self, series_ticker: str) -> Optional[str]:
        """从 Kalshi 该系列下任一 open event 的 settlement_sources 提取 CF 指数名。

        这是最权威的来源——event 的 settlement_sources 里直接写着
        url = https://www.cfbenchmarks.com/data/indices/BRTI，
        比自己猜 BTCUSD_RTI 之类可靠得多（BTC 实际就是 BRTI）。
        """
        if not series_ticker:
            return None
        try:
            d = self.cli.request("GET", "/events",
                                 params={"status": "open",
                                         "series_ticker": series_ticker,
                                         "limit": 5})
        except Exception:
            return None
        import re as _re
        for e in d.get("events") or []:
            for s in (e.get("settlement_sources") or []):
                url = s.get("url") or ""
                m = _re.search(r"/indices/([A-Za-z0-9_]+)", url)
                if m:
                    return m.group(1)
        return None

    def cf_summaries(self, index_ids: list[str]) -> list[dict]:
        """批量 CF index 摘要（尝试走 Kalshi 转发 /cfbenchmarks/summaries）。

        这个端点是否被 Kalshi 转发未知，所以做个 best-effort：
        - 如果 Kalshi 有转发 → 一次拿多个 index，节省调用次数
        - 如果 404/503 → 上层回退到逐个 cf_values 循环
        返回: 每个元素同 cf_values 格式，外加可能的 change_24h 等摘要字段
        """
        if not index_ids:
            return []
        ids_str = ",".join(index_ids)
        try:
            d = self.cli.request("GET", "/cfbenchmarks/summaries",
                                 params={"ids": ids_str})
        except Exception:
            return []
        if not isinstance(d, dict):
            return []
        for _ in range(3):
            if isinstance(d.get("data"), dict):
                d = d["data"]
            else:
                break
        payload = d.get("payload")
        out = []
        if isinstance(payload, dict) and isinstance(payload.get("summaries"), list):
            for s in payload["summaries"]:
                if not isinstance(s, dict) or s.get("value") is None:
                    continue
                out.append({
                    "index_id": s.get("id"),
                    "value": float(s.get("value")),
                    "time_ms": int(s.get("time")) if s.get("time") is not None else None,
                    "change_24h": s.get("change_24h"),
                    "server_time": d.get("serverTime"),
                })
            return out
        if isinstance(payload, dict):
            # /summaries 实际返回 {index_id: {value,time,last24Hours}}
            for idx in index_ids:
                s = payload.get(idx)
                if not isinstance(s, dict) or s.get("value") is None:
                    continue
                out.append({
                    "index_id": idx,
                    "value": float(s.get("value")),
                    "time_ms": int(s.get("time")) if s.get("time") is not None else None,
                    "server_time": d.get("serverTime"),
                })
        return out

    # ==== 行情 ====
    def quote(self, ticker: str) -> dict:
        m = self.cli.get_market(ticker) or {}
        q = {
            "ticker": ticker,
            "event_ticker": m.get("event_ticker"),
            "title": m.get("title") or m.get("subtitle") or "",
            "status": m.get("status"),
            "result": m.get("result"),
            "close_time": m.get("close_time"),
            "open_time": m.get("open_time"),
            "yes_bid": money(m, "yes_bid"),
            "yes_ask": money(m, "yes_ask"),
            "no_bid": money(m, "no_bid"),
            "no_ask": money(m, "no_ask"),
            "last": money(m, "last_price"),
            # 结构化目标价（CF 面板用）：ticker 里不一定带价格
            "floor_strike": m.get("floor_strike"),
            "cap_strike": m.get("cap_strike"),
            "strike_type": m.get("strike_type"),
        }
        if None in (q["yes_bid"], q["yes_ask"]):
            try:
                book = self._orderbook_quote(ticker)
            except Exception:
                book = {}
            for k in ("yes_bid", "yes_ask", "no_bid", "no_ask"):
                if q[k] is None and book.get(k) is not None:
                    q[k] = book[k]
        if q["no_bid"] is None and q["yes_ask"] is not None:
            q["no_bid"] = round(1.0 - q["yes_ask"], 4)
        if q["no_ask"] is None and q["yes_bid"] is not None:
            q["no_ask"] = round(1.0 - q["yes_bid"], 4)
        return q

    def _orderbook_quote(self, ticker: str) -> dict:
        ob = (self.cli.get_orderbook(ticker, depth=10) or {}).get("orderbook") or {}

        def prices(side):
            arr = ob.get(side) or ob.get(f"{side}_dollars") or []
            out = []
            for row in arr:
                if not row:
                    continue
                p = row[0]
                if isinstance(p, str):
                    x = _num(p)
                    if x is None:
                        continue
                    if x > 1.0:
                        x /= 100.0
                else:
                    x = float(p)
                    if isinstance(p, int) or x > 1.0:
                        x /= 100.0
                out.append(x)
            return out

        yes, no = prices("yes"), prices("no")
        yes_bid = max(yes) if yes else None
        no_bid = max(no) if no else None
        return {
            "yes_bid": yes_bid,
            "yes_ask": round(1.0 - no_bid, 4) if no_bid is not None else None,
            "no_bid": no_bid,
            "no_ask": round(1.0 - yes_bid, 4) if yes_bid is not None else None,
        }

    # ==== 交易动作 -> book side ====
    @staticmethod
    def to_book(action: str, price: float) -> tuple:
        """把「买入/卖出 YES/NO + 该合约价格」映射为 (book_side, YES 价)。"""
        if action == "buy_yes":
            return "bid", float(price)
        if action == "sell_yes":
            return "ask", float(price)
        if action == "buy_no":
            return "ask", round(1.0 - float(price), 4)
        if action == "sell_no":
            return "bid", round(1.0 - float(price), 4)
        raise ValueError(f"未知交易动作: {action}")

    @staticmethod
    def best_price(q: dict, action: str) -> Optional[float]:
        idx = {
            "buy_yes": "yes_ask",
            "sell_yes": "yes_bid",
            "buy_no": "no_ask",
            "sell_no": "no_bid",
        }[action]
        return q.get(idx)
