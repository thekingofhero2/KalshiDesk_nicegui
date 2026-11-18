# -*- coding: utf-8 -*-
"""Kalshi 账户管理系统（NiceGUI）。

启动：python -m kalshi_desk
浏览器打开 http://127.0.0.1:8090
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from nicegui import app, events, run, ui

from . import ai as ai_client
from . import db, store, ws
from .api import ACTION_LABEL, ENV_LABEL, ENDPOINTS, DeskAPI

CSS = """
:root { --kd-bg:#07080b; --kd-panel:#0c0e13; --kd-line:#181c24;
        --kd-line-strong:#242a36; --kd-text:#e8ebf1; --kd-muted:#79808f;
        --kd-accent:#35e0a1;
        --kd-mono:"JetBrains Mono","Cascadia Mono","SFMono-Regular",Consolas,monospace; }
html, body { background: var(--kd-bg); }
body { color: var(--kd-text); font-size: 13.5px; letter-spacing: .005em;
       -webkit-font-smoothing: antialiased;
       font-family: "Inter","SF Pro Text","PingFang SC","Microsoft YaHei",sans-serif;
       background-image:
         radial-gradient(900px 420px at 16% -12%, rgba(53,224,161,.055), transparent 62%),
         linear-gradient(rgba(255,255,255,.017) 1px, transparent 1px),
         linear-gradient(90deg, rgba(255,255,255,.017) 1px, transparent 1px);
       background-size: auto, 44px 44px, 44px 44px;
       background-attachment: fixed; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: #20242d; border-radius: 8px; }
::-webkit-scrollbar-track { background: transparent; }

.kd-shell { max-width: 1480px; margin: 0 auto; padding: 0 28px 64px; gap: 0; }
.kd-topbar { position: sticky; top: 0; z-index: 20; padding: 12px 0 13px;
             background: rgba(7,8,11,.88); backdrop-filter: blur(12px);
             border-bottom: 1px solid var(--kd-line); margin-bottom: 22px; }
.kd-wordmark { font-family: var(--kd-mono); font-size: 12px; font-weight: 700;
               letter-spacing: .26em; color: var(--kd-text); }
.kd-mut { color: var(--kd-muted); }
.kd-key { font-family: var(--kd-mono); font-size: 10.5px; color: var(--kd-muted);
          border: 1px solid var(--kd-line); border-radius: 4px; padding: 1px 6px; }

.kd-nav { width: 192px; flex-shrink: 0; position: sticky; top: 74px; gap: 1px;
          padding-top: 2px; }
.kd-nav-item { width: 100%; justify-content: flex-start; color: var(--kd-muted);
               border-radius: 6px; padding: 8px 12px; font-size: 12.5px;
               letter-spacing: .02em; position: relative; }
.kd-nav-item:hover { background: rgba(255,255,255,.04); color: var(--kd-text); }
.kd-nav-active { background: rgba(53,224,161,.075)!important;
                 color: var(--kd-accent)!important; }
.kd-nav-active::before { content: ""; position: absolute; left: -10px; top: 9px;
                         bottom: 9px; width: 2px; border-radius: 2px;
                         background: var(--kd-accent);
                         box-shadow: 0 0 12px rgba(53,224,161,.65); }
.kd-content { flex: 1; min-width: 0; gap: 20px; }

.kd-page-head { padding-bottom: 16px; border-bottom: 1px solid var(--kd-line); }
.kd-eyebrow { font-family: var(--kd-mono); font-size: 10px; letter-spacing: .24em;
              color: var(--kd-accent); opacity: .9; }
.kd-page-title { font-size: 21px; font-weight: 650; letter-spacing: -.015em;
                 line-height: 1.2; margin-top: 2px; }
.kd-page-desc { font-size: 12px; color: var(--kd-muted); }

.kd-metric-row { border-top: 1px solid var(--kd-line);
                 border-bottom: 1px solid var(--kd-line); }
.kd-metric { flex: 1; padding: 18px 20px; border-left: 1px solid var(--kd-line); }
.kd-metric:first-child { border-left: none; padding-left: 0; }
.kd-metric-label { font-family: var(--kd-mono); font-size: 10px; letter-spacing: .16em;
                   text-transform: uppercase; color: var(--kd-muted); }
.kd-metric-value { font-family: var(--kd-mono); font-size: 25px; font-weight: 600;
                   letter-spacing: -.02em; font-variant-numeric: tabular-nums;
                   margin-top: 8px; line-height: 1.1; }
.kd-metric-sub { font-family: var(--kd-mono); font-size: 10.5px; color: var(--kd-muted);
                 margin-top: 5px; }
.kd-section { font-family: var(--kd-mono); font-size: 10.5px; letter-spacing: .18em;
              text-transform: uppercase; color: var(--kd-muted);
              display: flex; align-items: center; gap: 8px; padding-top: 2px; }
.kd-section::before { content: ""; width: 3px; height: 10px; border-radius: 1px;
                      background: var(--kd-accent); display: inline-block; }

.q-table { background: transparent; }
.q-table thead tr { background: transparent; }
.q-table thead th { color: var(--kd-muted); font-family: var(--kd-mono);
                    font-size: 10px; letter-spacing: .12em; text-transform: uppercase;
                    border-bottom: 1px solid var(--kd-line-strong)!important;
                    padding: 10px 12px; }
.q-table tbody td { border-bottom: 1px solid rgba(255,255,255,.04)!important;
                    font-size: 12.5px; padding: 9px 12px; }
.q-table tbody tr:hover { background: rgba(53,224,161,.045)!important; cursor: pointer; }
.q-table td, .q-table th { font-variant-numeric: tabular-nums; }
.q-table td { font-family: var(--kd-mono); }

.q-tab { min-height: 38px; font-size: 12px; letter-spacing: .04em; padding: 0 14px; }
.q-tabs { border-bottom: 1px solid var(--kd-line); }
.q-tab--active { color: var(--kd-accent)!important; }
.q-tab__indicator { height: 1px!important; background: var(--kd-accent)!important; }

.q-field--outlined .q-field__control { border-radius: 6px;
                                      background: rgba(255,255,255,.018); }
.q-field--outlined .q-field__control:before { border-color: var(--kd-line-strong); }
.q-btn { border-radius: 6px; letter-spacing: .03em; }
.q-dialog .q-card, .kd-dialog { background: #0b0d12!important;
                                border: 1px solid var(--kd-line-strong);
                                border-radius: 10px!important; }
.q-notification { background: #11141a; border: 1px solid var(--kd-line-strong);
                  border-radius: 8px; font-size: 12.5px; }

.kd-pos { color: var(--kd-accent); }
.kd-neg { color: #ff6b7a; }
.kd-actions .q-btn__content { white-space: nowrap; }
.kd-chat-list { max-height: calc(100vh - 330px); min-height: 240px; overflow-y: auto;
                padding-right: 6px; }
.kd-bubble { padding: 9px 13px; border-radius: 8px; background: #0e1116;
             border-left: 2px solid var(--kd-line-strong); max-width: 680px;
             line-height: 1.55; }
.kd-chat-meta { font-family: var(--kd-mono); font-size: 10px; letter-spacing: .06em;
                color: var(--kd-muted); }
.kd-auth { min-height: 100vh; display: flex; align-items: center; justify-content: center;
           padding: 24px; }
.kd-auth-inner { width: 372px; max-width: 94vw; padding: 30px 28px;
                 border: 1px solid var(--kd-line-strong); border-radius: 12px;
                 background: rgba(12,14,19,.82); backdrop-filter: blur(10px);
                 box-shadow: 0 30px 90px rgba(0,0,0,.45); }
.kd-fade { animation: kdFade .3s cubic-bezier(.22,.7,.3,1) both; }
@keyframes kdFade { from { opacity: 0; transform: translateY(7px); }
                    to { opacity: 1; transform: none; } }
"""

TAB_OVER, TAB_POS, TAB_ORD, TAB_FILL, TAB_WS, TAB_SUB, TAB_MO, TAB_SET = (
    "概览", "持仓", "订单", "成交", "数据订阅", "子账户 / 分片", "动量机器人", "设置")

PAGE_OVER, PAGE_TRADE, PAGE_ANALY, PAGE_AI, PAGE_SET, PAGE_CHAT = (
    "概览", "交易", "分析", "AI", "系统设置", "聊天室")
PAGES = (PAGE_OVER, PAGE_TRADE, PAGE_ANALY, PAGE_AI, PAGE_SET, PAGE_CHAT)
PAGE_ICONS = {
    PAGE_OVER: "insights",
    PAGE_TRADE: "candlestick_chart",
    PAGE_ANALY: "query_stats",
    PAGE_AI: "smart_toy",
    PAGE_SET: "settings",
    PAGE_CHAT: "forum",
}
PAGE_META = {
    PAGE_OVER: ("ACCOUNT", "账户概览", "余额、敞口与子账户分片，读取本地最新快照"),
    PAGE_TRADE: ("EXECUTION", "交易", "持仓、订单、成交与子账户；手动下单按分类与周期筛选"),
    PAGE_ANALY: ("ANALYTICS", "分析", "近 30 天成交与已结算盈亏，统计自本地 DuckDB"),
    PAGE_AI: ("INTELLIGENCE", "AI 分析", "基于本地库数据提问，模型与密钥在系统设置中配置"),
    PAGE_SET: ("CONTROL", "系统设置", "同步、连接、代理、AI 模型与用户权限"),
    PAGE_CHAT: ("COMMS", "聊天室", "同一环境下的用户共享这段讨论"),
}
_STATIC_READY = False

FREQ_ORDER = ["fifteen_min", "hourly", "daily", "weekly", "monthly",
              "quarterly", "annual", "one_off", "custom", "often", "irregular"]
FREQ_CN = {
    "fifteen_min": "15 分钟", "hourly": "每小时", "daily": "每日",
    "weekly": "每周", "monthly": "每月", "quarterly": "每季",
    "annual": "每年", "one_off": "一次性", "one_time": "一次性",
    "custom": "不定期", "often": "高频", "irregular": "不定期",
    "adhoc": "不定期",
}
CATEGORY_CN = {
    "Crypto": "加密货币", "Sports": "体育", "Politics": "政治",
    "Elections": "选举", "Economics": "经济", "Financials": "金融",
    "Companies": "公司", "Entertainment": "娱乐", "Culture": "文化",
    "World": "国际", "Climate and Weather": "气候天气", "Health": "健康",
    "Science and Technology": "科技", "Transportation": "交通",
    "Commodities": "大宗商品", "Mentions": "提及次数", "Social": "社会",
    "AI": "人工智能", "Business": "商业", "Education": "教育",
    "Exotics": "另类", "other": "其他", "Other": "其他",
}


def usd(x: Optional[float], signed: bool = False) -> str:
    if x is None:
        return "—"
    body = f"${abs(x):,.2f}"
    if x < 0:
        return f"-{body}"
    return f"+{body}" if signed and x > 0 else body


def perps_price(x: Optional[float]) -> str:
    """Perps 价格保留 4 位小数（tick_size 常见为 0.0001）。"""
    return f"${x:,.4f}" if x is not None else "—"


# CF index → (perps ticker, 合约对应 BTC 数量换算倍数)
# KXBTCPERP 每张 = 0.0001 BTC，价格 × 10000 = BTC/USD
CF_PERPS_MAP = {"BRTI": ("KXBTCPERP", 10000.0)}


def fmt_ts(v) -> str:
    if v is None or v == "":
        return "—"
    try:
        if isinstance(v, (int, float)):
            t = float(v)
            if t > 2e10:
                t /= 1000.0
            return datetime.fromtimestamp(t).strftime("%m-%d %H:%M:%S")
        s = str(v)
        if s.isdigit():          # 库里 created_ts 存成 VARCHAR 的秒级时间戳
            return fmt_ts(int(s))
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).astimezone().strftime("%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return str(v)[:19]


def fmt_dt(v, fmt: str = "%m-%d %H:%M:%S") -> str:
    """格式化已是 datetime 的值（DuckDB 视图返回的三时区列），带兜底。"""
    if v is None or v == "":
        return "—"
    if isinstance(v, datetime):
        return v.strftime(fmt)
    return fmt_ts(v)


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ===== 动量机器人引擎：模块级单例状态 =====
# 必须放在模块级：NiceGUI 每个页面请求都会 new 一个 DeskUI，如果把引擎任务和
# running 标志存在实例上，页面一刷新就会出现「UI 显示已停止但引擎还在跑」，
# 而且旧实例的任务永远无法从新页面停掉。模块级共享后启停一致。
#   running   : 引擎是否运行中（唯一权威标志）
#   task      : 引擎协程
#   ui        : 最近一次渲染页面的 DeskUI（引擎用它拿 api / notify / 配置）
#   watchers  : buy_order_id -> 动量单上下文（一局未完不释放）
#   cooldown  : ticker -> 下次可下单时间戳
_MO_ENGINE: dict = {
    "running": False,
    "task": None,
    "ui": None,
    "last_tick": 0.0,
    "watchers": {},
    "cooldown": {},
    "started_at": 0.0,
    "last_ws_ensure": 0.0,
}


class DeskUI:
    def __init__(self):
        self.authed = False
        self.current_user: Optional[dict] = None
        self.page = PAGE_OVER
        self.user = ""
        self.api: Optional[DeskAPI] = None
        self.sess: Optional[dict] = None
        self.auto = True
        self.busy = False
        self.cooldown = 0.0  # 429 限流后的自动刷新恢复时间点
        self._trade_opening = False  # open_trade 重入保护：防多开交易对话框
        self._trade_momentum = False  # 当前对话框是否为动量模式
        self._mo_dir = "yes"          # 动量面板：检测到的上涨腿
        self._mo_delta = 0.0          # 动量面板：近 60s 价差
        self._mo_timer = None         # 动量面板刷新计时器
        # 动量单 watcher / 冷却：与模块级引擎状态共享同一份 dict，
        # 保证页面刷新后仍能看到活动中 watcher、冷却也继续生效。
        self._momentum_watchers = _MO_ENGINE["watchers"]
        self._mo_cooldown_until = _MO_ENGINE["cooldown"]
        self._mo_cfg_dlg: Optional[ui.dialog] = None
        self.mo_cfg: dict = store.load_config()["momentum"]
        # 注册为引擎当前 UI 宿主（引擎是模块级单例，总是指向最新页面实例）
        _MO_ENGINE["ui"] = self
        self._ws_panel_busy = False
        self._perps_panel_busy = False
        self._trade_chart_busy = False
        self._trade_chart_ticker = ""
        self._trade_chart_timer = None
        self._cf_quote_timer = None   # 下单框 CF 面板实时刷新计时器
        self._catalog = []           # 市场目录（series）内存缓存，跨多次下单复用
        self._catalog_env: Optional[str] = None   # 上面这份缓存属于哪个环境
        # CF Benchmarks 刷新状态
        self._cf_index_ids: set[str] = set()   # 当前活跃的 CF indexId 集合（动态发现）
        self._cf_last_discovery: float = 0.0    # 上次扫描 active 市场的时间戳
        self._cf_fail_until: float = 0.0        # 转发层不可用时的熔断截止时间
        self._cf_last_error: str = ""           # 最近一次 CF 拉取失败原因（UI 展示）
        self.cfb_latest: dict[str, dict] = {}    # 最新 CF 快照缓存（UI 渲染用）
        self._cf_live_seq = -1                   # WS 消息计数，变化时才重绘
        self.ticks = 0
        self.status_filter: Optional[str] = "resting"
        self.orders_ticker = ""
        self.fills_ticker = ""
        self.fills_days: Optional[int] = 3
        # 订单/成交查询防重入（防抖）
        self._orders_busy = False
        self._orders_lock = asyncio.Lock()   # 订单刷新串行化，切换时排队而非丢弃
        self._orders_pending = 0             # 排队中的刷新数，归零才关 loading
        self._fills_busy = False
        self._pos_busy = False
        self._pem_text: Optional[str] = None
        self.proxy_cfg: dict = store.load_config()["proxy"]
        self.refresh_interval: int = store.load_config()["refresh_interval"]
        self.timer = None
        self.state = {"balance": {}, "positions": [], "orders": [], "fills": [], "subs": []}
        self.pos_by_ticker: dict = {}
        self.order_by_id: dict = {}

    # ================= 页面骨架 =================
    def start(self) -> None:
        ui.dark_mode(True)
        ui.colors(primary="#3ee0a0", positive="#3ee0a0", negative="#ff6b7a",
                  info="#8b93a3")
        ui.add_css(CSS)
        chat_dir = store.DATA_DIR / "chat_images"
        chat_dir.mkdir(parents=True, exist_ok=True)
        global _STATIC_READY
        if not _STATIC_READY:
            app.add_static_files("/chat-images", str(chat_dir))
            _STATIC_READY = True
        self.trade_dlg = ui.dialog().props("persistent")
        self.trade_dlg.on_value_change(self._on_trade_dialog_change)
        self.order_dlg = ui.dialog().props("persistent")
        with ui.column().classes("kd-shell w-full") as self.root:
            pass

        self.rebuild()
        self.timer = ui.timer(self.refresh_interval, self.tick)
        # 首页必须先交付；DuckDB 锁等待/迁移不能阻塞 NiceGUI 的 3 秒响应窗口。
        asyncio.create_task(self._init_database())

    async def _init_database(self) -> None:
        try:
            await run.io_bound(db.init)
        except Exception as ex:
            self.notify(f"本地数据库无法打开（可能已被另一实例占用）：{ex}", type="negative")

    def _new_api(self, key_id: str, pem_path: str, env: str) -> DeskAPI:
        """按当前代理配置构造 API 客户端。"""
        return DeskAPI(key_id, pem_path, env, proxy=store.proxy_url(self.proxy_cfg))

    def rebuild(self) -> None:
        self.root.clear()
        with self.root:
            if not self.authed:
                self.build_auth_login()
            elif self.api is None and self.is_admin:
                self.build_login()
            else:
                self.build_main()

    def _el(self, name: str):
        """安全访问 UI 元素：属性不存在或已被 rebuild/clear 销毁则返回 None。"""
        el = getattr(self, name, None)
        if el is None:
            return None
        try:
            return None if el.is_deleted else el
        except Exception:
            return None

    # ================= 工作台登录 =================
    def build_auth_login(self) -> None:
        with ui.column().classes("kd-auth w-full"):
            with ui.column().classes("kd-auth-inner gap-4 kd-fade"):
                ui.label("KALSHI DESK").classes("kd-wordmark text-left w-full")
                with ui.column().classes("gap-1"):
                    ui.label("登录工作台").classes("text-3xl font-semibold tracking-tight")
                    ui.label("本地账户，凭据只保存在本机 data/config.json。") \
                        .classes("text-sm kd-mut")
                self.au_user = ui.input("用户名").classes("w-full") \
                    .props("dense outlined autofocus")
                self.au_pass = ui.input("密码", password=True, password_toggle_button=True) \
                    .classes("w-full").props("dense outlined")
                ui.button("登录", on_click=self.do_auth_login) \
                    .props("unelevated color=primary").classes("w-full")
                ui.label("默认账户 admin / admin，可在「系统设置 → 用户管理」中新增或改密。") \
                    .classes("text-xs kd-mut")
        self.au_pass.on("keydown.enter", self.do_auth_login)

    async def do_auth_login(self) -> None:
        username = (self.au_user.value or "").strip()
        user = store.check_login(username, self.au_pass.value or "")
        if not user:
            ui.notify("用户名或密码错误", type="negative")
            return
        self.authed, self.user, self.current_user = True, username, user
        self.page = PAGE_OVER
        self._pem_text = None
        ui.notify(f"欢迎，{username}（{self.role_label}）", type="positive")
        await self.auto_connect()
        self.rebuild()

    async def auto_connect(self) -> None:
        """登录工作台后尝试用本机已保存的 Kalshi 私钥自动连接。"""
        sess = store.load_session()
        if not sess:
            return
        try:
            api = self._new_api(sess["key_id"], sess["pem_path"], sess["env"])
            bal = await run.io_bound(api.balance)
            await run.io_bound(db.save_balance, sess["env"], sess["key_id"], bal)
            self.api, self.sess = api, sess
        except Exception as ex:
            self.login_error = f"自动连接 Kalshi 失败：{ex}"

    # ================= 登录 =================
    def build_login(self) -> None:
        with ui.column().classes("kd-auth w-full"):
            with ui.column().classes("kd-auth-inner gap-4 kd-fade"):
                ui.label("KALSHI DESK").classes("kd-wordmark text-left w-full")
                with ui.column().classes("gap-1"):
                    ui.label("连接 Kalshi 账户").classes("text-3xl font-semibold tracking-tight")
                    ui.label("上传 API 私钥后可同步余额、持仓、订单与成交，并直接下单。") \
                        .classes("text-sm kd-mut")
                if getattr(self, "login_error", ""):
                    ui.label(self.login_error).classes("text-red-400 text-sm")
                self.pem_name = ui.label("未选择文件").classes("text-xs kd-mut")
                ui.upload(label="上传 PEM 私钥", auto_upload=True, max_file_size=2_000_000,
                          on_upload=self.on_pem_upload).props("accept=.pem,.key,.txt flat bordered")
                self.key_input = ui.input(
                    "API Key ID", placeholder="Kalshi 控制台创建 API Key 时生成的 Key ID"
                ).classes("w-full").props("dense outlined")
                self.env_select = ui.select(
                    {"prod": "生产环境", "demo": "模拟环境"},
                    value=getattr(self, "login_env", None)
                    or (self.sess or {}).get("env", "prod"),
                    label="环境",
                ).classes("w-full").props("dense outlined")
                with ui.row().classes("w-full items-center gap-2"):
                    ui.button("连接账户", icon="login", on_click=self.do_login) \
                        .props("unelevated color=primary").classes("flex-1")
                    ui.button("诊断 Key", icon="troubleshoot", on_click=self.diagnose_key) \
                        .props("outline dense")
                self.diag_label = ui.label("").classes("text-xs kd-mut whitespace-pre-line")
                with ui.expansion("网络代理设置（SOCKS5）", icon="lan") \
                        .classes("w-full text-sm"):
                    self.build_proxy_box()
                ui.separator()
                ui.label(f"私钥仅保存在本机 {store.DATA_DIR}，不会发送到任何第三方服务。") \
                    .classes("text-xs kd-mut")

    async def on_pem_upload(self, e: events.UploadEventArguments) -> None:
        data = await e.file.read()
        try:
            text = store.normalize_pem(data)
        except Exception as ex:
            ui.notify(f"PEM 解析失败：{ex}", type="negative")
            return
        self._pem_text = text
        self.pem_name.set_text(f"已选择：{e.file.name}")
        ui.notify("私钥已载入", type="positive")

    async def do_login(self) -> None:
        key_id = (self.key_input.value or "").strip()
        env = self.env_select.value or "prod"
        await self._connect(key_id, env)

    async def diagnose_key(self) -> None:
        """用当前 Key 分别请求生产 / 模拟余额，判断 Key 属于哪个环境。"""
        key_id = (self.key_input.value or "").strip()
        if not self._pem_text:
            ui.notify("请先上传 .pem 私钥文件", type="warning")
            return
        if not key_id:
            ui.notify("请填写 API Key ID", type="warning")
            return
        self.diag_label.set_text("诊断中…")
        try:
            staged = store.stage_pem(self._pem_text)
        except Exception as ex:
            self.diag_label.set_text(f"私钥不可用：{ex}")
            return
        lines = []
        try:
            for env in ("prod", "demo"):
                try:
                    api = self._new_api(key_id, str(staged), env)
                    bal = await run.io_bound(api.balance)
                    lines.append(f"{ENV_LABEL[env]}：认证通过，可用余额 {usd(bal.get('available'))}")
                except Exception as ex:
                    msg = str(ex)
                    if " 401" in msg or "401:" in msg:
                        msg = "认证失败（401，Key 不属于该环境或与私钥不匹配）"
                    lines.append(f"{ENV_LABEL[env]}：{msg[:160]}")
        finally:
            try:
                staged.unlink()
            except OSError:
                pass
        self.diag_label.set_text("\n".join(lines))

    async def _connect(self, key_id: str, env: str) -> None:
        key_id = (key_id or "").strip()
        if not self._pem_text:
            ui.notify("请先上传 .pem 私钥文件", type="warning")
            return
        if not key_id:
            ui.notify("请填写 API Key ID（Kalshi 控制台创建 Key 时生成的 UUID）",
                      type="warning")
            return
        staged = None
        try:
            staged = store.stage_pem(self._pem_text)
            api = self._new_api(key_id, str(staged), env)
            bal = await run.io_bound(api.balance)
            await run.io_bound(db.save_balance, env, key_id, bal)
            sess = store.save_session(key_id, self._pem_text, env)
            api = self._new_api(key_id, sess["pem_path"], env)
        except Exception as ex:
            ui.notify(f"连接失败：{ex}", type="negative")
            return
        finally:
            if staged is not None:
                try:
                    staged.unlink()
                except OSError:
                    pass
        self.api, self.sess = api, sess
        self.login_error = ""
        self._pem_text = None
        ui.notify("已连接 Kalshi 账户", type="positive")
        self.rebuild()

    # ================= 主界面 =================
    def build_main(self) -> None:
        env = self.api.env if self.api else (self.sess or {}).get("env", "local")
        with ui.row().classes("kd-topbar w-full items-center gap-3"):
            ui.label("KALSHI DESK").classes("kd-wordmark")
            ui.badge(ENV_LABEL.get(env, env)).props(
                "color=negative flat" if env == "prod" else "color=info flat")
            if self.api and self.sess:
                ui.label(store.mask_key(self.sess["key_id"])).classes("kd-key")
            ui.space()
            if self.api:
                ui.switch("自动刷新", value=self.auto,
                          on_change=lambda e: setattr(self, "auto", bool(e.value)))
                self.interval_label = ui.label(f"每 {self.refresh_interval} 秒") \
                    .classes("text-xs kd-mut")
                ui.button("刷新", icon="refresh",
                          on_click=lambda: self.refresh_all(manual=True)).props("flat dense")
            self.updated_label = ui.label("本地快照").classes("text-xs kd-mut")
            ui.button(icon="logout", on_click=self.do_logout) \
                .props("flat round dense") \
                .tooltip(f"退出（{self.user} · {self.role_label}）")

        with ui.row().classes("w-full no-wrap items-start gap-6"):
            self.build_sidebar()
            self.body = ui.column().classes("kd-content")
        self.show_page(self.page)
        if self.is_admin:
            with ui.page_sticky(position="bottom-right", x_offset=24, y_offset=24):
                ui.button(f"切到{'模拟' if env == 'prod' else '生产'}环境",
                          icon="swap_horiz", on_click=self.switch_env) \
                    .props("unelevated rounded color=primary") \
                    .classes("shadow-lg").tooltip("一键切换模拟 / 生产环境")
        if self.api:
            asyncio.create_task(self.load_cached())
            asyncio.create_task(self._preload_catalog())   # 后台预热市场目录

    async def _preload_catalog(self) -> None:
        """后台预加载市场目录到内存，避免点「手动交易」时才同步拉取。"""
        if not self.api:
            return
        if self._catalog and self._catalog_env == self.api.env:
            return
        try:
            catalog = await run.io_bound(db.series_catalog, self.api.env)
            if not catalog:
                catalog = await run.io_bound(self.api.series_catalog)
                await run.io_bound(db.save_series_catalog, self.api.env, catalog)
            self._catalog = [s for s in catalog
                             if s["category"] and "test" not in s["category"].lower()]
            self._catalog_env = self.api.env
        except Exception:
            pass   # 预热失败不影响后续手动交易时重新加载

    @property
    def is_admin(self) -> bool:
        return bool(self.current_user and self.current_user.get("role") == "admin")

    @property
    def role_label(self) -> str:
        return "管理员" if self.is_admin else "只读"

    def allowed_pages(self) -> list:
        return list(PAGES) if self.is_admin else [PAGE_OVER, PAGE_CHAT]

    def build_sidebar(self) -> None:
        with ui.column().classes("kd-nav"):
            self.nav_buttons = {}
            for name in self.allowed_pages():
                btn = ui.button(name, icon=PAGE_ICONS[name],
                                on_click=lambda n=name: self.show_page(n)) \
                    .props("flat no-caps align=left").classes("kd-nav-item")
                self.nav_buttons[name] = btn
            ui.space()
            ui.label(f"{self.user}\n{self.role_label}").classes("text-xs kd-mut px-3")

    def _reset_page_refs(self) -> None:
        for attr in ("c_avail", "c_avail_ts", "c_expo", "c_pnl", "c_rest", "c_subs",
                     "shard_table", "sub_mini", "pos_table", "order_table",
                     "fill_table", "sub_table", "tr_table", "ai_answer",
                     "chat_box", "chat_preview", "an_metrics", "an_table",
                     "x_bal_hint", "ws_status", "ws_stats", "ws_error", "ws_table",
                     "cf_row", "cf_src_label", "cf_ws_status",
                     "cfb_card", "cf_spread_card", "cf_spread_title",
                     "cf_spread_range", "cf_spread_value",
                     "cf_spread_hint", "cf_spread_chart",
                     "perps_status", "perps_stats", "perps_select", "perps_price",
                     "perps_book", "perps_funding", "perps_error", "perps_table",
                     "sub_cat_select", "sub_freq_select", "sub_ser_select",
                     "mo_dir_label", "mo_trend_label", "mo_px_label", "mo_tp_label",
                     "mo_mult_input", "mo_hint",
                     "cfg_cat", "cfg_series", "cfg_tick_table", "cfg_tick_count",
                     "mo_open_table", "mo_hist_table", "mo_log_table",
                     "mo_status", "mo_toggle", "mo_stat_total", "mo_stat_wins",
                     "mo_stat_tps", "mo_stat_cancel", "mo_stat_pnl",
                     "mo_stat_watchers", "mo_stat_last",
                     "_page_spinner", "_orders_spinner", "_orders_sync_label",
                     "status_toggle"):
            setattr(self, attr, None)

    def show_page(self, name: str) -> None:
        if name not in self.allowed_pages():
            name = PAGE_OVER
        self.page = name
        for btn_name, btn in getattr(self, "nav_buttons", {}).items():
            if btn_name == name:
                btn.classes(add="kd-nav-active")
            else:
                btn.classes(remove="kd-nav-active")
        self._reset_page_refs()
        self.body.clear()
        with self.body:
            eyebrow, title, desc = PAGE_META[name]
            with ui.column().classes("kd-page-head w-full gap-1 kd-fade"):
                ui.label(eyebrow).classes("kd-eyebrow")
                ui.label(title).classes("kd-page-title")
                ui.label(desc).classes("kd-page-desc")
            if name == PAGE_OVER:
                self.build_overview()
                self.render_balance()
                self.render_subs()
            elif name == PAGE_TRADE:
                self.build_trade()
            elif name == PAGE_ANALY:
                self.build_analytics()
            elif name == PAGE_AI:
                self.build_ai_page()
            elif name == PAGE_SET:
                self.build_settings()
            elif name == PAGE_CHAT:
                self.build_chat()
        # 切页后异步刷新该页数据（带 loading），不阻塞界面构建
        asyncio.create_task(self._after_page_shown(name))

    async def _after_page_shown(self, name: str) -> None:
        """页面构建完成后异步加载最新数据，期间表格显示 loading 遮罩。"""
        if not self.api:
            return
        try:
            if name == PAGE_TRADE:
                # 交易页默认停在持仓 tab，而 tab 的 on_change 不会在初始时触发
                await self.refresh_positions()
            elif name == PAGE_OVER:
                # 概览从本地库重读（毫秒级），不额外打 API
                state = await run.io_bound(
                    db.load_state, self.api.env, self.sess["key_id"], self.status_filter,
                    self.orders_ticker or None, self.fills_ticker or None,
                    self.fills_days, False)
                if state:
                    self.state.update(state)
                    self.render_balance()
                    self.render_positions()
                    self.render_subs()
        except Exception:
            pass

    async def load_cached(self) -> None:
        """先用本地库数据渲染一遍，再等接口同步覆盖。"""
        if not self.api:
            return
        try:
            state = await run.io_bound(
                db.load_state, self.api.env, self.sess["key_id"], self.status_filter,
                self.orders_ticker or None, self.fills_ticker or None, self.fills_days, True)
        except Exception:
            return
        self.state.update(state)
        self.render_balance()
        self.render_positions()
        self.render_orders()
        self.render_subs()
        self.render_fills()
        # 从 DuckDB 恢复 CF 快照（登录后立即可见，不必等下次 API 同步）
        try:
            self.cfb_latest = await run.io_bound(
                db.cfb_latest, self.api.env) or {}
        except Exception:
            self.cfb_latest = {}
        # 登录后立即启动 CFB 实时订阅（不等下一轮 60s 刷新）
        try:
            await self._cf_discover()
            await self._ensure_cfb_sub()
        except Exception:
            pass
        self.render_cf_overview()

    def build_trade(self) -> None:
        with ui.tabs().classes("w-full") as tabs:
            ui.tab(TAB_POS, icon="account_balance_wallet").props("no-caps inline-label")
            ui.tab(TAB_ORD, icon="receipt_long").props("no-caps inline-label")
            ui.tab(TAB_FILL, icon="history").props("no-caps inline-label")
            ui.tab(TAB_WS, icon="stream").props("no-caps inline-label")
            ui.tab(TAB_SUB, icon="call_split").props("no-caps inline-label")
            ui.tab(TAB_MO, icon="auto_graph").props("no-caps inline-label")
        with ui.tab_panels(tabs, value=TAB_POS).classes("w-full kd-fade") \
                .style("background: transparent"):
            with ui.tab_panel(TAB_POS):
                self.build_positions()
                self.render_positions()
            with ui.tab_panel(TAB_ORD):
                self.build_orders()
                self.render_orders()
            with ui.tab_panel(TAB_FILL):
                self.build_fills()
                self.render_fills()
            with ui.tab_panel(TAB_WS):
                self.build_data_subscription()
            with ui.tab_panel(TAB_SUB):
                self.build_subaccounts()
                self.render_subs()
            with ui.tab_panel(TAB_MO):
                self.build_momentum_bot()
        tabs.on_value_change(lambda e: asyncio.create_task(self._on_trade_tab(e.value)))

    async def _on_trade_tab(self, name: str) -> None:
        """切换交易页子页签：立即刷新对应数据（持仓/订单只信 API 最新）。"""
        if not self.api:
            return
        if name == TAB_POS:
            await self.refresh_positions()
        elif name == TAB_ORD:
            await self.refresh_orders()
        elif name == TAB_FILL:
            await self.refresh_fills()
        elif name == TAB_WS:
            await self.refresh_subscription_panel()
        elif name == TAB_SUB:
            await self.refresh_transfers()
        elif name == TAB_MO:
            await self.refresh_momentum_panel()

    # ---------- 动量机器人 ----------
    def _ws_subscriber(self) -> ws.TradeSubscriber:
        return ws.get_subscriber(
            self.sess["key_id"], self.sess["pem_path"], self.api.env,
            proxy=store.proxy_url(self.proxy_cfg))

    def build_data_subscription(self) -> None:
        with ui.row().classes("w-full items-center gap-2"):
            ui.label("WebSocket 实时成交").classes("kd-section")
            self.ws_status = ui.label("未连接").classes("kd-key")
            self.ws_stats = ui.label("").classes("text-xs kd-mut")
            ui.space()
            self._api_btn("启动连接", icon="play_arrow", coro=self.start_subscription) \
                .props("flat dense")
            self._api_btn("停止连接", icon="stop", coro=self.stop_subscription) \
                .props("flat dense")
        self.ws_error = ui.label("").classes("text-xs text-red-400")
        ui.label("只需选择市场：每 15 秒自动发现当前及即将开盘的 ticker，新窗口自动订阅，旧窗口自动移除。") \
            .classes("text-xs kd-mut")

        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            self.sub_cat_select = ui.select({}, label="品类").classes("w-48") \
                .props("dense outlined")
            self.sub_freq_select = ui.select({}, label="周期").classes("w-40") \
                .props("dense outlined")
            self._api_btn(icon="refresh", coro=self.reload_subscription_catalog) \
                .props("flat dense").tooltip("从 Kalshi 刷新市场目录")
        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            self.sub_ser_select = ui.select({}, label="市场（选择后自动管理 ticker）", with_input=True) \
                .classes("flex-1").props("dense outlined")
            self._api_btn("订阅市场", icon="add", coro=self.add_subscription) \
                .props("unelevated")

        with ui.row().classes("w-full items-center gap-2"):
            ui.label("已订阅市场").classes("kd-section")
            ui.space()
            self._api_btn("取消选中订阅", icon="remove", coro=self.remove_subscriptions) \
                .props("flat dense")
        self.ws_table = ui.table(
            columns=[
                {"name": "series", "label": "市场", "field": "series", "align": "left"},
                {"name": "tickers", "label": "自动订阅 ticker", "field": "tickers", "align": "left"},
                {"name": "price", "label": "最新成交", "field": "price", "align": "right"},
                {"name": "last_ticker", "label": "成交 ticker", "field": "last_ticker", "align": "left"},
                {"name": "time", "label": "成交时间 / 最近刷新", "field": "time", "align": "right"},
            ], rows=[], row_key="series", selection="multiple", pagination=10,
        ).classes("w-full")

        ui.separator()
        with ui.row().classes("w-full items-center gap-2"):
            ui.label("Kalshi Perps / Invest 实时行情").classes("kd-section")
            self.perps_status = ui.label("未连接").classes("kd-key")
            self.perps_stats = ui.label("").classes("text-xs kd-mut")
            ui.space()
            self._api_btn("刷新市场", icon="refresh", coro=self.load_perps_markets) \
                .props("flat dense")
            self._api_btn("启动", icon="play_arrow", coro=self.start_perps) \
                .props("flat dense")
            self._api_btn("停止", icon="stop", coro=self.stop_perps) \
                .props("flat dense")
        ui.label("独立 perps 交易所（external-api-margin-ws.kalshi.com），"
                 "订阅 ticker + trade 频道；BTC 永续 ticker 为 KXBTCPERP。") \
            .classes("text-xs kd-mut")
        with ui.row().classes("w-full gap-3 items-end no-wrap"):
            self.perps_select = ui.select({"KXBTCPERP": "KXBTCPERP"},
                                          label="Perps 市场", value="KXBTCPERP",
                                          with_input=True) \
                .classes("flex-1").props("dense outlined")
        with ui.row().classes("w-full gap-4 items-center"):
            self.perps_price = ui.label("—").classes("text-lg font-semibold kd-mono")
            self.perps_book = ui.label("").classes("text-xs kd-mut")
            self.perps_funding = ui.label("").classes("text-xs kd-mut")
        self.perps_error = ui.label("").classes("text-xs text-red-400")
        self.perps_table = ui.table(
            columns=[
                {"name": "time", "label": "时间", "field": "time", "align": "left"},
                {"name": "price", "label": "价格", "field": "price", "align": "right"},
                {"name": "count", "label": "数量", "field": "count", "align": "right"},
                {"name": "side", "label": "方向", "field": "side", "align": "right"},
            ], rows=[], row_key="trade_id", pagination=8,
        ).classes("w-full")

        self.sub_cat_select.on_value_change(lambda e: self._on_sub_category(e.value))
        self.sub_freq_select.on_value_change(lambda _: self._apply_sub_series_filter())
        ui.timer(2.0, self.refresh_subscription_panel)
        ui.timer(2.0, self.refresh_perps_panel)
        asyncio.create_task(self._init_subscription_panel())
        asyncio.create_task(self._init_perps_panel())

    async def _init_subscription_panel(self) -> None:
        if not (self.api and self._el("sub_cat_select")):
            return
        try:
            if self._catalog and self._catalog_env == self.api.env:
                catalog = self._catalog
            else:
                catalog = await run.io_bound(db.series_catalog, self.api.env)
                if not catalog:
                    catalog = await run.io_bound(self.api.series_catalog)
                    await run.io_bound(db.save_series_catalog, self.api.env, catalog)
                self._catalog = [s for s in catalog if s.get("category")
                                 and "test" not in s["category"].lower()]
                self._catalog_env = self.api.env
                catalog = self._catalog
        except Exception as ex:
            self.notify(f"市场目录加载失败：{ex}", type="negative")
            return
        select = self._el("sub_cat_select")
        if not select:
            return
        cats = sorted({s["category"] for s in catalog if s.get("category")})
        select.options = {c: CATEGORY_CN.get(c, c) for c in cats}
        select.value = "Crypto" if "Crypto" in cats else (cats[0] if cats else None)
        select.update()
        self._on_sub_category(select.value)
        await self.refresh_subscription_panel()

    def _on_sub_category(self, category: Optional[str]) -> None:
        freq_select = self._el("sub_freq_select")
        if not freq_select:
            return
        freqs = self._freqs_for(category)
        freq_select.options = {f: FREQ_CN.get(f, f) for f in freqs}
        freq_select.value = freqs[0] if freqs else None
        freq_select.update()
        self._apply_sub_series_filter()

    def _apply_sub_series_filter(self) -> None:
        series = self._el("sub_ser_select")
        if not series:
            return
        series.options = self._series_options(
            self.sub_cat_select.value, self.sub_freq_select.value)
        series.value = None
        series.update()

    async def reload_subscription_catalog(self) -> None:
        if not self.api:
            return
        try:
            catalog = await run.io_bound(self.api.series_catalog, True)
            await run.io_bound(db.save_series_catalog, self.api.env, catalog)
        except Exception as ex:
            self.notify(f"市场目录刷新失败：{ex}", type="negative")
            return
        self._catalog = [s for s in catalog if s.get("category")
                         and "test" not in s["category"].lower()]
        self._catalog_env = self.api.env
        await self._init_subscription_panel()
        self.notify(f"市场目录已刷新（{len(catalog)} 个系列）", type="positive")

    async def start_subscription(self) -> None:
        if not (self.api and self.sess):
            return
        sub = self._ws_subscriber()
        await sub.start()
        self.notify("WebSocket 正在连接", type="info")
        await self.refresh_subscription_panel()

    async def stop_subscription(self) -> None:
        if not (self.api and self.sess):
            return
        await self._ws_subscriber().stop()
        self.notify("WebSocket 已停止，订阅列表已保留", type="info")
        await self.refresh_subscription_panel()

    async def add_subscription(self) -> None:
        select = self._el("sub_ser_select")
        series_ticker = (select.value or "").strip() if select else ""
        if not series_ticker:
            self.notify("请先选择要订阅的市场", type="warning")
            return
        sub = self._ws_subscriber()
        await sub.add_series(series_ticker)
        await sub.start()
        select.value = None
        select.update()
        count = len(sub.snapshot()["series_tickers"].get(series_ticker) or [])
        self.notify(f"已订阅 {series_ticker}：当前 {count} 个 ticker，之后自动切换", type="positive")
        await self.refresh_subscription_panel()

    async def remove_subscriptions(self) -> None:
        table = self._el("ws_table")
        if not table:
            return
        series = {r.get("series") for r in (table.selected or [])}
        if not series:
            self.notify("请先在表格中勾选要取消的市场", type="warning")
            return
        sub = self._ws_subscriber()
        await sub.set_series(sub.series - series)
        table.selected = []
        self.notify(f"已取消 {len(series)} 个市场及其自动 ticker 订阅", type="positive")
        await self.refresh_subscription_panel()

    async def refresh_subscription_panel(self) -> None:
        if self._ws_panel_busy or not (self.api and self.sess and self._el("ws_table")):
            return
        self._ws_panel_busy = True
        try:
            sub = self._ws_subscriber()
            snap = sub.snapshot()
            tickers = snap["tickers"]
            latest = await run.io_bound(db.market_trades_latest, self.api.env, tickers) \
                if tickers else {}
            total = await run.io_bound(db.market_trades_count, self.api.env)
            table = self._el("ws_table")
            if not table:
                return
            selected = {r.get("series") for r in (table.selected or [])}
            rows = []
            for series in snap["series"]:
                active = snap["series_tickers"].get(series) or []
                trades = [latest[t] for t in active if latest.get(t)]
                last = max(trades, key=lambda r: r.get("ts") or 0) if trades else {}
                shown = ", ".join(active[:3]) + (" …" if len(active) > 3 else "")
                rows.append({
                    "series": series,
                    "tickers": f"{len(active)} 个 · {shown or '等待发现'}",
                    "price": usd(last.get("price")) if last else "—",
                    "last_ticker": last.get("ticker") or "—",
                    "time": (fmt_ts(last.get("ts")) if last else
                             f"刷新 {fmt_ts(snap['last_market_refresh'])}"),
                })
            table.rows = rows
            table.selected = [r for r in rows if r["series"] in selected]
            table.update()
            status_text = {"connected": "已连接", "connecting": "连接中",
                           "error": "连接异常", "stopped": "已停止"}.get(
                               snap["status"], snap["status"])
            if el := self._el("ws_status"):
                el.set_text(status_text)
            if el := self._el("ws_stats"):
                el.set_text(f"市场 {len(snap['series'])} · 自动 ticker {len(tickers)} · "
                            f"收到 {snap['msg_count']} · 本次落库 {snap['saved_count']} · "
                            f"库内累计 {total}")
            if el := self._el("ws_error"):
                el.set_text("；".join(x for x in (
                    snap["last_error"], snap["last_market_error"]) if x))
        except Exception as ex:
            if el := self._el("ws_error"):
                el.set_text(str(ex)[:300])
        finally:
            self._ws_panel_busy = False

    # ---------- Perps（Kalshi Invest）实时行情 ----------
    def _perps_subscriber(self) -> ws.PerpsSubscriber:
        return ws.get_perps_subscriber(
            self.sess["key_id"], self.sess["pem_path"], self.api.env,
            proxy=store.proxy_url(self.proxy_cfg))

    async def _init_perps_panel(self) -> None:
        if not (self.api and self.sess):
            return
        await self.load_perps_markets(silent=True)
        await self.refresh_perps_panel()

    async def load_perps_markets(self, silent: bool = False) -> None:
        if not (self.api and self.sess):
            return
        try:
            rows = await run.io_bound(self._perps_subscriber().markets)
        except Exception as ex:
            if el := self._el("perps_error"):
                el.set_text(f"perps 市场加载失败：{str(ex)[:280]}")
            if not silent:
                self.notify(f"perps 市场加载失败：{ex}", type="negative")
            return
        select = self._el("perps_select")
        if select is None:
            return
        options = {r["ticker"]: (f'{r["ticker"]} · {r["title"]}'
                                 if r["title"] else r["ticker"]) for r in rows}
        select.options = options
        if select.value not in options:
            select.value = ("KXBTCPERP" if "KXBTCPERP" in options else
                            (rows[0]["ticker"] if rows else None))
        select.update()
        if not silent:
            self.notify(f"perps 市场已刷新（{len(rows)} 个）", type="positive")

    async def start_perps(self) -> None:
        if not (self.api and self.sess):
            return
        select = self._el("perps_select")
        ticker = ((select.value if select else "") or "KXBTCPERP").strip().upper()
        sub = self._perps_subscriber()
        await sub.set_tickers({ticker})
        await sub.start()
        self.notify(f"Perps 订阅已启动：{ticker}", type="info")
        await self.refresh_perps_panel()

    async def stop_perps(self) -> None:
        if not (self.api and self.sess):
            return
        await self._perps_subscriber().stop()
        self.notify("Perps 订阅已停止", type="info")
        await self.refresh_perps_panel()

    async def refresh_perps_panel(self) -> None:
        if self._perps_panel_busy or not (self.api and self.sess
                                          and self._el("perps_table")):
            return
        self._perps_panel_busy = True
        try:
            snap = self._perps_subscriber().snapshot()
            select = self._el("perps_select")
            ticker = ((select.value if select else "") or
                      (snap["tickers"][0] if snap["tickers"] else "") or "KXBTCPERP")
            row = snap["latest"].get(ticker) or {}
            if el := self._el("perps_price"):
                el.set_text(perps_price(row.get("price")))
            if el := self._el("perps_book"):
                el.set_text(f"Bid {perps_price(row.get('bid'))} × {row.get('bid_size') or 0:g}"
                            f"  Ask {perps_price(row.get('ask'))} × {row.get('ask_size') or 0:g}")
            if el := self._el("perps_funding"):
                rate = row.get("funding_rate")
                next_ms = row.get("next_funding_time")
                text = f"资金费率 {rate * 100:.4f}%" if rate is not None else ""
                if next_ms:
                    text += f" · 下次 {fmt_ts(next_ms / 1000)}"
                el.set_text(text)

            try:
                trades = await run.io_bound(db.perps_trades_recent,
                                            self.api.env, ticker, 20)
            except Exception:
                trades = [r for r in snap["recent"] if r.get("ticker") == ticker][:20]
            total = await run.io_bound(db.perps_trades_count, self.api.env)
            table = self._el("perps_table")
            if table is None:
                return
            table.rows = [{
                "trade_id": r.get("trade_id") or "",
                "time": fmt_ts(r.get("ts")),
                "price": perps_price(r.get("price")),
                "count": f"{r.get('count') or 0:g}",
                "side": ("主动买" if r.get("side") == "bid" else
                         "主动卖" if r.get("side") == "ask" else (r.get("side") or "")),
            } for r in trades]
            table.update()

            status_text = {"connected": "已连接", "connecting": "连接中",
                           "error": "连接异常", "stopped": "已停止"}.get(
                               snap["status"], snap["status"])
            if el := self._el("perps_status"):
                el.set_text(status_text)
            if el := self._el("perps_stats"):
                el.set_text(f"{ticker} · ticker {snap['ticker_count']} · "
                            f"trade {snap['trade_count']} · "
                            f"本次落库 {snap['saved_count']} · 库内累计 {total}")
            if el := self._el("perps_error"):
                el.set_text(snap["last_error"] or "")
        except Exception as ex:
            if el := self._el("perps_error"):
                el.set_text(str(ex)[:300])
        finally:
            self._perps_panel_busy = False

    # ---------- 分析 ----------
    def build_analytics(self) -> None:
        with ui.row().classes("w-full items-center gap-2"):
            ui.label("统计口径 · 近 30 天").classes("kd-section")
            ui.space()
            ui.button("重新统计", icon="refresh",
                      on_click=lambda: asyncio.create_task(self.load_analytics())) \
                .props("flat dense")
        self.an_metrics = ui.row().classes(
            "kd-metric-row w-full no-wrap items-stretch")
        with self.an_metrics:
            self.an_fills, self.an_fills_sub = self._metric("近 30 天成交笔数", with_sub=True)
            self.an_vol = self._metric("近 30 天成交额")
            self.an_fees = self._metric("近 30 天手续费")
            self.an_net = self._metric("已结算净盈亏")
            self.an_pos = self._metric("当前持仓数")
        ui.label("成交额 Top 市场").classes("kd-section")
        self.an_table = ui.table(
            columns=[
                {"name": "ticker", "label": "市场", "field": "ticker", "align": "left"},
                {"name": "fills", "label": "成交笔数", "field": "fills", "align": "right"},
                {"name": "contracts", "label": "合约数", "field": "contracts", "align": "right"},
                {"name": "volume", "label": "成交额", "field": "volume", "align": "right"},
            ],
            rows=[], row_key="ticker", pagination=10,
        ).classes("w-full")
        asyncio.create_task(self.load_analytics())

    async def load_analytics(self) -> None:
        if not self.api:
            return
        try:
            data = await run.io_bound(db.analytics, self.api.env)
        except Exception as ex:
            self.notify(f"统计失败：{ex}", type="negative")
            return
        f = data.get("fills") or {}
        s = data.get("settlements") or {}
        if el := self._el("an_fills"):
            el.set_text(str(f.get("n") or 0))
        if el := self._el("an_fills_sub"):
            el.set_text(f"{f.get('contracts', 0):g} 张合约")
        if el := self._el("an_vol"):
            el.set_text(usd(f.get("volume")))
        if el := self._el("an_fees"):
            el.set_text(usd(f.get("fees")))
        if el := self._el("an_net"):
            el.set_text(usd(s.get("net"), signed=True))
        if el := self._el("an_pos"):
            el.set_text(str(data.get("position_count") or 0))
        if table := self._el("an_table"):
            table.rows = [{
                "ticker": r.get("ticker") or "",
                "fills": str(r.get("fills") or 0),
                "contracts": f"{r.get('contracts') or 0:g}",
                "volume": usd(r.get("volume")),
            } for r in (data.get("top_markets") or [])]
            table.update()

    # ---------- AI ----------
    def build_ai_page(self) -> None:
        ai_cfg = store.load_config()["ai"]
        providers = ai_cfg["providers"]
        with ui.row().classes("w-full items-center gap-2"):
            ui.label("选择模型").classes("kd-section")
            ui.space()
            ui.select({i: f"{p['name']} · {p['model'] or '未命名模型'}"
                       for i, p in enumerate(providers)},
                      value=ai_cfg["active"], label="模型").classes("w-64") \
                .props("dense outlined") \
                .bind_value_to(self, "_ai_active")
        self._ai_active = ai_cfg["active"]
        self.ai_question = ui.textarea(
            placeholder="例如：近 30 天我的成交集中在哪些市场？已结算部分的盈亏如何？"
        ).classes("w-full").props("outlined autogrow rows=2")
        with ui.row().classes("items-center gap-2"):
            ui.button("提问", icon="send", on_click=self.do_ai_ask).props("unelevated")
            ui.label("仅使用本地 DuckDB 中的余额、持仓、成交、订单与结算数据，不会上传原始订单。") \
                .classes("text-xs kd-mut")
        self.ai_answer = ui.markdown("").classes("w-full text-sm")
        ui.label("提示：在「系统设置 → AI 模型」中配置服务商与 API Key。") \
            .classes("text-xs kd-mut")

    async def do_ai_ask(self) -> None:
        question = (self.ai_question.value or "").strip()
        if not question:
            ui.notify("请输入问题", type="warning")
            return
        cfg = store.load_config()["ai"]
        idx = int(getattr(self, "_ai_active", cfg["active"]) or 0)
        provider = cfg["providers"][min(max(idx, 0), len(cfg["providers"]) - 1)]
        if not provider.get("api_key"):
            ui.notify("请先在「系统设置 → AI 模型」中填写 API Key", type="negative")
            return
        self.ai_answer.set_content("_思考中…_")
        env = self.api.env if self.api else "local"
        try:
            data = await run.io_bound(db.analytics, env)
            context = json.dumps(data, ensure_ascii=False, default=str)[:12000]
            answer = await run.io_bound(ai_client.ask, question, context, provider,
                                        store.proxy_url(self.proxy_cfg))
            self.ai_answer.set_content(answer or "（模型没有返回内容）")
        except Exception as ex:
            self.ai_answer.set_content(f"**分析失败**：{ex}")

    # ---------- 聊天室 ----------
    def chat_env(self) -> str:
        return self.api.env if self.api else (self.sess or {}).get("env", "local")

    def build_chat(self) -> None:
        env = self.chat_env()
        self._chat_image = ""
        with ui.row().classes("w-full items-center gap-2"):
            ui.label(ENV_LABEL.get(env, env)).classes("kd-key")
            ui.label("同一环境下的用户共享这段讨论").classes("text-xs kd-mut")
            ui.space()
            ui.button("刷新", icon="refresh",
                      on_click=lambda: asyncio.create_task(self.load_chat())) \
                .props("flat dense")
        self.chat_scroll = ui.scroll_area().classes("w-full") \
            .style("height: calc(100vh - 340px); min-height: 240px")
        with self.chat_scroll:
            self.chat_box = ui.column().classes("w-full gap-3 pr-2")
        self.chat_preview = ui.image().classes("h-20 rounded-md").style("display:none")
        with ui.row().classes("w-full items-end gap-2"):
            self.chat_input = ui.textarea(placeholder="输入消息…").classes("flex-1") \
                .props("outlined autogrow rows=1")
            ui.upload(on_upload=self.on_chat_upload, auto_upload=True) \
                .props("flat dense accept=image/* label=图片").classes("w-36")
            ui.button("发送", icon="send", on_click=self.do_chat_send).props("unelevated")
        asyncio.create_task(self.load_chat())
        ui.timer(4.0, self.load_chat)

    async def on_chat_upload(self, e) -> None:
        data = await e.file.read()
        if len(data) > 4 * 1024 * 1024:
            ui.notify("图片不能超过 4MB", type="negative")
            return
        name = f"{uuid4().hex}{Path(e.file.name or 'img.png').suffix or '.png'}"
        folder = store.DATA_DIR / "chat_images"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(data)
        self._chat_image = name
        self.chat_preview.set_source(f"/chat-images/{name}")
        self.chat_preview.style("display:block")

    async def do_chat_send(self) -> None:
        text = (self.chat_input.value or "").strip()
        image = getattr(self, "_chat_image", "")
        if not text and not image:
            return
        try:
            await run.io_bound(db.add_chat_message, self.chat_env(), self.user, text, image)
        except Exception as ex:
            ui.notify(f"发送失败：{ex}", type="negative")
            return
        self.chat_input.value = ""
        self._chat_image = ""
        self.chat_preview.set_source("")
        self.chat_preview.style("display:none")
        await self.load_chat()

    async def load_chat(self) -> None:
        chat_box = self._el("chat_box")
        if not chat_box:
            return
        try:
            rows = await run.io_bound(db.chat_messages, self.chat_env(), 100)
        except Exception:
            return
        chat_box.clear()
        with chat_box:
            for m in rows:
                with ui.column().classes("w-full gap-1"):
                    ui.label(f"{m.get('username')} · {fmt_ts(m.get('created'))}") \
                        .classes("kd-chat-meta")
                    if m.get("image"):
                        ui.image(f"/chat-images/{m['image']}") \
                            .classes("max-h-64 rounded-md cursor-pointer") \
                            .on("click", lambda e, src=m["image"]: self.preview_image(src))
                    if m.get("body"):
                        ui.label(m["body"]).classes("kd-bubble text-sm whitespace-pre-wrap")
        if scroll := self._el("chat_scroll"):
            try:
                scroll.scroll_to(percent=1.0)
            except Exception:
                pass

    def preview_image(self, name: str) -> None:
        with self.root:
            dlg = ui.dialog()
            with dlg, ui.card().classes("p-2"):
                ui.image(f"/chat-images/{name}").classes("max-h-[80vh]")
        dlg.open()

    # ---------- 概览 ----------
    def _metric(self, title: str, with_sub: bool = False):
        with ui.column().classes("kd-metric gap-0"):
            ui.label(title).classes("kd-metric-label")
            lbl = ui.label("—").classes("kd-metric-value")
            sub = ui.label("").classes("kd-metric-sub") if with_sub else None
        return (lbl, sub) if with_sub else lbl

    def build_overview(self) -> None:
        with ui.row().classes("kd-metric-row w-full no-wrap items-stretch"):
            self.c_avail, self.c_avail_ts = self._metric("可用余额", with_sub=True)
            self.c_expo = self._metric("持仓敞口")
            self.c_pnl = self._metric("已实现盈亏")
            self.c_rest = self._metric("在挂订单")
            self.c_subs = self._metric("子账户数")

        # CF Benchmarks 行情条（常驻，走 Kalshi 转发端点）
        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("w-full items-center gap-2"):
                ui.label("CF BENCHMARKS").classes("kd-section")
                self.cf_src_label = ui.label("数据源：Kalshi 转发").classes("text-xs kd-mut")
                self.cf_ws_status = ui.label("实时订阅未启动").classes("kd-key")
                ui.space()
                self._api_btn(icon="play_arrow", coro=self.start_cfb) \
                    .props("flat dense round").tooltip("启动 CFB WebSocket 实时订阅")
                self._api_btn(icon="stop", coro=self.stop_cfb) \
                    .props("flat dense round").tooltip("停止 CFB 实时订阅")
                self._api_btn(icon="refresh", coro=self.refresh_cf) \
                    .props("flat dense round").tooltip("立即刷新 CF 价格")
            self.cf_row = ui.row().classes("w-full gap-3 no-wrap items-stretch")
            with self.cf_row:
                ui.label("加载中…").classes("text-xs kd-mut")
        ui.timer(2.0, self.refresh_cf_live)

        with ui.row().classes("w-full gap-8 items-start"):
            with ui.column().classes("flex-1 min-w-[380px] gap-2"):
                ui.label("分片余额分布").classes("kd-section")
                self.shard_table = ui.table(
                    columns=[
                        {"name": "shard", "label": "shard", "field": "shard", "align": "center"},
                        {"name": "balance", "label": "余额", "field": "balance", "align": "right"},
                        {"name": "pct", "label": "占比", "field": "pct", "align": "right"},
                    ],
                    rows=[], row_key="id", pagination=5,
                ).classes("w-full")
            with ui.column().classes("flex-1 min-w-[380px] gap-2"):
                ui.label("子账户余额").classes("kd-section")
                self.sub_mini = ui.table(
                    columns=[
                        {"name": "shard", "label": "shard", "field": "shard", "align": "center"},
                        {"name": "sub", "label": "子账户", "field": "sub", "align": "center"},
                        {"name": "balance", "label": "余额", "field": "balance", "align": "right"},
                        {"name": "updated", "label": "更新时间", "field": "updated", "align": "left"},
                    ],
                    rows=[], row_key="id", pagination=5,
                ).classes("w-full")

    # ---------- 持仓 ----------
    def build_positions(self) -> None:
        with ui.row().classes("w-full items-center gap-2"):
            self._api_btn("手动交易", icon="add", coro=self.open_trade) \
                .props("unelevated dense")
            self._api_btn("动量交易", icon="trending_up",
                          coro=lambda: self.open_trade(momentum=True)) \
                .props("unelevated dense color=positive")
            ui.label("选中任意持仓行 → 查看实时行情并直接平仓 / 买入 / 卖出；"
                     "动量交易自动跟随上涨腿").classes("text-xs kd-mut")
        self.pos_table = ui.table(
            columns=[
                {"name": "ticker", "label": "市场", "field": "ticker", "align": "left", "sortable": True},
                {"name": "side", "label": "方向", "field": "side", "align": "center"},
                {"name": "qty", "label": "数量", "field": "qty", "align": "right"},
                {"name": "exposure", "label": "敞口", "field": "exposure", "align": "right"},
                {"name": "pnl", "label": "已实现盈亏", "field": "pnl", "align": "right"},
                {"name": "resting", "label": "在挂", "field": "resting", "align": "right"},
                {"name": "shard", "label": "shard", "field": "shard", "align": "center"},
                {"name": "act", "label": "操作", "field": "act", "align": "center"},
            ],
            rows=[], row_key="id", pagination=12, selection="single",
            on_select=self.on_pos_select,
        ).classes("w-full")
        self.pos_table.add_slot("body-cell-ticker", '''
            <q-td :props="props">
                <span class="cursor-pointer" @click="e => e.target.closest('tr')
                    .querySelector('.q-checkbox').click()">{{ props.value }}</span>
            </q-td>
        ''')
        self.pos_table.add_slot("body-cell-act", '''
            <q-td :props="props" class="text-center">
                <q-btn dense flat size="sm" color="primary" label="交易"
                    @click="e => e.target.closest('tr').querySelector('.q-checkbox').click()" />
            </q-td>
        ''')

    def on_pos_select(self, e) -> None:
        if not e.selection:
            return
        row = e.selection[0]
        self.pos_table.selected = []
        p = self.pos_by_ticker.get(row.get("id"))
        if not p:
            return
        leg = "yes" if p["yes_qty"] > 0 else "no"
        qty = int(p["yes_qty"] or p["no_qty"])
        # 持仓平仓通常是挂单等价格，默认用 GTC 而非 IOC（IOC 未成交会立即消失）
        asyncio.create_task(self.open_trade(p["ticker"], leg=leg, qty=qty,
                                            prefer_tif="good_till_canceled"))

    # ---------- 订单 ----------
    def build_orders(self) -> None:
        with ui.row().classes("w-full items-center gap-2"):
            self.status_toggle = ui.toggle(
                {"all": "全部", "resting": "在挂", "executed": "已成交", "canceled": "已撤"},
                value="resting",
                on_change=self._on_status_change,
            ).props("dense")
            self.ord_ticker_input = ui.input("市场 ticker 过滤", placeholder="留空 = 全部") \
                .classes("w-64").props("dense outlined clearable")
            self._api_btn("刷新", icon="refresh", coro=self._on_order_query).props("dense flat")
            self._orders_sync_label = ui.label("").classes("text-xs kd-mut font-mono w-20")
            ui.label(f"自动每 {self.refresh_interval} 秒同步 · 下单/撤单后立即刷新 · "
                     "选中在挂订单行即可撤单").classes("text-xs kd-mut")
        # 同步中的醒目加载条：转圈 + 文案（默认隐藏）
        self._orders_spinner = ui.row().classes(
            "w-full justify-center items-center gap-3 py-3").style("color:#35e0a1")
        with self._orders_spinner:
            ui.spinner(size="md", color="green")
            ui.label("正在同步最新数据…").classes("text-xs font-mono")
        self._orders_spinner.set_visibility(False)
        self.order_table = ui.table(
            columns=[
                {"name": "time_utc", "label": "UTC", "field": "time_utc", "align": "left"},
                {"name": "time_et", "label": "美东", "field": "time_et", "align": "left"},
                {"name": "time_bj", "label": "北京", "field": "time_bj", "align": "left"},
                {"name": "ticker", "label": "市场", "field": "ticker", "align": "left"},
                {"name": "side", "label": "方向", "field": "side", "align": "center"},
                {"name": "price", "label": "价格", "field": "price", "align": "right"},
                {"name": "count", "label": "数量", "field": "count", "align": "right"},
                {"name": "filled", "label": "成交", "field": "filled", "align": "right"},
                {"name": "remaining", "label": "剩余", "field": "remaining", "align": "right"},
                {"name": "status", "label": "状态", "field": "status", "align": "center"},
                {"name": "result", "label": "结算", "field": "result", "align": "center"},
                {"name": "shard", "label": "shard", "field": "shard", "align": "center"},
                {"name": "act", "label": "操作", "field": "act", "align": "center"},
            ],
            rows=[], row_key="id", pagination=15, selection="single",
            on_select=self.on_order_select,
        ).classes("w-full")
        self.order_table.add_slot("body-cell-result", '''
            <q-td :props="props" class="text-center">
                <span v-if="props.value === 'win'"
                      style="color:#35e0a1;font-weight:700">赢</span>
                <span v-else-if="props.value === 'loss'"
                      style="color:#ff5c5c;font-weight:700">输</span>
                <span v-else-if="props.value === 'n/a'"
                      style="color:#8b93a7;font-size:11px">非二元</span>
                <span v-else style="color:#3c4455">—</span>
            </q-td>
        ''')
        self.order_table.add_slot("body-cell-ticker", '''
            <q-td :props="props">
                <span class="cursor-pointer" @click="e => e.target.closest('tr')
                    .querySelector('.q-checkbox').click()">{{ props.value }}</span>
            </q-td>
        ''')
        self.order_table.add_slot("body-cell-act", '''
            <q-td :props="props" class="text-center">
                <q-btn dense flat size="sm" color="primary" label="详情"
                    @click="e => e.target.closest('tr').querySelector('.q-checkbox').click()" />
            </q-td>
        ''')

    async def _on_status_change(self, e) -> None:
        """切换 全部/在挂/已成交/已撤：显示 loading → 拉最新数据 → 渲染。"""
        v = e.value
        self.status_filter = None if v == "all" else v
        # 切换即从服务器刷新最新数据（不再只查本地缓存）
        await self.refresh_orders()

    async def _on_order_query(self) -> None:
        """手动刷新订单：应用 ticker 过滤 → 调 API → 落库 → 读库。"""
        self.orders_ticker = (self.ord_ticker_input.value or "").strip()
        await self.refresh_orders()

    def on_order_select(self, e) -> None:
        if not e.selection:
            return
        row = e.selection[0]
        self.order_table.selected = []
        asyncio.create_task(self.open_order(row.get("id")))

    # ---------- 成交 ----------
    def build_fills(self) -> None:
        with ui.row().classes("w-full items-center gap-2"):
            self.fill_ticker_input = ui.input("市场 ticker 过滤", placeholder="留空 = 全部") \
                .classes("w-64").props("dense outlined clearable")
            self.fill_days_select = ui.select(
                {3: "近 3 天", 7: "近 7 天", 30: "近 30 天", 0: "不限"},
                value=3, label="时间范围",
            ).classes("w-36")
            self._api_btn("查询", icon="search", coro=self._on_fill_query).props("dense flat")
        self.fill_table = ui.table(
            columns=[
                {"name": "time", "label": "时间", "field": "time", "align": "left"},
                {"name": "ticker", "label": "市场", "field": "ticker", "align": "left"},
                {"name": "action", "label": "动作", "field": "action", "align": "center"},
                {"name": "side", "label": "方向", "field": "side", "align": "center"},
                {"name": "price", "label": "成交价", "field": "price", "align": "right"},
                {"name": "count", "label": "数量", "field": "count", "align": "right"},
                {"name": "role", "label": "角色", "field": "role", "align": "center"},
                {"name": "order", "label": "订单", "field": "order", "align": "left"},
            ],
            rows=[], row_key="id", pagination=20,
        ).classes("w-full")

    async def _on_fill_query(self) -> None:
        if self._fills_busy:
            return
        self.fills_ticker = (self.fill_ticker_input.value or "").strip()
        days = self.fill_days_select.value
        self.fills_days = None if not days else int(days)
        await self.refresh_fills()

    # ---------- 子账户 / 分片 ----------
    def build_subaccounts(self) -> None:
        with ui.column().classes("w-full gap-2"):
            ui.label("子账户余额（含各 shard）").classes("kd-section")
            self.sub_table = ui.table(
                columns=[
                    {"name": "shard", "label": "shard", "field": "shard", "align": "center"},
                    {"name": "sub", "label": "子账户", "field": "sub", "align": "center"},
                    {"name": "balance", "label": "余额", "field": "balance", "align": "right"},
                    {"name": "updated", "label": "更新时间", "field": "updated", "align": "left"},
                ],
                rows=[], row_key="id", pagination=10,
            ).classes("w-full")

        with ui.row().classes("w-full gap-10 items-start"):
            with ui.column().classes("flex-1 min-w-[380px] gap-2"):
                ui.label("同 shard 子账户转账").classes("kd-section")
                with ui.row().classes("gap-2"):
                    self.t_from = ui.number("从子账户", value=0, min=0, precision=0).classes("w-28")
                    self.t_to = ui.number("到子账户", value=1, min=0, precision=0).classes("w-28")
                    self.t_shard = ui.number("shard（可空）", value=None, precision=0).classes("w-32")
                self.t_amt = ui.number("金额（美元）", value=10.0, min=0.01, step=1.0,
                                       precision=2).classes("w-44")
                self._api_btn("提交转账", icon="swap_horiz", coro=self.do_transfer_sub) \
                    .props("unelevated")
                ui.label("amount_cents 为整数美分，由系统自动换算。").classes("text-xs kd-mut")

            with ui.column().classes("flex-1 min-w-[380px] gap-2"):
                ui.label("跨 shard 转账").classes("kd-section")
                self.x_bal_hint = ui.label("各分片余额：—").classes("text-xs kd-mut")
                with ui.row().classes("gap-2"):
                    self.x_from = ui.number("源 shard", value=0, min=0, precision=0).classes("w-28")
                    self.x_to = ui.number("目标 shard", value=2, min=0, precision=0).classes("w-28")
                    self.x_amt = ui.number("金额（美元）", value=10.0, min=0.01, step=1.0,
                                           precision=2).classes("w-40")
                with ui.row().classes("gap-2"):
                    self.x_src = ui.select({"event_contract": "event_contract", "margined": "margined"},
                                           value="event_contract", label="源类型").classes("w-40")
                    self.x_dst = ui.select({"event_contract": "event_contract", "margined": "margined"},
                                           value="event_contract", label="目标类型").classes("w-40")
                self._api_btn("提交跨 shard 转账", icon="sync_alt", coro=self.do_transfer_shard) \
                    .props("unelevated")
                ui.label("金额按 centicents（1 美元 = 10000）提交。").classes("text-xs kd-mut")

        with ui.column().classes("w-full gap-2"):
            with ui.row().classes("items-center gap-2"):
                ui.label("创建子账户 / 转账记录").classes("kd-section")
                self.new_sub_shard = ui.number("指定 shard（可空）", value=None, precision=0) \
                    .classes("w-44")
                self._api_btn("创建", icon="add", coro=self.do_create_subaccount).props("dense")
                ui.space()
                self._api_btn("刷新转账记录", icon="refresh",
                              coro=self.refresh_transfers).props("dense flat")
            self.tr_table = ui.table(
                columns=[
                    {"name": "time", "label": "时间", "field": "time", "align": "left"},
                    {"name": "type", "label": "类型", "field": "type", "align": "center"},
                    {"name": "amount", "label": "金额", "field": "amount", "align": "right"},
                    {"name": "from", "label": "从", "field": "from", "align": "center"},
                    {"name": "to", "label": "到", "field": "to", "align": "center"},
                ],
                rows=[], row_key="id", pagination=8,
            ).classes("w-full")
        self.render_balance()      # 用本地快照先填充「各分片余额」

    # ---------- 设置 ----------
    def build_settings(self) -> None:
        tab = getattr(self, "settings_tab", "系统设置")
        with ui.tabs().classes("w-full") as tabs:
            ui.tab("系统设置", icon="settings").props("no-caps inline-label")
            ui.tab("用户管理", icon="group").props("no-caps inline-label")
        with ui.tab_panels(tabs, value=tab).classes("w-full kd-fade") \
                .style("background: transparent"):
            with ui.tab_panel("系统设置"):
                self.build_system_settings()
            with ui.tab_panel("用户管理"):
                self.build_user_management()
        tabs.on_value_change(lambda e: setattr(self, "settings_tab", e.value))

    def build_system_settings(self) -> None:
        with ui.column().classes("w-full max-w-[760px] gap-2"):
            ui.label("同步").classes("kd-section")
            with ui.row().classes("items-center gap-2"):
                self.ri_input = ui.number("自动刷新间隔（秒）", value=self.refresh_interval,
                                          min=5, max=3600, precision=0).classes("w-52")
                ui.button("保存", icon="schedule", on_click=self.do_save_interval) \
                    .props("unelevated dense")
            ui.label("默认 60 秒；保存后立即生效并写入 data/config.json。") \
                .classes("text-xs kd-mut")
        ui.separator()

        with ui.column().classes("w-full max-w-[760px] gap-2"):
            ui.label("当前连接").classes("kd-section")
            ui.label(f"环境：{ENV_LABEL[self.api.env]}　({self.api.base_url})").classes("text-sm")
            ui.label(f"Key ID：{store.mask_key(self.sess['key_id'])}").classes("text-sm font-mono")
            ui.label(f"私钥路径：{self.sess['pem_path']}").classes("text-xs kd-mut")
            with ui.row().classes("gap-2"):
                ui.button("测试连接", icon="wifi_tethering", on_click=self.test_conn).props("outline")
                ui.button("解绑并清除全部环境私钥", icon="delete_forever",
                          on_click=self.do_unbind).props("outline color=negative")
        ui.separator()

        with ui.column().classes("w-full max-w-[760px] gap-2"):
            ui.label("重新绑定私钥").classes("kd-section")
            self.pem_name2 = ui.label("未选择文件").classes("text-xs kd-mut")
            ui.upload(label="上传新的 PEM", auto_upload=True, max_file_size=2_000_000,
                      on_upload=self.on_pem_upload2).props("accept=.pem,.key,.txt flat bordered")
            self.key_input2 = ui.input("API Key ID").classes("w-full").props("dense outlined")
            self.env_select2 = ui.select({"prod": "生产环境", "demo": "模拟环境"},
                                         value=self.api.env, label="环境").classes("w-48")
            ui.button("保存并连接", icon="save", on_click=self.do_rebind).props("unelevated")
        ui.separator()

        with ui.column().classes("w-full max-w-[760px] gap-2"):
            ui.label("网络代理（SOCKS5）").classes("kd-section")
            self.build_proxy_box()

        ui.separator()
        with ui.column().classes("w-full max-w-[760px] gap-2"):
            ui.label("AI 模型").classes("kd-section")
            ui.label("支持任意 OpenAI 兼容接口（OpenAI / DeepSeek / Moonshot / 自建网关）。") \
                .classes("text-xs kd-mut")
            self._ai_providers = [dict(p) for p in store.load_config()["ai"]["providers"]]
            self._ai_active_idx = store.load_config()["ai"]["active"]
            self.ai_list = ui.column().classes("w-full gap-0")
            self._render_ai_rows()
            with ui.row().classes("items-end gap-2 pt-2 no-wrap"):
                self.ai_name = ui.input("名称").classes("w-28").props("dense outlined")
                self.ai_base = ui.input("Base URL", placeholder="https://api.openai.com/v1") \
                    .classes("w-64").props("dense outlined")
                self.ai_model = ui.input("模型").classes("w-40").props("dense outlined")
                self.ai_key = ui.input("API Key", password=True,
                                       password_toggle_button=True) \
                    .classes("w-52").props("dense outlined")
                ui.button("添加", icon="add", on_click=self.do_add_provider).props("dense")
            with ui.row().classes("items-center gap-2"):
                self.ai_active_select = ui.select(
                    {i: p["name"] for i, p in enumerate(self._ai_providers)},
                    value=min(self._ai_active_idx, len(self._ai_providers) - 1),
                    label="默认服务商").classes("w-48").props("dense outlined")
                ui.button("保存默认服务商", icon="save", on_click=self.do_save_ai) \
                    .props("dense")

    def build_user_management(self) -> None:
        with ui.column().classes("w-full max-w-[760px] gap-2"):
            ui.label("账户").classes("kd-section")
            ui.label("非管理员账户只能访问「概览」与「聊天室」。") \
                .classes("text-xs kd-mut")
            self.user_list = ui.column().classes("w-full gap-0")
            self._render_users()
            with ui.row().classes("items-end gap-2 pt-2"):
                self.nu_name = ui.input("用户名").classes("w-40").props("dense outlined")
                self.nu_pass = ui.input("密码", password=True,
                                        password_toggle_button=True) \
                    .classes("w-40").props("dense outlined")
                self.nu_role = ui.select({"viewer": "只读", "admin": "管理员"},
                                         value="viewer", label="角色").classes("w-36") \
                    .props("dense outlined")
                ui.button("添加用户", icon="person_add", on_click=self.do_add_user) \
                    .props("dense")

    # ---------- 用户管理 ----------
    def _render_users(self) -> None:
        self.user_list.clear()
        with self.user_list:
            for u in store.load_users():
                with ui.row().classes("w-full items-center gap-3 py-2") \
                        .style("border-bottom:1px solid var(--kd-line)"):
                    ui.label(u["username"]).classes("text-sm font-mono")
                    ui.label("管理员" if u["role"] == "admin" else "只读") \
                        .classes("text-xs kd-mut")
                    ui.space()
                    ui.button(icon="key",
                              on_click=lambda n=u["username"]: asyncio.create_task(
                                  self.do_reset_pw(n))) \
                        .props("flat dense round size=sm").tooltip("重置密码")
                    ui.button(icon="delete",
                              on_click=lambda n=u["username"]: asyncio.create_task(
                                  self.do_delete_user(n))) \
                        .props("flat dense round size=sm color=negative").tooltip("删除用户")

    async def do_add_user(self) -> None:
        name = (self.nu_name.value or "").strip()
        users = store.load_users()
        if any(u["username"] == name for u in users):
            ui.notify("用户名已存在", type="negative")
            return
        users.append({"username": name, "password": self.nu_pass.value or "",
                      "role": self.nu_role.value or "viewer"})
        try:
            store.save_users(users)
        except ValueError as ex:
            ui.notify(str(ex), type="negative")
            return
        ui.notify(f"已添加用户 {name}", type="positive")
        self.settings_tab = "用户管理"
        self.show_page(PAGE_SET)

    async def do_delete_user(self, name: str) -> None:
        if not await self.confirm(f"删除用户 {name}？"):
            return
        users = [u for u in store.load_users() if u["username"] != name]
        try:
            store.save_users(users)
        except ValueError as ex:
            ui.notify(str(ex), type="negative")
            return
        if name == self.user:
            self.authed, self.current_user, self.user = False, None, ""
            self.api, self.sess = None, None
            self.rebuild()
            return
        ui.notify(f"已删除用户 {name}", type="positive")
        self.settings_tab = "用户管理"
        self.show_page(PAGE_SET)

    async def do_reset_pw(self, name: str) -> None:
        pwd = await self.prompt_text(f"重置 {name} 的密码")
        if not pwd:
            return
        users = store.load_users()
        for u in users:
            if u["username"] == name:
                u["password"] = pwd
        try:
            store.save_users(users)
        except ValueError as ex:
            ui.notify(str(ex), type="negative")
            return
        ui.notify(f"已重置 {name} 的密码", type="positive")

    # ---------- AI 配置 ----------
    def _render_ai_rows(self) -> None:
        self.ai_list.clear()
        with self.ai_list:
            for i, p in enumerate(self._ai_providers):
                with ui.row().classes("w-full items-center gap-3 py-2 no-wrap") \
                        .style("border-bottom:1px solid var(--kd-line)"):
                    ui.label(p["name"]).classes("text-sm w-24 truncate")
                    ui.label(p.get("base_url") or "—").classes("text-xs kd-mut truncate")
                    ui.label(p.get("model") or "—").classes("text-xs w-32 truncate")
                    ui.label("已配置 Key" if p.get("api_key") else "未配置 Key") \
                        .classes("text-xs kd-mut")
                    ui.space()
                    ui.button(icon="delete",
                              on_click=lambda idx=i: asyncio.create_task(
                                  self.do_del_provider(idx))) \
                        .props("flat dense round size=sm color=negative")

    async def do_add_provider(self) -> None:
        name = (self.ai_name.value or "").strip()
        base = (self.ai_base.value or "").strip().rstrip("/")
        model = (self.ai_model.value or "").strip()
        key = self.ai_key.value or ""
        if not (name and base and model):
            ui.notify("名称、Base URL、模型不能为空", type="warning")
            return
        self._ai_providers.append({"name": name, "base_url": base,
                                   "model": model, "api_key": key})
        try:
            store.save_ai(self._ai_providers, self._ai_active_idx)
        except ValueError as ex:
            ui.notify(str(ex), type="negative")
            return
        ui.notify(f"已添加 AI 服务商 {name}", type="positive")
        self.settings_tab = "系统设置"
        self.show_page(PAGE_SET)

    async def do_del_provider(self, idx: int) -> None:
        if not (0 <= idx < len(self._ai_providers)):
            return
        name = self._ai_providers[idx]["name"]
        if not await self.confirm(f"删除 AI 服务商 {name}？"):
            return
        self._ai_providers.pop(idx)
        active = min(self._ai_active_idx, len(self._ai_providers) - 1)
        store.save_ai(self._ai_providers, max(active, 0))
        ui.notify(f"已删除 {name}", type="positive")
        self.settings_tab = "系统设置"
        self.show_page(PAGE_SET)

    async def do_save_ai(self) -> None:
        idx = int(self.ai_active_select.value or 0)
        store.save_ai(self._ai_providers, idx)
        ui.notify("已保存默认 AI 服务商", type="positive")
        self.settings_tab = "系统设置"
        self.show_page(PAGE_SET)

    # ---------- 代理配置 ----------
    def build_proxy_box(self) -> None:
        p = self.proxy_cfg
        with ui.column().classes("w-full gap-2"):
            self.px_enabled = ui.switch("启用 SOCKS5 代理", value=bool(p.get("enabled")))
            ui.label("启用后，访问 Kalshi 生产 / Demo 官方接口全部经该代理，"
                     "域名由代理端解析（socks5h）。").classes("text-xs kd-mut")
            with ui.row().classes("gap-2"):
                self.px_host = ui.input("代理地址", value=p.get("host") or "127.0.0.1") \
                    .classes("w-44").props("dense outlined")
                self.px_port = ui.number("端口", value=int(p.get("port") or 1080),
                                         min=1, max=65535, precision=0).classes("w-28")
            with ui.row().classes("gap-2"):
                self.px_user = ui.input("用户名（可空）", value=p.get("username") or "") \
                    .classes("w-40").props("dense outlined")
                self.px_pass = ui.input("密码（可空）", value=p.get("password") or "",
                                        password=True, password_toggle_button=True) \
                    .classes("w-40").props("dense outlined")
            with ui.row().classes("w-full items-center gap-2"):
                ui.button("保存并测试", icon="network_check",
                          on_click=self.save_proxy_and_test).props("unelevated dense")
                self.px_status = ui.label(self._proxy_status_text(p)).classes("text-xs kd-mut")

    @staticmethod
    def _proxy_status_text(p: dict) -> str:
        url = store.proxy_url(p)
        return f"当前生效：{url}" if url else "当前：直连（未启用代理）"

    @staticmethod
    def _probe_proxy(base_url: str, proxy: str) -> str:
        """用一次公开行情请求验证代理链路（401 等状态码也算连通）。"""
        import requests
        r = requests.get(f"{base_url}/markets", params={"limit": 1},
                         proxies={"http": proxy, "https": proxy}, timeout=15)
        return f"HTTP {r.status_code}，返回 {len(r.content)} 字节"

    async def save_proxy_and_test(self) -> None:
        try:
            self.proxy_cfg = store.save_proxy({
                "enabled": bool(self.px_enabled.value),
                "host": self.px_host.value,
                "port": self.px_port.value,
                "username": self.px_user.value,
                "password": self.px_pass.value,
            })
        except ValueError as ex:
            ui.notify(str(ex), type="negative")
            return
        self.px_status.set_text(self._proxy_status_text(self.proxy_cfg))
        url = store.proxy_url(self.proxy_cfg)
        if not url:
            if self.api and self.sess:
                self.api = self._new_api(self.sess["key_id"], self.sess["pem_path"],
                                         self.sess["env"])
            ui.notify("已保存：未启用代理，改为直连", type="positive")
            return
        base = ENDPOINTS[self.api.env] if self.api else ENDPOINTS.get(
            ((el.value if (el := self._el("env_select")) else None) or "prod"),
            ENDPOINTS["prod"])
        try:
            msg = await run.io_bound(self._probe_proxy, base, url)
        except Exception as ex:
            ui.notify(f"代理测试失败：{ex}", type="negative")
            return
        ui.notify(f"代理可用（{msg}）", type="positive")
        if self.api and self.sess:
            try:
                api = self._new_api(self.sess["key_id"], self.sess["pem_path"], self.sess["env"])
                await run.io_bound(api.balance)
            except Exception as ex:
                ui.notify(f"代理切换后连接失败：{ex}", type="negative")
                return
            self.api = api
            await self.refresh_all(manual=True)
            ui.notify("已切换代理并重新连接成功", type="positive")

    async def on_pem_upload2(self, e: events.UploadEventArguments) -> None:
        data = await e.file.read()
        try:
            text = store.normalize_pem(data)
        except Exception as ex:
            ui.notify(f"PEM 解析失败：{ex}", type="negative")
            return
        self._pem_text = text
        self.pem_name2.set_text(f"已选择：{e.file.name}")
        ui.notify("私钥已载入", type="positive")

    async def do_rebind(self) -> None:
        await self._connect((self.key_input2.value or "").strip(), self.env_select2.value or "prod")

    async def test_conn(self) -> None:
        try:
            bal = await run.io_bound(self.api.balance)
            ui.notify(f"连接正常，可用余额 {usd(bal['available'])}", type="positive")
        except Exception as ex:
            ui.notify(f"连接失败：{ex}", type="negative")

    async def do_save_interval(self) -> None:
        try:
            value = store.save_refresh_interval(int(self.ri_input.value or 0))
        except (TypeError, ValueError) as ex:
            ui.notify(f"保存失败：{ex}", type="negative")
            return
        self.refresh_interval = value
        if self.timer:
            self.timer.interval = value
        if hasattr(self, "interval_label"):
            self.interval_label.set_text(f"每 {value} 秒")
        ui.notify(f"自动刷新间隔已设为 {value} 秒", type="positive")

    async def switch_env(self) -> None:
        """悬浮按钮：在模拟 / 生产环境之间切换（各环境使用各自保存的 Key）。"""
        if not self.api:
            return
        target = "demo" if self.api.env == "prod" else "prod"
        label = "模拟环境" if target == "demo" else "生产环境"
        sess = store.load_session(target)
        if not sess:
            self.login_env = target
            self.api, self.sess = None, None
            ui.notify(f"尚未绑定{label}的 API Key，请上传私钥并填写 Key ID", type="warning")
            self.rebuild()
            return
        try:
            api = self._new_api(sess["key_id"], sess["pem_path"], target)
            bal = await run.io_bound(api.balance)
        except Exception as ex:
            ui.notify(f"切换到{label}失败：{ex}", type="negative")
            return
        try:
            await run.io_bound(db.save_balance, target, sess["key_id"], bal)
            await run.io_bound(store.save_last_env, target)
        except Exception:
            pass
        self.api, self.sess = api, sess
        self.state = {"balance": {}, "positions": [], "orders": [], "fills": [], "subs": []}
        self.page = PAGE_OVER
        ui.notify(f"已切换到{label}（{store.mask_key(sess['key_id'])}）", type="positive")
        self.rebuild()

    async def do_unbind(self) -> None:
        if not await self.confirm("确定解除绑定？本机保存的私钥文件将被删除。"):
            return
        store.clear_session()
        self.api, self.sess = None, None
        self.state = {"balance": {}, "positions": [], "orders": [], "fills": [], "subs": []}
        ui.notify("已解绑并清除本地私钥", type="positive")
        self.rebuild()

    async def do_logout(self) -> None:
        if not await self.confirm("退出工作台？Kalshi 私钥与本地数据仍保留在本机。"):
            return
        self.authed, self.user = False, ""
        self.current_user = None
        self.page = PAGE_OVER
        self.api, self.sess = None, None
        self.rebuild()

    # ================= 数据刷新 =================
    async def tick(self) -> None:
        if not (self.api and self.auto and not self.busy):
            return
        if time.time() < self.cooldown:
            return
        await self.refresh_all()

    def notify(self, message: str, type: str = "info") -> None:
        """后台任务里也能安全使用的通知（显式进入页面根容器）。"""
        try:
            with self.root:
                ui.notify(message, type=type)
        except RuntimeError:
            pass

    @staticmethod
    def _busy_run(btn, coro):
        """包装一个 async 可调用：btn 在 coro 运行期间被 disable，
        无论正常结束、早退或抛异常都用 try/finally 恢复。返回一个可直接传给 ui.button(on_click=) 的 async handler。"""
        async def _h():
            btn.disable()
            try:
                await coro()
            finally:
                btn.enable()
        return _h

    def _api_btn(self, *args, coro, **props):
        """创建一个自带 API 防重入保护的按钮。

        用法：self._api_btn("提交", coro=self.submit_trade, icon="send").props("unelevated")
        其中 coro 是一个无参数 async 可调用；如需捕获变量，传 lambda 即可：
            coro=lambda: self.cancel_order(o)
        """
        btn = ui.button(*args, **props)
        btn.on_click(self._busy_run(btn, coro))
        return btn

    # ==== CF Benchmarks：symbol → CF indexId 映射 ====
    # 命名以 Kalshi event 的 settlement_sources 为准（可从
    # https://www.cfbenchmarks.com/data/indices/<CODE> 反查）：
    #   KXBTCD → BRTI（Bitcoin Real Time Index，注意不是 BTCUSD_RTI）
    #   KXETHD → ETHUSD_RTI，KXXRP → XRPUSD_RTI，KXDOGE → DOGEUSD_RTI
    _CF_MAP: dict[str, str] = {
        "BTC": "BRTI", "ETH": "ETHUSD_RTI", "SOL": "SOLUSD_RTI",
        "XRP": "XRPUSD_RTI", "ADA": "ADAUSD_RTI", "BNB": "BNBUSD_RTI",
        "AVAX": "AVAXUSD_RTI", "DOGE": "DOGEUSD_RTI", "LINK": "LINKUSD_RTI",
        "ARB": "ARBUSD_RTI", "OP": "OPUSD_RTI", "MATIC": "MATICUSD_RTI",
        "LTC": "LTCUSD_RTI", "BCH": "BCHUSD_RTI", "XLM": "XLMUSD_RTI",
        "UNI": "UNIUSD_RTI", "AAVE": "AAVEUSD_RTI", "SUI": "SUIUSD_RTI",
    }
    # CF indexId 是 BRTI 这类代号时，反向展示用该 symbol
    _CF_REVERSE = {"BRTI": "BTC"}

    @classmethod
    def _cf_sym_label(cls, idx_id: str) -> str:
        """indexId → 展示用币种名：BRTI→BTC、ETHUSD_RTI→ETH。"""
        if idx_id in cls._CF_REVERSE:
            return cls._CF_REVERSE[idx_id]
        return idx_id.replace("USD_RTI", "").replace("USD_RR", "")

    @classmethod
    def _cf_symbol_from_ticker(cls, ticker: str) -> Optional[str]:
        """从 Kalshi ticker 里提取 CF 标的 symbol。

        不能直接用 KX([A-Z]+) 贪婪正则——KXBNBMAXY 会吃成 BNBMAXY、KXSOLPERP 会吃成
        SOLPERP，都匹配不上。改为三级判定：
        1) 按 "-" 分段，第 2 段精确等于 symbol（KXBNBMAXY-BNB-26DEC31-67000 → BNB）
        2) 首段去掉 KX 后精确等于 symbol（KXBTC-LOW-2026 → BTC）
        3) 首段以 symbol 为前缀，按 symbol 长度降序匹配（KXETH15M-... → ETH）
        """
        if not ticker.startswith("KX"):
            return None
        parts = ticker.split("-")
        head = parts[0][2:]          # 去掉 KX 前缀
        # 1) 第二段精确匹配（最可靠：KXSYMBOLMAXY-SYMBOL-...）
        if len(parts) >= 2 and parts[1] in cls._CF_MAP:
            return parts[1]
        # 2) 首段精确匹配
        if head in cls._CF_MAP:
            return head
        # 3) 前缀匹配，长 symbol 优先，避免 BNB 抢在 BNBXXX 之前
        for sym in sorted(cls._CF_MAP, key=len, reverse=True):
            if head.startswith(sym):
                return sym
        return None

    @classmethod
    def cf_index_id_for_ticker(cls, ticker: str) -> Optional[str]:
        """给定 Kalshi market ticker，返回对应的 CF Benchmarks indexId（如果是 CF 标的）。"""
        sym = cls._cf_symbol_from_ticker(ticker)
        return cls._CF_MAP.get(sym) if sym else None

    # 固定采集的核心币种：不依赖 Kalshi 当前是否有对应活跃市场，
    # 否则一旦 crypto 市场空窗就完全采不到数据、曲线永远建立不起来。
    _CF_CORE_SYMBOLS = ("BTC", "ETH", "SOL", "XRP", "DOGE")

    async def _cf_discover(self, force: bool = False) -> None:
        """确定要采集的 CF indexId 集合。

        来源优先级：
        1) Kalshi 活跃 crypto event 的 settlement_sources（最权威，
           里面直接写着 https://www.cfbenchmarks.com/data/indices/BRTI）
        2) 固定核心币种兜底（避免 crypto 市场空窗时完全无数据）
        每 10 分钟重算一次（或 force=True 立即）。
        """
        now = time.time()
        if not force and (now - self._cf_last_discovery) < 600:
            return
        ids = {self._CF_MAP[s] for s in self._CF_CORE_SYMBOLS if s in self._CF_MAP}
        import re as _re
        # 从活跃 crypto event 的结算源提取真实指数代号
        try:
            d = await run.io_bound(self.api.cli.request, "GET", "/events",
                                   {"status": "open", "limit": 200})
            for e in (d.get("events") or []):
                if (e.get("category") or "").lower() != "crypto":
                    continue
                for s in (e.get("settlement_sources") or []):
                    m = _re.search(r"/indices/([A-Za-z0-9_]+)", s.get("url") or "")
                    if m:
                        ids.add(m.group(1))
        except Exception:
            pass
        # 再从活跃市场 ticker 反推（覆盖非 crypto 分类但结算用 CF 的情况）
        try:
            d = await run.io_bound(self.api.cli.request, "GET", "/markets",
                                   {"status": "open", "limit": 200})
            for m in (d.get("markets") or []):
                if m.get("status") != "active":
                    continue
                idx = self.cf_index_id_for_ticker(m.get("ticker", ""))
                if idx:
                    ids.add(idx)
        except Exception:
            pass
        self._cf_index_ids = ids
        self._cf_last_discovery = now

    async def _cf_fetch_and_persist(self, force: bool = False) -> None:
        """拉取当前已发现的所有 CF indexId 的值 → 落 DuckDB → 更新内存快照。

        优先尝试 cf_summaries 批量（一次 N 个），失败回退逐个 cf_values。
        转发层不可用时熔断 10 分钟，避免每轮自动刷新都白等超时。
        """
        if not self._cf_index_ids or not self.api:
            return
        if not force and time.time() < self._cf_fail_until:
            return
        ids = sorted(self._cf_index_ids)
        rows: list[dict] = []
        # 先试批量
        summaries = await run.io_bound(self.api.cf_summaries, ids)
        if summaries:
            rows.extend(summaries)
        else:
            # 回退：逐个拉
            for idx in ids:
                r = await run.io_bound(self.api.cf_values, idx)
                if r:
                    rows.append(r)
        if not rows:
            self._cf_fail_until = time.time() + 600   # 熔断 10 分钟
            # 记录具体失败原因，便于 UI 显示（503 / 结构不识别 / 网络）
            try:
                _ok, msg = await run.io_bound(self.api.cf_probe, ids[0])
                self._cf_last_error = msg
            except Exception as ex:
                self._cf_last_error = str(ex)[:160]
            return
        self._cf_last_error = ""
        self._cf_fail_until = 0.0
        try:
            await run.io_bound(db.save_cfb_ticks, self.api.env, rows)
        except Exception:
            pass
        # 更新内存快照
        latest = await run.io_bound(db.cfb_latest, self.api.env, list(ids))
        self.cfb_latest.update(latest)

    async def refresh_cf(self) -> None:
        """手动刷新 CF 价格（概览页刷新按钮），绕过熔断。"""
        if not self.api:
            return
        await self._cf_discover(force=True)
        await self._ensure_cfb_sub()
        await self._cf_fetch_and_persist(force=True)
        self.render_cf_overview()

    # ---------- CFB WebSocket 实时订阅 ----------
    def _cfb_subscriber(self) -> ws.CfbSubscriber:
        return ws.get_cfb_subscriber(
            self.sess["key_id"], self.sess["pem_path"], self.api.env,
            proxy=store.proxy_url(self.proxy_cfg))

    async def _ensure_cfb_sub(self) -> None:
        """把已发现的 index 列表同步给订阅器并启动（幂等）。"""
        if not (self.api and self.sess) or not self._cf_index_ids:
            return
        sub = self._cfb_subscriber()
        await sub.set_indices(sorted(self._cf_index_ids))
        await sub.start()

    async def start_cfb(self) -> None:
        if not (self.api and self.sess):
            return
        await self._cf_discover(force=True)
        await self._ensure_cfb_sub()
        self.notify(f"CFB 实时订阅已启动（{len(self._cf_index_ids)} 个指数）",
                    type="info")
        await self.refresh_cf_live()

    async def stop_cfb(self) -> None:
        if not (self.api and self.sess):
            return
        await self._cfb_subscriber().stop()
        self.notify("CFB 实时订阅已停止", type="info")
        await self.refresh_cf_live()

    async def refresh_cf_live(self) -> None:
        """2 秒一次：把 WS 最新值合并进快照并重绘行情条。"""
        if not (self.api and self.sess and self._el("cf_row")):
            return
        snap = self._cfb_subscriber().snapshot()
        if el := self._el("cf_ws_status"):
            if snap["running"]:
                st = {"connected": "已连接", "connecting": "连接中",
                      "error": "连接异常"}.get(snap["status"], snap["status"])
                text = f"实时订阅：{st} · {len(snap['indices'])} 指数"
                if snap["last_error"]:
                    text += f" · {snap['last_error'][:40]}"
                el.set_text(text)
            else:
                el.set_text("实时订阅未启动")
        if snap["msg_count"] == self._cf_live_seq:
            return
        self._cf_live_seq = snap["msg_count"]
        for idx, rec in snap["latest"].items():
            ts = rec.get("ts")
            self.cfb_latest[idx] = {
                "value": rec.get("value"),
                "ingested_at": datetime.fromtimestamp(ts) if ts else None,
            }
        self.render_cf_overview()

    def render_cf_overview(self) -> None:
        """概览页 CF 行情条：每个采集中的币种一张卡片。"""
        row = self._el("cf_row")
        if not row:
            return
        ids = sorted(self._cf_index_ids) or [
            self._CF_MAP[s] for s in self._CF_CORE_SYMBOLS if s in self._CF_MAP]
        snap = self.cfb_latest or {}
        ws_live = bool(self.api and self.sess
                       and self._cfb_subscriber().status == "connected")
        row.clear()
        with row:
            live = [i for i in ids if (snap.get(i) or {}).get("value") is not None]
            if not live:
                if lbl := self._el("cf_src_label"):
                    lbl.set_text("数据源：CFB WebSocket · 等待数据" if ws_live else
                                 "数据源：Kalshi 转发 · 当前不可用")
                reason = self._cf_last_error or "尚未拉取"
                ui.label("等待数据 —— CFB 实时订阅与 Kalshi 转发均未返回，"
                         "恢复后此处自动填充").classes("text-xs kd-mut")
                ui.label(f"原因：{reason}").classes("text-xs kd-mut font-mono")
                return
            if lbl := self._el("cf_src_label"):
                lbl.set_text("数据源：CFB WebSocket 实时 + Kalshi 转发兜底"
                             if ws_live else "数据源：Kalshi 转发")
            for idx in ids:
                rec = snap.get(idx) or {}
                sym = self._cf_sym_label(idx)
                val = rec.get("value")
                with ui.column().classes("kd-metric gap-0 min-w-[130px]"):
                    ui.label(f"{sym} / USD").classes("kd-metric-label")
                    if val is None:
                        ui.label("—").classes("kd-metric-value")
                        ui.label("待采集").classes("kd-metric-sub")
                    else:
                        ui.label(f"${val:,.2f}").classes("kd-metric-value")
                        ts = rec.get("ingested_at")
                        stamp = ts.strftime("%H:%M:%S") if hasattr(ts, "strftime") else "—"
                        ui.label(f"更新 {stamp}").classes("kd-metric-sub")

    async def refresh_all(self, manual: bool = False) -> None:
        if not self.api or self.busy:
            return
        self.busy = True
        try:
            async def staggered(delay, fn, *args):
                """错开启动，避免一秒钟内并发发出十多个请求触发 Kalshi 限流。"""
                if delay:
                    await asyncio.sleep(delay)
                return await run.io_bound(fn, *args)

            order_status = self.status_filter
            order_ticker = self.orders_ticker or None
            order_min_ts = None
            if order_status != "resting":
                watermark_status = (None if order_status in (None, "all")
                                    else order_status)
                last_ts = await run.io_bound(
                    db.last_order_ts, self.api.env, watermark_status, order_ticker)
                order_min_ts = last_ts - 60 if last_ts else None
            jobs = [
                staggered(0.0, self.api.balance),
                staggered(0.25, self.api.positions),
                # None = 完整翻页；有水位时增量通常只有一页，首次才同步全部历史。
                staggered(0.5, self.api.orders, order_status, order_ticker,
                          None, None, order_min_ts),
                staggered(0.75, self.api.subaccount_balances),
            ]
            with_fills = manual or self.ticks % 2 == 0
            if with_fills:
                jobs.append(staggered(1.0, self.api.fills,
                                      self.fills_ticker or None, self.fills_days))
            results = await asyncio.gather(*jobs, return_exceptions=True)

            errs = []
            loaded = {}

            def take(i: int, key: str) -> bool:
                r = results[i]
                if isinstance(r, Exception):
                    errs.append(f"{key}: {r}")
                    return False
                loaded[key] = r
                return True

            take(0, "balance")
            take(1, "positions")
            take(2, "orders")
            take(3, "subs")
            if with_fills:
                take(4, "fills")

            env, key_id = self.api.env, self.sess["key_id"]
            # 先增量落库，再从本地库读取渲染
            try:
                await run.io_bound(db.persist, env, key_id, **loaded)
            except Exception as ex:
                errs.append(f"本地库写入失败: {ex}")
            # ==== CF Benchmarks 刷新 ====
            try:
                await self._cf_discover()     # 10min 一次，自动跳过
                await self._ensure_cfb_sub()  # 启动/同步 CFB 实时订阅（幂等）
                await self._cf_fetch_and_persist()
                self.render_cf_overview()
            except Exception as ex:
                errs.append(f"CF Benchmarks 刷新失败: {ex}")
            # =============================
            try:
                state = await run.io_bound(
                    db.load_state, env, key_id, self.status_filter,
                    self.orders_ticker or None, self.fills_ticker or None,
                    self.fills_days, with_fills)
            except Exception as ex:
                errs.append(f"本地库读取失败: {ex}")
                state = {}
            if state:
                self.state.update(state)
                if "balance" in loaded:
                    self.render_balance()
                if "positions" in loaded:
                    self.render_positions()
                if "orders" in loaded:
                    self.render_orders()
                if "subs" in loaded:
                    self.render_subs()
                if with_fills and "fills" in loaded:
                    self.render_fills()

            self.ticks += 1
            limited = any("429" in e for e in errs)
            if limited:
                self.cooldown = time.time() + 10
            if errs:
                if lbl := self._el("updated_label"):
                    lbl.set_text("触发限流，10 秒后恢复" if limited else "部分同步失败")
                if manual:
                    self.notify(errs[0], type="negative")
            else:
                if lbl := self._el("updated_label"):
                    lbl.set_text(f"已同步 {datetime.now().strftime('%H:%M:%S')}")
        finally:
            self.busy = False

    async def refresh_orders(self) -> None:
        """刷新订单：分层增量拉取 → 落库 → 渲染。带重入保护 + loading 视觉。

        分层策略（避免 min_ts 漏掉 resting 订单的状态变更）：
          1) resting 订单：完整拉取（数量少、状态会变，必须全量）
          2) executed / canceled / 全部：按各自水位增量拉，并完整翻到 cursor 结束
        """
        if not self.api:
            return
        # 立即显示 loading（即使后面要排队等锁），保证切换有即时反馈
        self._orders_busy = True
        self._orders_pending += 1
        self._orders_busy_label(True)
        try:
          async with self._orders_lock:      # 串行化：多次快速切换会排队执行
            env = self.api.env
            ticker = self.orders_ticker or None
            # 锁内读取，保证用的是最新选中的状态
            status = self.status_filter
            all_rows: list = []
            resting_ok = False

            # === 1) resting 订单：API 是唯一权威来源（过期订单不应出现）===
            try:
                resting = await run.io_bound(self.api.orders, "resting", ticker, None, None)
                all_rows.extend(resting)
                await run.io_bound(db.save_orders, env, resting)
                # 用权威快照校正本地陈旧的 resting（到期/撤单但未在增量窗口内）
                keep = [o["order_id"] for o in resting if o.get("order_id")]
                await run.io_bound(db.reconcile_resting, env, keep, ticker)
                resting_ok = True
            except Exception:
                pass

            # === 2) 再按用户选中的状态增量拉 ===
            if status in (None, "all", "executed", "canceled"):
                # 各状态/ticker 独立水位，减 60s 重叠窗口防边界丢失。
                remote_status = None if status in (None, "all") else status
                last_ts = await run.io_bound(
                    db.last_order_ts, env, remote_status, ticker)
                min_ts = (last_ts - 60) if last_ts else None
                hist = await run.io_bound(
                    self.api.orders, remote_status, ticker, None, None, min_ts)
                all_rows.extend(hist)

            # === 3) 拉最近结算记录（供视图判定赢/输）===
            try:
                settle_rows = await run.io_bound(self.api.settlements, None, 200)
                if settle_rows:
                    await run.io_bound(db.save_settlements, env, settle_rows)
            except Exception:
                pass

            # === 4) 落库 + 渲染 ===
            if all_rows:
                await run.io_bound(db.save_orders, env, all_rows)
            if status == "resting" and not resting_ok:
                self.notify("在挂订单同步失败，当前显示本地缓存", type="warning")
            # 用锁内读到的 status 查询，避免中途切换导致读错筛选
            self.state["orders"] = await run.io_bound(
                db.orders, env, status, ticker)
            self.render_orders()
        except Exception as ex:
            self.notify(f"订单查询失败：{ex}", type="negative")
        finally:
            # 计数归零才关 loading：多次切换排队时保持遮罩直到最后一个完成
            self._orders_pending = max(0, self._orders_pending - 1)
            if self._orders_pending == 0:
                self._orders_busy = False
                self._orders_busy_label(False)

    async def refresh_positions(self) -> None:
        """持仓：API 拉最新全量 → 落库（不在快照里的会被删除）→ 渲染。
        带重入保护 + 表格 loading。持仓必须每次取最新，本地库只作缓存。"""
        if not self.api or self._pos_busy:
            return
        self._pos_busy = True
        self._table_loading("pos_table", True)
        try:
            env = self.api.env
            rows = await run.io_bound(self.api.positions)
            await run.io_bound(db.save_positions, env, rows)
            self.state["positions"] = await run.io_bound(db.positions, env)
            self.render_positions()
        except Exception as ex:
            self.notify(f"持仓刷新失败：{ex}", type="negative")
        finally:
            self._pos_busy = False
            self._table_loading("pos_table", False)

    def _table_loading(self, attr: str, on: bool) -> None:
        """给表格加/去 Quasar loading 遮罩（后台/切页时使用）。"""
        if tbl := self._el(attr):
            try:
                tbl.props(f"loading={'true' if on else 'false'}")
            except Exception:
                pass

    async def refresh_fills(self) -> None:
        """刷新成交：增量拉取 → 落库 → 渲染。带重入保护 + loading。"""
        if not self.api or self._fills_busy:
            return
        self._fills_busy = True
        self._fills_busy_label(True)
        try:
            env = self.api.env
            last_ts = await run.io_bound(db.last_fill_ts, env)
            min_ts = (last_ts - 60) if last_ts else None
            rows = await run.io_bound(
                self.api.fills, self.fills_ticker or None, self.fills_days,
                3, min_ts)
            await run.io_bound(db.save_fills, env, rows)
            self.state["fills"] = await run.io_bound(
                db.fills, env, self.fills_ticker or None, self.fills_days)
            self.render_fills()
        except Exception as ex:
            self.notify(f"成交查询失败：{ex}", type="negative")
        finally:
            self._fills_busy = False
            self._fills_busy_label(False)

    def _orders_busy_label(self, on: bool) -> None:
        """订单页同步中的视觉反馈：禁用状态切换 + 转圈加载条 + 表格遮罩。"""
        if lbl := getattr(self, "_orders_sync_label", None):
            try:
                lbl.set_text("同步中…" if on else "")
            except Exception:
                pass
        # 同步期间禁用 全部/在挂/已成交/已撤 切换，防止重复触发
        if tg := self._el("status_toggle"):
            try:
                if on:
                    tg.disable()
                else:
                    tg.enable()
            except Exception:
                pass
        # 转圈加载条
        sp = getattr(self, "_orders_spinner", None)
        if sp is not None:
            try:
                if not sp.is_deleted:
                    sp.set_visibility(on)
            except Exception:
                pass
        self._table_loading("order_table", on)

    def _fills_busy_label(self, on: bool) -> None:
        """成交页同步中的视觉反馈。"""
        self._table_loading("fill_table", on)

    async def refresh_transfers(self) -> None:
        if not self.api:
            return
        self._table_loading("tr_table", True)
        try:
            rows = await run.io_bound(self.api.subaccount_transfers, 50)
            await run.io_bound(db.save_transfers, self.api.env, rows)
            stored = await run.io_bound(db.transfers, self.api.env, 50)
            items = [{
                "id": r.get("transfer_id") or f"sub-{i}",
                "ts": r.get("created_ts"),
                "type": "子账户",
                "amount": usd(r.get("amount")),
                "frm": str(r.get("from_subaccount")),
                "to": str(r.get("to_subaccount")),
            } for i, r in enumerate(stored)]
            # 跨 shard 转账不在 subaccounts/transfers 里，必须单独查这个端点
            try:
                xrows = await run.io_bound(self.api.intra_exchange_transfers, 50)
            except Exception:
                xrows = []
            for i, r in enumerate(xrows):
                status = (r.get("status") or "").lower()
                items.append({
                    "id": r.get("transfer_id") or f"x-{i}",
                    "ts": r.get("created_ts"),
                    "type": "跨 shard" if status in ("", "complete", "completed")
                    else f"跨 shard（{status}）",
                    "amount": usd(r.get("amount")),
                    "frm": f"shard {r.get('from_shard')}",
                    "to": f"shard {r.get('to_shard')}",
                })
            items.sort(key=lambda x: float(x.get("ts") or 0), reverse=True)
            table = self._el("tr_table")
            if not table:
                return
            table.rows = [{
                "id": it["id"],
                "time": fmt_ts(it["ts"]),
                "type": it["type"],
                "amount": it["amount"],
                "from": it["frm"],
                "to": it["to"],
            } for it in items[:50]]
            table.update()
        except Exception as ex:
            self.notify(f"转账记录查询失败：{ex}", type="negative")
        finally:
            self._table_loading("tr_table", False)

    # ================= 渲染 =================
    def render_balance(self) -> None:
        b = self.state.get("balance") or {}
        if c_avail := self._el("c_avail"):
            c_avail.set_text(usd(b.get("available")))
            if c_avail_ts := self._el("c_avail_ts"):
                c_avail_ts.set_text(
                    f"本地库同步于 {fmt_ts(b.get('synced_at'))}" if b.get("synced_at")
                    else "尚无本地快照")
        if lbl := self._el("updated_label"):
            lbl.set_text(
                f"本地快照 · {fmt_ts(b.get('synced_at'))}" if b.get("synced_at")
                else "本地快照")
        pos = self.state.get("positions") or []
        expo = sum(p.get("exposure") or 0 for p in pos)
        pnl = sum(p.get("realized_pnl") or 0 for p in pos)
        if c_expo := self._el("c_expo"):
            c_expo.set_text(usd(expo))
            if c_pnl := self._el("c_pnl"):
                c_pnl.set_text(usd(pnl, signed=True))
            resting = sum(1 for o in (self.state.get("orders") or [])
                          if (o.get("status") == "resting"))
            if c_rest := self._el("c_rest"):
                c_rest.set_text(str(resting))
            if c_subs := self._el("c_subs"):
                c_subs.set_text(str(len(self.state.get("subs") or [])))

        if table := self._el("shard_table"):
            shards = b.get("shards") or []
            total = sum(s.get("balance") or 0 for s in shards)
            table.rows = [{
                "id": str(s.get("exchange_index")),
                "shard": str(s.get("exchange_index")),
                "balance": usd(s.get("balance")),
                "pct": f"{(s.get('balance') or 0) / total * 100:.1f}%" if total else "—",
            } for s in shards]
            table.update()
        # 跨 shard 转账表单旁显示各分片当前余额，避免转到没有资金的分片
        if hint := self._el("x_bal_hint"):
            shards = b.get("shards") or []
            hint.set_text("各分片余额：" + "　".join(
                f"shard {s.get('exchange_index')} {usd(s.get('balance'))}"
                for s in shards) if shards else "各分片余额：—")

    def render_subs(self) -> None:
        subs = self.state.get("subs") or []
        rows = [{
            "id": f"{s.get('exchange_index')}-{s.get('subaccount')}",
            "shard": "—" if s.get("exchange_index") is None else str(s.get("exchange_index")),
            "sub": "—" if s.get("subaccount") is None else str(s.get("subaccount")),
            "balance": usd(s.get("balance")),
            "updated": fmt_ts(s.get("updated_ts")),
        } for s in subs]
        if table := self._el("sub_table"):
            table.rows = rows
            table.update()
        if mini := self._el("sub_mini"):
            mini.rows = rows[:50]
            mini.update()
        if lbl := self._el("c_subs"):
            lbl.set_text(str(len(subs)))

    def render_positions(self) -> None:
        positions = self.state.get("positions") or []
        self.pos_by_ticker = {p["ticker"]: p for p in positions}
        if table := self._el("pos_table"):
            table.rows = [{
                "id": p["ticker"],
                "ticker": p["ticker"],
                "side": "YES" if p["yes_qty"] > 0 else "NO",
                "qty": f"{int(p['yes_qty'] or p['no_qty'])}",
                "exposure": usd(p.get("exposure")),
                "pnl": usd(p.get("realized_pnl"), signed=True),
                "resting": str(p.get("resting") or 0),
                "shard": "—" if p.get("exchange_index") is None else str(p.get("exchange_index")),
            } for p in positions]
            table.update()
        if c_expo := self._el("c_expo"):
            c_expo.set_text(usd(sum(p.get("exposure") or 0 for p in positions)))
            if c_pnl := self._el("c_pnl"):
                c_pnl.set_text(
                    usd(sum(p.get("realized_pnl") or 0 for p in positions), signed=True))

    def render_orders(self) -> None:
        orders = self.state.get("orders") or []
        self.order_by_id = {o["order_id"]: o for o in orders if o.get("order_id")}
        if table := self._el("order_table"):
            table.rows = [{
                "id": o["order_id"],
                "time_utc": fmt_dt(o.get("created_utc") or o.get("created")),
                "time_et": fmt_dt(o.get("created_et")),
                "time_bj": fmt_dt(o.get("created_bj")),
                "ticker": o.get("ticker") or "",
                "side": o.get("side_txt") or "",
                "price": usd(o.get("price")),
                "count": f"{(o.get('count') or 0):g}",
                "filled": f"{(o.get('filled') or 0):g}",
                "remaining": f"{(o.get('remaining') or 0):g}",
                "status": o.get("status") or "",
                "result": o.get("settle_result") or "",
                "shard": "—" if o.get("exchange_index") is None else str(o.get("exchange_index")),
            } for o in orders]
            table.update()
        if c_rest := self._el("c_rest"):
            c_rest.set_text(str(sum(1 for o in orders if o.get("status") == "resting")))

    def render_fills(self) -> None:
        fills = self.state.get("fills") or []
        table = self._el("fill_table")
        if not table:
            return
        table.rows = [{
            "id": f.get("fill_id") or f.get("trade_id") or f"f-{i}",
            "time": fmt_ts(f.get("created")),
            "ticker": f.get("ticker") or "",
            "action": "买入" if f.get("action") == "buy" else ("卖出" if f.get("action") == "sell" else "—"),
            "side": (f.get("side") or "—").upper(),
            "price": usd(f.get("price")),
            "count": f"{(f.get('count') or 0):g}",
            "role": "Taker" if f.get("is_taker") else "Maker",
            "order": (f.get("order_id") or "")[:18],
        } for i, f in enumerate(fills)]
        table.update()

    # ================= 下单 / 平仓 =================
    async def prompt_text(self, title: str) -> str:
        with self.root:
            d = ui.dialog()
            with d, ui.card().classes("w-[400px] gap-2"):
                ui.label(title).classes("font-semibold")
                inp = ui.input("新值").classes("w-full").props("dense outlined")
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("取消", on_click=lambda: d.submit("")).props("flat")
                    ui.button("确定", on_click=lambda: d.submit(inp.value or "")) \
                        .props("unelevated")
        value = await d
        d.delete()
        return str(value or "").strip()

    async def confirm(self, text: str) -> bool:
        with self.root:
            d = ui.dialog()
            with d, ui.card().classes("w-[440px] gap-2"):
                ui.label("请确认").classes("font-semibold")
                ui.label(text).classes("text-sm whitespace-pre-line")
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("取消", on_click=lambda: d.submit(False)).props("flat")
                    ui.button("确认", on_click=lambda: d.submit(True)) \
                        .props("unelevated color=negative")
        result = bool(await d)
        d.delete()
        return result

    async def open_trade(self, ticker: str = "", leg: Optional[str] = None,
                         qty: Optional[int] = None,
                         prefer_tif: str = "immediate_or_cancel",
                         momentum: bool = False) -> None:
        if not self.api:
            return
        if self._trade_opening:
            return
        self._trade_opening = True
        _t0 = time.perf_counter()
        try:
            self._stop_trade_chart()
            self.trade_dlg.clear()
            quote = None
            qerr = ""
            if ticker:
                try:
                    quote = await run.io_bound(self.api.quote, ticker)
                except Exception as ex:
                    qerr = f"行情获取失败：{ex}"
                if quote and quote.get("status") and quote["status"] not in ("active", None):
                    # 持仓对应市场已关闭/结算，禁止进入下单流程
                    self.notify(
                        f"市场 {ticker} 当前状态：{quote['status']}，不可下单",
                        type="warning")
                    return
            pos = self.pos_by_ticker.get(ticker)
            _t_quote = time.perf_counter()
            # 市场目录（series）几乎不变，按三级缓存取用：
            #   1) 本次会话已加载且环境未变 → 直接用内存
            #   2) 本地 DuckDB 缓存 → 读库（首次运行或换环境后）
            #   3) 都没有 → 全量拉 /series 并落库
            mem_hit = bool(self._catalog and self._catalog_env == self.api.env)
            catalog = (self._catalog if mem_hit else [])
            if not catalog:
                try:
                    catalog = await run.io_bound(db.series_catalog, self.api.env)
                except Exception as ex:
                    qerr = qerr or f"本地市场目录读取失败：{ex}"
                if not catalog:
                    try:
                        catalog = await run.io_bound(self.api.series_catalog)
                        await run.io_bound(db.save_series_catalog, self.api.env, catalog)
                    except Exception as ex:
                        qerr = qerr or f"市场目录获取失败：{ex}"
                self._catalog_env = self.api.env
            self._catalog = [s for s in catalog
                             if s["category"] and "test" not in s["category"].lower()]
            _t_catalog = time.perf_counter()
            print(f"[open_trade] quote={_t_quote-_t0:.2f}s catalog={_t_catalog-_t_quote:.2f}s "
                  f"mem_hit={mem_hit} rows={len(self._catalog)}")
            cats = sorted({s["category"] for s in self._catalog})
            cat = "Crypto" if "Crypto" in cats else (cats[0] if cats else None)

            pre_series, pre_markets = None, []
            if ticker and quote and quote.get("event_ticker"):
                try:
                    pre_series = await run.io_bound(self.api.event_series,
                                                    quote["event_ticker"])
                    pre_markets = await run.io_bound(self.api.markets_by_series, pre_series)
                except Exception:
                    pre_series = None
            pre_item = next((s for s in self._catalog if s["ticker"] == pre_series), None)
            if pre_item:
                cat = pre_item["category"]
            freqs = self._freqs_for(cat)
            freq = freqs[0] if freqs else None
            if pre_item and pre_item["frequency"] in freqs:
                freq = pre_item["frequency"]
            series_opts = self._series_options(cat, freq)
            mk_options = {m["ticker"]: m["label"] for m in pre_markets} if pre_series else {}

            with self.trade_dlg, ui.card().classes("w-[820px] max-w-[96vw] gap-3"):
                with ui.row().classes("w-full items-center"):
                    ui.label("动量下单" if momentum else "下单 / 平仓") \
                        .classes("text-lg font-semibold")
                    if momentum:
                        ui.badge("自动跟随上涨腿 · 实时取价 · 成交后立即止盈") \
                            .props("color=positive flat").classes("text-[10px]")
                    ui.space()
                    ui.button(icon="close", on_click=self.trade_dlg.close).props("flat round dense")

                with ui.row().classes("w-full gap-3 items-end no-wrap"):
                    self.cat_select = ui.select(
                        {c: CATEGORY_CN.get(c, c) for c in cats}, value=cat, label="分类") \
                        .classes("w-48").props("dense outlined")
                    self.freq_select = ui.select(
                        {f: FREQ_CN.get(f, f) for f in freqs}, value=freq, label="周期") \
                        .classes("w-40").props("dense outlined")
                    self._api_btn(icon="refresh", coro=self.reload_catalog) \
                        .props("flat dense").tooltip("刷新市场目录")
                with ui.row().classes("w-full gap-3 items-end no-wrap"):
                    self.ser_select = ui.select(dict(sorted(series_opts.items())),
                                                value=pre_series or None, label="选择市场",
                                                with_input=True) \
                        .classes("flex-1").props("dense outlined")
                    self.tk_select = ui.select(dict(sorted(mk_options.items())),
                                               value=ticker or None, label="选择 ticker",
                                               with_input=True) \
                        .classes("flex-1").props("dense outlined")
                self.q_info = ui.label(qerr or (quote or {}).get("title") or
                                       "选择市场与 ticker 后自动加载行情").classes("text-xs kd-mut")
                self.q_line = ui.label("").classes("text-sm font-mono")
                self.q_pos = ui.label("").classes("text-sm")
                with ui.card().classes("w-full gap-1 p-2 rounded-lg").props("flat dense"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.label("实时成交 · DuckDB").classes("kd-section")
                        ui.space()
                        self.trade_chart_info = ui.label("选择 ticker 后按所属市场自动订阅并绘图") \
                            .classes("text-xs kd-mut")
                    self.trade_chart = ui.echart(self._trade_chart_options(
                        [], self._ts_epoch((quote or {}).get("open_time")),
                        self._ts_epoch((quote or {}).get("close_time")))) \
                        .classes("w-full h-52")
                # CF Benchmarks 面板（选中 CF 类市场时动态渲染水位 + 曲线 + 差值）
                self.cfb_card = ui.card().classes("w-full gap-1 p-2 rounded-lg").props("flat dense")
                self.cfb_card.visible = False
                # CF vs Invest BTC 价差图：独立卡片，原地更新，避免被 CF 面板重绘清掉
                self.cf_spread_card = ui.card().classes("w-full gap-1 p-2 rounded-lg") \
                    .props("flat dense")
                self.cf_spread_card.visible = False
                with self.cf_spread_card:
                    with ui.row().classes("w-full items-center gap-2"):
                        self.cf_spread_title = ui.label("KXBTCPERP − CF 价差") \
                            .classes("text-xs font-mono kd-mut")
                        self.cf_spread_range = ui.toggle(
                            {"30m": "30m", "1h": "1h", "2h": "2h"},
                            value="2h") \
                            .props("spread dense no-caps").classes("text-[10px]")
                        self.cf_spread_range.on_value_change(
                            lambda e: asyncio.ensure_future(self._render_cf_spread()))
                        ui.space()
                        self.cf_spread_value = ui.label("—").classes("text-xs font-mono")
                    self.cf_spread_hint = ui.label("等待数据…") \
                        .classes("text-xs kd-mut italic")
                    self.cf_spread_chart = ui.echart({
                        "xAxis": {"type": "time"}, "yAxis": {"type": "value"},
                        "series": [],
                    }).classes("w-full h-36")
                    self.cf_spread_chart.visible = False

                if momentum:
                    # ===== 动量下单面板（方向/买价/止盈价全部自动，无可手填价格）=====
                    self.act_toggle = None
                    self.px_input = None
                    self.post_only = None
                    self.est_label = None
                    with ui.card().classes("w-full gap-2 p-3 rounded-lg") \
                            .props("flat").style("border:1px solid #1f2a24;"):
                        with ui.row().classes("w-full items-center gap-3"):
                            ui.label("上涨腿").classes("text-xs kd-mut")
                            self.mo_dir_label = ui.label("选择 ticker 后自动检测") \
                                .classes("text-base font-semibold font-mono")
                            self.mo_trend_label = ui.label("") \
                                .classes("text-xs kd-mut font-mono")
                            ui.space()
                            self.mo_px_label = ui.label("买价 —") \
                                .classes("text-sm font-mono")
                            self.mo_tp_label = ui.label("止盈 —") \
                                .classes("text-sm font-mono")
                    with ui.row().classes("w-full gap-3 items-end"):
                        self.mo_mult_input = ui.number("止盈倍率", value=1.10,
                                                       min=1.01, max=3.0, step=0.05,
                                                       precision=2).classes("w-36")
                        self.qty_input = ui.number("数量（张）", value=qty or 1, min=1,
                                                   precision=0).classes("w-32")
                        self.sub_input = ui.number("子账户", value=0, min=0,
                                                   precision=0).classes("w-28")
                        self.tif_toggle = ui.toggle(
                            {"immediate_or_cancel": "IOC 立即成交",
                             "good_till_canceled": "GTC 挂单"},
                            value="immediate_or_cancel").props("dense")
                    self.mo_hint = ui.label(
                        "下单瞬间拉最新盘口：买入价取该腿卖一价，止盈价 = 买价 × 倍率（向上取整到 0.01）；"
                        "买单成交后立即挂 GTC 止盈卖单，不等结算") \
                        .classes("text-xs kd-mut italic")
                    with ui.row().classes("w-full justify-end gap-2"):
                        self._api_btn("刷新行情", icon="refresh",
                                      coro=self.reload_quote).props("flat")
                        self._api_btn("动量买入", icon="trending_up",
                                      coro=self._submit_momentum_trade) \
                            .props("unelevated color=positive")
                else:
                    default_action = "sell_yes" if leg == "yes" else ("sell_no" if leg == "no" else "buy_yes")
                    self.act_toggle = ui.toggle(dict(ACTION_LABEL), value=default_action) \
                        .props("spread dense no-caps").classes("kd-actions")
                    with ui.row().classes("w-full gap-3 items-end"):
                        self.px_input = ui.number("价格（所选合约，美元）", value=0.5,
                                                  min=0.01, max=0.99, step=0.01,
                                                  precision=2).classes("w-52")
                        self.qty_input = ui.number("数量（张）", value=qty or 1, min=1,
                                                   precision=0).classes("w-36")
                        self.sub_input = ui.number("子账户", value=0, min=0,
                                                   precision=0).classes("w-32")
                        self.tif_toggle = ui.toggle(
                            {"immediate_or_cancel": "IOC 立即成交", "good_till_canceled": "GTC 挂单"},
                            value=prefer_tif).props("dense")
                    with ui.row().classes("w-full gap-3 items-center"):
                        self.post_only = ui.checkbox("只做 maker（post-only）")
                        self.est_label = ui.label("").classes("text-sm kd-mut")
                    with ui.row().classes("w-full justify-end gap-2"):
                        self._api_btn("刷新行情", icon="refresh", coro=self.reload_quote).props("flat")
                        self._api_btn("提交订单", icon="send", coro=self.submit_trade).props("unelevated")

                self._set_quote(quote)
                if not momentum:
                    self.act_toggle.on_value_change(lambda e: self._on_action_change(e.value))
                self.cat_select.on_value_change(lambda e: self._on_category_pick(e.value))
                self.freq_select.on_value_change(lambda e: self._on_freq_pick())
                self.ser_select.on_value_change(
                    lambda e: asyncio.create_task(self._on_series_pick(e.value)))
                self.tk_select.on_value_change(
                    lambda e: asyncio.create_task(self._on_market_pick(e.value)))
                if momentum:
                    self.mo_mult_input.on_value_change(lambda _: self._render_momentum_panel())
                    self.qty_input.on_value_change(lambda _: self._render_momentum_panel())
                else:
                    for el in (self.px_input, self.qty_input):
                        el.on_value_change(lambda _: self._update_est())

            self._trade_momentum = momentum
            if not momentum:
                self._on_action_change(default_action)
                self._update_est()
            self._trade_chart_ticker = ticker or ""
            # open_trade 由后台任务执行，await 后没有默认 slot；计时器必须显式挂到对话框。
            with self.trade_dlg:
                self._trade_chart_timer = ui.timer(2.0, self.refresh_trade_chart)
                self._cf_quote_timer = ui.timer(2.0, self.refresh_cf_quote_panel)
                if momentum:
                    self._mo_timer = ui.timer(2.0, self._refresh_momentum_panel)
            self.trade_dlg.open()
            if ticker:
                asyncio.create_task(self._activate_trade_chart(ticker))
            if momentum:
                if ticker:
                    asyncio.create_task(self._refresh_momentum_panel())
                else:
                    self._render_momentum_panel()
            print(f"[open_trade] total={time.perf_counter()-_t0:.2f}s")
        finally:
            self._trade_opening = False

    def _freqs_for(self, category: Optional[str]) -> list:
        found = {s["frequency"] for s in self._catalog
                 if s["category"] == category and s["frequency"]}
        ordered = [f for f in FREQ_ORDER if f in found]
        return ordered + sorted(found - set(ordered))

    def _series_options(self, category: Optional[str],
                        freq: Optional[str]) -> dict:
        return {s["ticker"]: s["title"] for s in self._catalog
                if s["category"] == category and s["frequency"] == freq}

    def _apply_series_filter(self) -> None:
        self.ser_select.options = self._series_options(
            self.cat_select.value, self.freq_select.value)
        self.ser_select.value = None
        self.ser_select.update()
        self.tk_select.options = {}
        self.tk_select.value = None
        self.tk_select.update()

    def _on_category_pick(self, category: Optional[str]) -> None:
        freqs = self._freqs_for(category)
        self.freq_select.options = {f: FREQ_CN.get(f, f) for f in freqs}
        self.freq_select.value = freqs[0] if freqs else None
        self.freq_select.update()
        self._apply_series_filter()

    def _on_freq_pick(self) -> None:
        self._apply_series_filter()

    async def reload_catalog(self) -> None:
        try:
            catalog = await run.io_bound(self.api.series_catalog, True)
        except Exception as ex:
            self.notify(f"市场目录刷新失败：{ex}", type="negative")
            return
        # 强制刷新后写回本地缓存，下次打开下单框直接读库
        try:
            await run.io_bound(db.save_series_catalog, self.api.env, catalog)
        except Exception as ex:
            self.notify(f"市场目录写入本地库失败：{ex}", type="negative")
        self._catalog = [s for s in catalog
                         if s["category"] and "test" not in s["category"].lower()]
        self._catalog_env = self.api.env
        cats = sorted({s["category"] for s in self._catalog})
        self.cat_select.options = {c: CATEGORY_CN.get(c, c) for c in cats}
        if self.cat_select.value not in cats:
            self.cat_select.value = "Crypto" if "Crypto" in cats else (cats[0] if cats else None)
        self.cat_select.update()
        freqs = self._freqs_for(self.cat_select.value)
        self.freq_select.options = {f: FREQ_CN.get(f, f) for f in freqs}
        if self.freq_select.value not in freqs:
            self.freq_select.value = freqs[0] if freqs else None
        self.freq_select.update()
        self._apply_series_filter()
        self.notify(f"市场目录已刷新（{len(cats)} 个分类）", type="positive")

    async def _on_series_pick(self, series_ticker: Optional[str]) -> None:
        if not series_ticker:
            return
        try:
            rows = await run.io_bound(self.api.markets_by_series, series_ticker)
        except Exception as ex:
            self.notify(f"ticker 列表获取失败：{ex}", type="negative")
            return
        self.tk_select.options = {m["ticker"]: m["label"] for m in rows}
        self.tk_select.value = None
        self.tk_select.update()
        if not rows:
            self.notify("该市场当前没有在交易的 ticker", type="warning")
        elif len(rows) == 1:
            self.tk_select.value = rows[0]["ticker"]
            self._trade_chart_ticker = rows[0]["ticker"]
            await asyncio.gather(
                self.reload_quote(), self._activate_trade_chart(rows[0]["ticker"]))

    async def _on_market_pick(self, ticker: Optional[str]) -> None:
        self._trade_chart_ticker = ticker or ""
        if ticker:
            await asyncio.gather(self.reload_quote(), self._activate_trade_chart(ticker))
        else:
            if chart := self._el("trade_chart"):
                chart.options.clear()
                chart.options.update(self._trade_chart_options([]))
                chart.update()
            if info := self._el("trade_chart_info"):
                info.set_text("选择 ticker 后按所属市场自动订阅并绘图")

    def _on_trade_dialog_change(self, e) -> None:
        if not e.value:
            self._stop_trade_chart()
            if self._cf_quote_timer is not None:
                self._cf_quote_timer.active = False
                self._cf_quote_timer = None
            if getattr(self, "_mo_timer", None) is not None:
                self._mo_timer.active = False
                self._mo_timer = None

    def _stop_trade_chart(self) -> None:
        if self._trade_chart_timer is not None:
            self._trade_chart_timer.active = False
            self._trade_chart_timer = None
        self._trade_chart_ticker = ""

    async def _activate_trade_chart(self, ticker: str) -> None:
        """选中 ticker 时订阅其所属市场，由后台自动轮换该市场的 ticker。"""
        if not (self.api and self.sess):
            return
        try:
            sub = self._ws_subscriber()
            series_ticker = self.ser_select.value or ticker.split("-", 1)[0]
            await sub.add_series(series_ticker)
            if ticker not in sub.tickers:
                await sub.refresh_markets()
            await sub.start()
        except Exception as ex:
            if ticker == self._trade_chart_ticker:
                self.notify(f"实时成交订阅失败：{ex}", type="negative")
            return
        await self.refresh_trade_chart()

    @staticmethod
    def _ts_epoch(value) -> Optional[float]:
        """把 Kalshi 的 ISO/秒/毫秒时间转成 epoch 秒，失败返回 None。"""
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            v = float(value)
            return v / 1000.0 if v > 1e11 else v
        try:
            text = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(text).timestamp()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _aggregate_trades_per_second(rows: list) -> list:
        """把逐笔成交按秒聚合：VWAP 作为该秒价格，count 求和。"""
        buckets: dict[int, list] = {}
        for r in rows:
            if r.get("price") is None or r.get("ts") is None:
                continue
            sec = int(r["ts"])
            price = float(r["price"])
            qty = float(r.get("count") or 0.0)
            b = buckets.setdefault(sec, [0.0, 0.0, 0])
            b[0] += price * qty
            b[1] += qty
            b[2] += 1
        return [{
            "ts": sec,
            "price": (b[0] / b[1]) if b[1] else None,
            "count": b[1],
            "trades": b[2],
        } for sec, b in sorted(buckets.items()) if b[1]]

    @staticmethod
    def _trade_chart_options(rows: list,
                             open_ts: Optional[float] = None,
                             close_ts: Optional[float] = None) -> dict:
        data = [[int(r["ts"]) * 1000, r.get("price"), r.get("count") or 0.0]
                for r in rows if r.get("price") is not None]
        xaxis = {"type": "time", "axisLabel": {"fontSize": 9, "color": "#888"},
                 "axisLine": {"lineStyle": {"color": "#333"}}}
        # X 轴固定在该 ticker 的市场时间范围内
        if open_ts is not None:
            xaxis["min"] = int(open_ts * 1000)
        if close_ts is not None:
            xaxis["max"] = int(close_ts * 1000)
        show_symbol = len(data) <= 120
        return {
            "animationDurationUpdate": 250,
            "grid": {"left": 52, "right": 48, "top": 16, "bottom": 34},
            "tooltip": {"trigger": "axis"},
            "xAxis": xaxis,
            "yAxis": [
                {"type": "value", "name": "YES $", "scale": True, "min": 0, "max": 1,
                 "axisLabel": {"fontSize": 9, "color": "#888"},
                 "splitLine": {"lineStyle": {"color": "#222"}}},
                {"type": "value", "name": "张数", "scale": True,
                 "axisLabel": {"fontSize": 9, "color": "#888"},
                 "splitLine": {"show": False}},
            ],
            "dataZoom": [{"type": "inside", "start": 0, "end": 100}],
            "series": [
                {"name": "成交价", "type": "line", "data": data,
                 "encode": {"x": 0, "y": 1}, "showSymbol": show_symbol,
                 "symbolSize": 4,
                 "lineStyle": {"color": "#35e0a1", "width": 1.6},
                 "itemStyle": {"color": "#35e0a1"}},
                {"name": "成交张数", "type": "bar", "yAxisIndex": 1, "data": data,
                 "encode": {"x": 0, "y": 2},
                 "itemStyle": {"color": "rgba(139,147,163,.25)"}},
            ],
        }

    async def refresh_trade_chart(self) -> None:
        ticker = self._trade_chart_ticker
        if (self._trade_chart_busy or not ticker or not self.api
                or not self._el("trade_chart") or not self.trade_dlg.value):
            return
        self._trade_chart_busy = True
        try:
            q = self._quote or {}
            open_ts = self._ts_epoch(q.get("open_time"))
            close_ts = self._ts_epoch(q.get("close_time"))
            raw, live = await asyncio.gather(
                run.io_bound(
                    db.market_trades_range, self.api.env, ticker,
                    int(open_ts) if open_ts else None,
                    int(close_ts) if close_ts else None),
                self._safe_quote(ticker),
            )
            if ticker != self._trade_chart_ticker or not self.trade_dlg.value:
                return
            # 行情条同图一起刷新，取最新买一/卖一/最新价
            if live:
                self._apply_live_quote(live)
            rows = self._aggregate_trades_per_second(raw)
            chart = self._el("trade_chart")
            if not chart:
                return
            chart.options.clear()
            chart.options.update(self._trade_chart_options(rows, open_ts, close_ts))
            chart.update()
            snap = self._ws_subscriber().snapshot()
            if info := self._el("trade_chart_info"):
                if rows:
                    last = rows[-1]
                    info.set_text(
                        f"{ticker} · {len(raw)} 笔 → 秒聚合 {len(rows)} 点 · "
                        f"最新 {usd(last.get('price'))} · {fmt_ts(last.get('ts'))} · "
                        f"{snap['status']}")
                else:
                    info.set_text(f"{ticker} 已加入订阅，等待首笔成交 · {snap['status']}")
        except Exception as ex:
            if info := self._el("trade_chart_info"):
                info.set_text(f"成交图加载失败：{str(ex)[:120]}")
        finally:
            self._trade_chart_busy = False

    async def _safe_quote(self, ticker: str) -> Optional[dict]:
        """拉取最新行情，失败静默返回 None（不打断图的刷新）。"""
        try:
            return await run.io_bound(self.api.quote, ticker)
        except Exception:
            return None

    @staticmethod
    def _price_line_text(quote: dict) -> str:
        return (
            f"YES 买一 {usd(quote.get('yes_bid'))} / 卖一 {usd(quote.get('yes_ask'))}    "
            f"NO 买一 {usd(quote.get('no_bid'))} / 卖一 {usd(quote.get('no_ask'))}    "
            f"最新 {usd(quote.get('last'))}"
        )

    def _apply_live_quote(self, quote: dict) -> None:
        """只把最新买卖价并入当前行情条，不重绘 CF 面板、不动用户输入的价格。"""
        cur = self._quote
        if not cur or quote.get("ticker") != cur.get("ticker"):
            return
        for k in ("yes_bid", "yes_ask", "no_bid", "no_ask", "last", "status"):
            cur[k] = quote.get(k)
        if line := self._el("q_line"):
            line.set_text(self._price_line_text(cur))

    def _set_quote(self, quote: Optional[dict]) -> None:
        self._quote = quote
        if not quote:
            self.q_line.set_text("")
            self._cfb_hide()
            return
        p = self.pos_by_ticker.get(quote.get("ticker") or "")
        self.q_line.set_text(self._price_line_text(quote))
        self.q_info.set_text(
            f"{quote.get('title') or ''}　状态：{quote.get('status') or '—'}"
            f"　收盘：{fmt_ts(quote.get('close_time'))}")
        if p:
            self.q_pos.set_text(
                f"当前持仓：YES {int(p['yes_qty'])} 张 / NO {int(p['no_qty'])} 张"
                f"　敞口 {usd(p.get('exposure'))}")
        else:
            self.q_pos.set_text("当前持仓：无")
        # 触发 CF Benchmarks 面板异步渲染
        asyncio.create_task(self._render_cfb_panel(quote))

    def _cfb_hide(self) -> None:
        """隐藏 CF 面板并清空内容。"""
        if card := self._el("cfb_card"):
            card.clear()
            card.visible = False
        if card := self._el("cf_spread_card"):
            card.visible = False

    @staticmethod
    def _fmt_duration(sec: Optional[float]) -> str:
        if sec is None or sec < 0 or sec != sec:
            return "—"
        sec = int(round(sec))
        if sec >= 3600:
            return f"{sec // 3600}小时{(sec % 3600) // 60}分"
        if sec >= 60:
            return f"{sec // 60}分{sec % 60:02d}秒"
        return f"{sec}秒"

    @staticmethod
    def _cf_rate_per_sec(recent: list) -> Optional[float]:
        """用最近一段 CF tick 做线性回归，返回 USD/秒 的变化速率。"""
        pts = [(int(r["time_ms"]) / 1000.0, float(r["value"])) for r in recent
               if r.get("time_ms") and r.get("value") is not None]
        if len(pts) < 3:
            return None
        pts.sort(key=lambda x: x[0])
        span = pts[-1][0] - pts[0][0]
        if span < 20:
            return None
        mx = sum(p[0] for p in pts) / len(pts)
        my = sum(p[1] for p in pts) / len(pts)
        var = sum((p[0] - mx) ** 2 for p in pts)
        if var <= 0:
            return None
        cov = sum((p[0] - mx) * (p[1] - my) for p in pts)
        return cov / var

    @classmethod
    def _cf_reach_metric(cls, recent: list, cur: Optional[float],
                         strike: Optional[float], close_ts: Optional[float],
                         now_ts: float, is_below: bool = False) -> Optional[dict]:
        """达成时间指标：以当前速率到目标的耗时 vs 距收盘剩余时间。"""
        if cur is None or strike is None:
            return None
        rate = cls._cf_rate_per_sec(recent)
        rate_min = (rate * 60.0) if rate is not None else None
        remaining = (close_ts - now_ts) if close_ts else None
        if remaining is not None and remaining < 0:
            remaining = 0.0
        if rate is None:
            return {"ok": None, "text": "速率样本不足，暂无法估算",
                    "rate_min": None, "eta": None, "remaining": remaining}
        # 已处于 YES 区间：判断按当前速率能否保持到收盘
        already = (cur <= strike) if is_below else (cur >= strike)
        if already:
            holding = (rate > 0) if is_below else (rate < 0)   # 朝不利方向
            if not holding:
                text = "已 YES，当前速率向上/持平，可保持至收盘"
                ok = True
                eta = None
            else:
                eta = abs(cur - strike) / abs(rate)
                if remaining is None:
                    text = f"已 YES，按当前速率约 {cls._fmt_duration(eta)} 后跌破"
                    ok = None
                else:
                    ok = eta >= remaining
                    text = (f"已 YES，按当前速率约 {cls._fmt_duration(eta)} 后跌破，"
                            f"{'可保持到收盘' if ok else '早于收盘'}")
            return {"ok": ok, "text": text, "rate_min": rate_min,
                    "eta": eta, "remaining": remaining}
        # 尚未达成：需要朝目标方向移动
        need_up = not is_below
        approaching = (rate > 0) if need_up else (rate < 0)
        if not approaching:
            text = ("按当前速率无法达成（方向相反）" if remaining is None
                    else f"按当前速率无法达成，剩余 {cls._fmt_duration(remaining)}")
            return {"ok": False, "text": text, "rate_min": rate_min,
                    "eta": None, "remaining": remaining}
        eta = abs(strike - cur) / abs(rate)
        if remaining is None:
            text = f"预计 {cls._fmt_duration(eta)} 后达成（缺少收盘时间）"
            ok = None
        else:
            ok = eta <= remaining
            if ok:
                text = (f"预计 {cls._fmt_duration(eta)} 后达成，"
                        f"距收盘还有 {cls._fmt_duration(remaining)}")
            else:
                text = (f"预计 {cls._fmt_duration(eta)} 后达成，"
                        f"晚于收盘 {cls._fmt_duration(eta - remaining)}")
        return {"ok": ok, "text": text, "rate_min": rate_min,
                "eta": eta, "remaining": remaining}

    @staticmethod
    def _cf_strike_from_ticker(ticker: str) -> Optional[float]:
        """从 ticker 末段兜底解析目标价。

        支持两种真实格式：
        - KXBTCD-26NOV1717-T73749.99 / -B73625 → 去前缀 T/B
        - KXBTCMAXY-26DEC31-67000 → 纯数字
        注意 KXBTC15M-26NOV162215-15 的末段 15 是市场序号，不是目标价，
        这类 15 分钟系列必须走 market.floor_strike。
        """
        if not ticker:
            return None
        series = ticker.split("-", 1)[0].upper()
        tail = ticker.rsplit("-", 1)[-1].strip()
        if tail[:1] in ("T", "B") and tail[1:].replace(".", "", 1).isdigit():
            return float(tail[1:])
        if tail.replace(".", "", 1).isdigit():
            val = float(tail)
            if "15M" in series or val < 100:
                return None
            return val
        return None

    async def _render_cfb_panel(self, quote: dict) -> None:
        """异步渲染 CF Benchmarks 面板：水位 + 曲线 + 差值。

        - ticker 不是 CF 标的 → 隐藏面板
        - 是 CF 标的但 DuckDB 里还没数据 → 显示占位文字
        - 有数据 → 画 ECharts 折线 + 显示实时价/目标价/差值
        """
        ticker = quote.get("ticker", "")
        idx_id = self.cf_index_id_for_ticker(ticker)
        if not idx_id:
            self._cfb_hide()
            return
        if not self.api:
            self._cfb_hide()
            return
        card = self._el("cfb_card")
        if not card:
            return
        # 查 DuckDB 历史（24h 画图 + 5min 算速率）
        try:
            history, recent, latest = await asyncio.gather(
                run.io_bound(db.cfb_history, self.api.env, idx_id,
                             hours=24.0, limit=300),
                run.io_bound(db.cfb_history, self.api.env, idx_id,
                             hours=5.0 / 60.0, limit=600),
                run.io_bound(db.cfb_latest, self.api.env, [idx_id]),
            )
        except Exception:
            history, recent, latest = [], [], {}
        latest = latest or {}
        history = history or []
        recent = recent or []
        # 优先用 WS 实时快照，避免 DB 里还是上一秒的值
        if self.cfb_latest.get(idx_id):
            latest[idx_id] = self.cfb_latest[idx_id]
        card.clear()
        card.visible = True
        # 第一行：CF 关联状态
        sym = self._cf_sym_label(idx_id)
        with card:
            with ui.row().classes("w-full items-center gap-2 text-xs"):
                ui.icon("insights").classes("text-[var(--kd-accent)]")
                ui.label(f"CF Benchmarks · {sym} ({idx_id})").classes("font-mono kd-mut")
                ui.space()
                if latest.get(idx_id):
                    cf_val = latest[idx_id].get("value")
                    ui.label(f"最新 ${cf_val:,.2f}" if cf_val is not None else "无快照") \
                        .classes("font-mono text-[var(--kd-accent)]")
                else:
                    ui.label("无快照").classes("kd-mut")
        # 第二行：目标价 + 差值（优先用 Kalshi 结构化 floor_strike）
        strike = quote.get("floor_strike")
        if strike is None:
            strike = self._cf_strike_from_ticker(ticker)
        with card:
            with ui.row().classes("w-full items-center gap-4 text-sm"):
                if strike is not None:
                    cap = quote.get("cap_strike")
                    if cap is not None and float(cap) != float(strike):
                        target = f"${strike:,.0f} – ${cap:,.0f}"
                    elif float(strike).is_integer():
                        target = f"${strike:,.0f}"
                    else:
                        target = f"${strike:,.2f}"
                    ui.label(f"🎯 目标价 {target}").classes("kd-mut")
                    if latest.get(idx_id) and latest[idx_id].get("value") is not None:
                        cur = latest[idx_id]["value"]
                        diff = cur - strike
                        pct = (diff / strike * 100) if strike else 0
                        arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "·")
                        sign = "+" if diff >= 0 else ""
                        color = "var(--kd-accent)" if diff < 0 else "#ef4444"
                        with ui.row().classes("items-center gap-1 font-mono"):
                            ui.label(f"差值 {arrow} {sign}${abs(diff):,.2f} ({sign}{pct:.2f}%)") \
                                .style(f"color:{color}")
                            ui.label("CF vs 目标").classes("text-xs kd-mut")
                else:
                    ui.label("（非目标价型市场）").classes("text-xs kd-mut")
        # 第三行：达成时间指标（按 5 分钟 CF 速率推算）
        if strike is not None:
            cur_val = (latest.get(idx_id) or {}).get("value")
            stype = str(quote.get("strike_type") or "").lower()
            is_below = ("less" in stype) or ("below" in stype)
            metric = self._cf_reach_metric(
                recent, cur_val, float(strike),
                self._ts_epoch(quote.get("close_time")),
                datetime.now().timestamp(), is_below)
            if metric:
                color = ("var(--kd-accent)" if metric["ok"] else "#ef4444") \
                    if metric["ok"] is not None else "var(--kd-mut)"
                with card:
                    with ui.row().classes("w-full items-center gap-2 text-xs"):
                        ui.icon("timer").classes("text-[var(--kd-accent)]")
                        ui.label("达成时间").classes("font-mono kd-mut")
                        ui.label(metric["text"]).classes("font-mono").style(f"color:{color}")
                        if metric["rate_min"] is not None:
                            ui.label(f"速率 {metric['rate_min']:+.2f} USD/分") \
                                .classes("font-mono kd-mut")
        # 第四行：ECharts 曲线
        if len(history) >= 2:
            data = [[int(r["time_ms"]), float(r["value"])] for r in history
                    if r.get("time_ms") and r.get("value") is not None]
            chart_opt = {
                "grid": {"left": 60, "right": 20, "top": 10, "bottom": 28},
                "xAxis": {"type": "time",
                          "min": data[0][0] if data else None,
                          "max": data[-1][0] if data else None,
                          "axisLabel": {"fontSize": 9, "color": "#888"},
                          "axisLine": {"lineStyle": {"color": "#333"}}},
                "yAxis": {"type": "value", "scale": True,
                          "axisLabel": {"fontSize": 9, "color": "#888"},
                          "splitLine": {"lineStyle": {"color": "#222"}}},
                "series": [{
                    "type": "line",
                    "data": data,
                    "smooth": True,
                    "showSymbol": False,
                    "lineStyle": {"color": "#35e0a1", "width": 2},
                    "areaStyle": {"color": {"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                                            "colorStops": [
                                                {"offset": 0, "color": "rgba(53,224,161,0.3)"},
                                                {"offset": 1, "color": "rgba(53,224,161,0.0)"},
                                            ]}},
                }],
            }
            if strike is not None:
                chart_opt["series"].append({
                    "type": "line", "markLine": {
                        "symbol": "none",
                        "data": [{"yAxis": strike, "lineStyle": {"color": "#f59e0b", "type": "dashed"},
                                  "label": {"formatter": f"目标 ${strike:,.2f}",
                                            "color": "#f59e0b", "fontSize": 10}}],
                    },
                })
            with card:
                ui.echart(chart_opt).classes("w-full h-40")
        elif idx_id and not history:
            with card:
                ui.label("CF Benchmarks 转发层暂无数据，等 Kalshi 恢复后自动填充") \
                    .classes("text-xs kd-mut italic")
        await self._render_cf_spread()

    async def _render_cf_spread(self) -> None:
        """更新 CF 与 Invest BTC（KXBTCPERP）的价差图，近 2 小时滚动。

        图表元素在对话框创建时只建一次，这里只原地更新 options，
        避免每次 2 秒刷新重建导致图一闪就消失。
        """
        card = self._el("cf_spread_card")
        if not card:
            return
        idx_id = self.cf_index_id_for_ticker((self._quote or {}).get("ticker", ""))
        mapping = CF_PERPS_MAP.get(idx_id or "")
        if not mapping or not self.api:
            card.visible = False
            return
        card.visible = True
        perps_ticker, mult = mapping
        rng = "2h"
        if rg := self._el("cf_spread_range"):
            rng = rg.value or "2h"
        range_hours = {"30m": 0.5, "1h": 1.0, "2h": 2.0}.get(rng, 2.0)
        range_label = {"30m": "半小时", "1h": "1 小时", "2h": "2 小时"}.get(rng, "2 小时")
        if lbl := self._el("cf_spread_title"):
            lbl.set_text(f"{perps_ticker} − CF 价差（近 {range_label}）")
        # 保证 perps 订阅在跑，这样才能持续拿到 invest BTC 价格
        try:
            sub = self._perps_subscriber()
            await sub.set_tickers({perps_ticker})
            await sub.start()
        except Exception:
            pass
        now_ts = int(datetime.now().timestamp())
        since = now_ts - int(range_hours * 3600)
        perps_limit = max(1500, int(range_hours * 1500))
        cfb_limit = max(1200, int(range_hours * 1200))
        try:
            cf_rows, perps_rows = await asyncio.gather(
                run.io_bound(db.cfb_history, self.api.env, idx_id, range_hours, cfb_limit),
                run.io_bound(db.perps_trades_since, self.api.env,
                             perps_ticker, since, perps_limit),
            )
        except Exception:
            cf_rows, perps_rows = [], []
        cf_rows = cf_rows or []
        perps_rows = perps_rows or []
        cf = [(int(r["time_ms"]), float(r["value"])) for r in cf_rows
              if r.get("time_ms") and r.get("value") is not None]
        cf.sort(key=lambda x: x[0])
        pts = []
        j = 0
        for r in perps_rows:
            if r.get("price") is None or not cf:
                continue
            t = int(r["ts"]) * 1000
            while j + 1 < len(cf) and abs(cf[j + 1][0] - t) <= abs(cf[j][0] - t):
                j += 1
            if abs(cf[j][0] - t) <= 15000:
                diff = float(r["price"]) * mult - cf[j][1]
                pts.append([t, round(diff, 2)])
        latest_diff = pts[-1][1] if pts else None
        if val := self._el("cf_spread_value"):
            if latest_diff is not None:
                color = "#60a5fa" if latest_diff >= 0 else "#f97316"
                val.set_text(f"{latest_diff:+,.2f} USD")
                val.style(f"color:{color}")
            else:
                val.set_text("—")
        chart = self._el("cf_spread_chart")
        hint = self._el("cf_spread_hint")
        if len(pts) < 2:
            if hint:
                hint.set_text("等待 CFB 与 KXBTCPERP 同步数据（perps 已自动订阅）")
                hint.visible = True
            if chart:
                chart.visible = False
            return
        if hint:
            hint.visible = False
        if not chart:
            return
        chart.visible = True
        opt = {
            "animationDurationUpdate": 200,
            "grid": {"left": 62, "right": 20, "top": 8, "bottom": 24},
            "tooltip": {"trigger": "axis"},
            "xAxis": {
                "type": "time", "min": since * 1000, "max": now_ts * 1000,
                "axisLabel": {"fontSize": 9, "color": "#888"},
                "axisLine": {"lineStyle": {"color": "#333"}},
            },
            "yAxis": {
                "type": "value", "scale": True, "name": "价差 $",
                "nameTextStyle": {"fontSize": 9, "color": "#888"},
                "axisLabel": {"fontSize": 9, "color": "#888"},
                "splitLine": {"lineStyle": {"color": "#222"}},
            },
            "series": [{
                "type": "line",
                "data": pts,
                "smooth": True,
                "showSymbol": False,
                "lineStyle": {"color": "#60a5fa", "width": 1.6},
                "areaStyle": {"color": "rgba(96,165,250,0.15)"},
                "markLine": {
                    "symbol": "none",
                    "silent": True,
                    "label": {"show": False},
                    "data": [{"yAxis": 0}],
                    "lineStyle": {"color": "#555", "type": "dashed"},
                },
            }],
        }
        chart.options.clear()
        chart.options.update(opt)
        chart.update()

    async def refresh_cf_quote_panel(self) -> None:
        """下单框内 CF 面板每 2 秒跟随 WS 实时价重绘。"""
        if not (self.api and self._quote and self.trade_dlg.value
                and self._el("cfb_card")):
            return
        snap = self._cfb_subscriber().snapshot()
        if not snap["latest"]:
            return
        changed = False
        for idx, rec in snap["latest"].items():
            val = rec.get("value")
            if val is None:
                continue
            if (self.cfb_latest.get(idx) or {}).get("value") != val:
                changed = True
            ts = rec.get("ts")
            self.cfb_latest[idx] = {
                "value": val,
                "ingested_at": datetime.fromtimestamp(ts) if ts else None,
            }
        if changed:
            await self._render_cfb_panel(self._quote)
        else:
            await self._render_cf_spread()

    def _on_action_change(self, action: str) -> None:
        best = DeskAPI.best_price(self._quote or {}, action)
        if best is not None and 0.01 <= best <= 0.99:
            self.px_input.value = round(best, 2)
        self._update_est()

    def _update_est(self) -> None:
        """手动交易下单金额预估（动量模式无此控件，调用方已分流）。"""
        if not getattr(self, "est_label", None) or not getattr(self, "px_input", None):
            return
        try:
            count = int(self.qty_input.value or 0)
            price = float(self.px_input.value or 0)
            if count > 0 and price > 0:
                verb = "支出" if str(self.act_toggle.value).startswith("buy") else "收入"
                self.est_label.set_text(f"预计{verb} ≈ {usd(count * price)}（未含手续费）")
            else:
                self.est_label.set_text("")
        except (TypeError, ValueError):
            self.est_label.set_text("")

    # ---------- 动量面板（独立入口，方向/价格全自动） ----------
    async def _detect_momentum(self, ticker: str,
                                window_sec: int = 60) -> tuple[str, float]:
        """检测哪条腿在上涨，返回 (direction, delta)，direction ∈ {"yes","no"}。

        Kalshi 二元市场 YES 价 + NO 价 = 1，所以 YES 价上涨 ⇔ NO 价下跌：
          delta > 0 → YES 腿在涨 → buy_yes
          delta < 0 → NO 腿在涨  → buy_no
        用窗口内前 20% / 后 20% 成交价的均值差抗噪（首尾单笔容易被插针带偏）。
        """
        direction, delta = "yes", 0.0
        if not (self.api and ticker):
            return direction, delta

        def _fetch(win: int) -> list:
            try:
                return db.market_trades_range(
                    self.api.env, ticker, int(time.time() - win), None, 2000) or []
            except Exception:
                return []

        # 15 分钟类市场成交稀少：60s 窗口不足 2 笔时自动扩到 300s / 900s
        rows: list = []
        for win in (window_sec, max(window_sec, 300), max(window_sec, 900)):
            rows = await run.io_bound(_fetch, win)
            if len(rows) >= 2:
                break
        if len(rows) < 2:  # 仍不足 → 本轮不触发
            return direction, delta
        pts = [float(r["price"]) for r in rows if r.get("price") is not None]
        if len(pts) < 2:
            return direction, delta
        k = max(1, int(len(pts) * 0.2))
        head = sum(pts[:k]) / k
        tail = sum(pts[-k:]) / k
        delta = tail - head
        return ("yes" if delta >= 0 else "no"), delta

    @staticmethod
    def _momentum_buy_px(quote: dict, direction: str) -> Optional[float]:
        """该腿可成交的卖一价（下单瞬间的最新价）；无盘口时退化为最新成交价。"""
        action = "buy_yes" if direction == "yes" else "buy_no"
        px = DeskAPI.best_price(quote or {}, action)
        if px is None:
            last = quote.get("last")
            if last is not None:
                px = last if direction == "yes" else round(1.0 - last, 4)
        if px is None:
            return None
        try:
            px = float(px)
        except (TypeError, ValueError):
            return None
        return px if 0.01 <= px <= 0.99 else None

    @staticmethod
    def _momentum_tp_px(buy_px: float, mult: float) -> float:
        """止盈价 = 买价 × 倍率，向上取整到 0.01 且至少比买价高 0.01，上限 0.99。"""
        tp = int(buy_px * mult * 100 + 0.9999999) / 100.0
        tp = max(tp, round(buy_px + 0.01, 2))
        return min(0.99, round(tp, 2))

    # CF 指数相对水位线（strike）的有利偏离达到 0.10% 时，止盈倍率打满上限
    _MO_CF_RAMP_PCT = 0.10

    def _mo_market_frac(self, quote: dict) -> Optional[float]:
        """市场生命周期进度 0~1：已过时长 / 总时长（open_time → close_time）。

        15 分钟市场 frac=0.1333 即第 2 分钟、0.9333 即结束前 1 分钟。
        缺 open_time / close_time（如 one_off 市场）时返回 None，不启用该过滤。
        """
        q = quote or {}
        open_ts = self._parse_close_time(q.get("open_time"))
        close_ts = self._parse_close_time(q.get("close_time"))
        if not open_ts or not close_ts or close_ts <= open_ts:
            return None
        return (time.time() - open_ts) / (close_ts - open_ts)

    async def _mo_tp_mult_cf(self, cfg: dict, ticker: str, direction: str,
                              quote: Optional[dict]) -> float:
        """参考 cf_benchmark 与水位线（strike）的有利差值动态放大止盈倍率。

        - 开关关闭 / 非 CF 标的 / 无 strike / 无 CF 快照 → 用基础 tp_mult
        - 有利偏离（方向校正后）越大，倍率越接近上限 tp_cf_max；
          偏离达到 _MO_CF_RAMP_PCT（strike 的 0.10%）即打满
        - 不利或零偏离 → 仍用基础 tp_mult
        """
        base = float(cfg.get("tp_mult") or 1.02)
        if not cfg.get("tp_cf_boost"):
            return base
        idx_id = self.cf_index_id_for_ticker(ticker)
        if not idx_id:
            return base
        strike = (quote or {}).get("floor_strike")
        if strike is None:
            strike = self._cf_strike_from_ticker(ticker)
        try:
            strike = float(strike)
        except (TypeError, ValueError):
            return base
        if strike <= 0:
            return base
        cf = ((getattr(self, "cfb_latest", None) or {}).get(idx_id) or {}).get("value")
        if cf is None:
            try:
                env = self.api.env if self.api else "demo"
                latest = await run.io_bound(db.cfb_latest, env, [idx_id])
                cf = ((latest or {}).get(idx_id) or {}).get("value")
            except Exception:
                cf = None
        try:
            cf = float(cf)
        except (TypeError, ValueError):
            return base
        # 方向校正：先算出「YES 腿有利」的距离，再按本次买的是 YES 还是 NO 取符号
        stype = str((quote or {}).get("strike_type") or "").lower()
        yes_favorable = (strike - cf) if ("less" in stype or "below" in stype) \
            else (cf - strike)
        favorable = yes_favorable if direction == "yes" else -yes_favorable
        pct = favorable / strike * 100.0
        if pct <= 0:
            return base
        cap = max(base, float(cfg.get("tp_cf_max") or base))
        ratio = min(1.0, pct / self._MO_CF_RAMP_PCT)
        return base + (cap - base) * ratio

    def _render_momentum_panel(self) -> None:
        """用已有自检结果重绘动量面板（供输入变化时即时刷新）。"""
        self._paint_momentum(self._mo_dir, self._mo_delta, self._quote)

    def _paint_momentum(self, direction: str, delta: float, quote: Optional[dict]) -> None:
        label = self._el("mo_dir_label")
        if not label:
            return
        arrow = "↑" if delta >= 0 else "↓"
        leg_name = "YES" if direction == "yes" else "NO"
        strength = ("强" if abs(delta) >= 0.03 else
                    "中" if abs(delta) >= 0.01 else "弱")
        label.set_text(f"{leg_name} {arrow} 上涨")
        if el := self._el("mo_trend_label"):
            el.set_text(f"近 60s Δ{delta:+.3f}（动量{strength}）")
        buy_px = self._momentum_buy_px(quote or {}, direction)
        mult_el = self._el("mo_mult_input")
        try:
            mult = float(mult_el.value if mult_el else 1.1) or 1.1
        except (TypeError, ValueError):
            mult = 1.1
        if buy_px is None:
            if el := self._el("mo_px_label"):
                el.set_text("买价 —（无盘口）")
            if el := self._el("mo_tp_label"):
                el.set_text("止盈 —")
            return
        tp = self._momentum_tp_px(buy_px, mult)
        if el := self._el("mo_px_label"):
            el.set_text(f"买价 {buy_px:.2f}")
        if el := self._el("mo_tp_label"):
            el.set_text(f"止盈 {tp:.2f}（{mult:.2f}×）")

    async def _refresh_momentum_panel(self) -> None:
        """每 2 秒重算动量方向与买/止盈价。

        盘口由 refresh_trade_chart 同一节奏拉取并写入 self._quote，
        这里不再重复请求 API，避免两条 2s 定时器撞在一起触发 429 限流。
        """
        if not (self.api and self._el("mo_dir_label") and self.trade_dlg.value):
            return
        ticker = self._trade_chart_ticker
        if not ticker:
            self._mo_dir, self._mo_delta = "yes", 0.0
            self._paint_momentum("yes", 0.0, None)
            return
        direction, delta = await self._detect_momentum(ticker)
        self._mo_dir, self._mo_delta = direction, delta
        self._paint_momentum(direction, delta, self._quote)

    async def reload_quote(self) -> None:
        ticker = (self.tk_select.value or "").strip()
        if not ticker:
            self.notify("请先选择市场与 ticker", type="warning")
            return
        try:
            quote = await run.io_bound(self.api.quote, ticker)
        except Exception as ex:
            self.notify(f"行情获取失败：{ex}", type="negative")
            return
        self._set_quote(quote)
        if getattr(self, "_trade_momentum", False):
            direction, delta = await self._detect_momentum(ticker)
            self._mo_dir, self._mo_delta = direction, delta
            self._paint_momentum(direction, delta, quote)
        else:
            self._on_action_change(self.act_toggle.value)

    async def submit_trade(self) -> None:
        # === 动量模式分流（独立入口，方向与价格全自动） ===
        if getattr(self, "_trade_momentum", False):
            await self._submit_momentum_trade()
            return
        ticker = (self.tk_select.value or "").strip()
        action = self.act_toggle.value
        price = _num(self.px_input.value)
        count = _num(self.qty_input.value)
        if not ticker:
            ui.notify("请先选择市场与 ticker", type="warning")
            return
        if price is None or not (0.01 <= price <= 0.99):
            ui.notify("价格需在 0.01 ~ 0.99 之间", type="warning")
            return
        if not count or count < 1:
            ui.notify("数量至少 1 张", type="warning")
            return
        count = int(count)
        if self.post_only.value and self.tif_toggle.value != "good_till_canceled":
            ui.notify("post-only 订单必须使用 GTC", type="warning")
            return
        if action.startswith("sell"):
            p = self.pos_by_ticker.get(ticker)
            held = 0
            if p:
                held = int(p["yes_qty"] if action == "sell_yes" else p["no_qty"])
            if count > held:
                ui.notify(f"可卖数量不足：当前持仓 {held} 张", type="warning")
                return
        # 下单前再确认一次市场仍可交易（防止行情延迟或对话框打开期间市场已关闭）
        try:
            live = await run.io_bound(self.api.quote, ticker)
        except Exception as ex:
            ui.notify(f"无法确认市场状态：{ex}", type="negative")
            return
        status = (live or {}).get("status")
        if status and status != "active":
            ui.notify(f"市场当前状态 {status}，不可下单", type="negative")
            self._set_quote(live)
            return
        self._quote = live or self._quote
        side, yes_px = DeskAPI.to_book(action, price)
        summary = (f"{ACTION_LABEL[action]}　{ticker}\n"
                   f"价格 {price:.2f}　数量 {count} 张　"
                   f"金额 ≈ {usd(count * price)}\n"
                   f"TIF {self.tif_toggle.value}　子账户 {int(self.sub_input.value or 0)}")
        if not await self.confirm(summary):
            return
        tif = self.tif_toggle.value
        post_only = bool(self.post_only.value) and tif == "good_till_canceled"
        sub = int(self.sub_input.value or 0)
        try:
            r = await run.io_bound(
                lambda: self.api.place(ticker, side, yes_px, count, tif, post_only, sub))
            filled = _num(r.get("fill_count_fp") or r.get("fill_count")) or 0.0
            status = r.get("status") or ("resting" if tif == "good_till_canceled" else "—")
            ui.notify(f"已提交：成交 {filled:g}/{count} 张，状态 {status}", type="positive")
            self.trade_dlg.close()
            await self._after_trade()
        except Exception as ex:
            msg = str(ex)
            if "insufficient_shard_balance" in msg:
                idx = (getattr(self, "_quote", None) or {}).get("exchange_index")
                where = f"（分片 {idx}）" if idx is not None else ""
                msg = (f"该市场所在交易分片{where}可用余额不足，无法挂单。\n"
                       "请到「交易 → 子账户」页把资金转到该分片，或先减少持仓释放资金。")
            elif "market_inactive" in msg:
                msg = "市场当前不可交易（可能已关闭或结算）"
            ui.notify(f"下单失败：{msg}", type="negative")

    async def _after_trade(self) -> None:
        """下单/撤单后的刷新：订单表立即刷新（单个请求，秒回），
        余额/持仓等其余数据放到后台补，避免用户干等全量同步。"""
        await self.refresh_orders()
        asyncio.create_task(self.refresh_all(manual=True))

    # ---------- 动量下单 ----------
    # 参考 frac_spike_grid.py 网格单止盈状态机：
    #   bidding → tp_resting → done
    #   买入挂单 → 成交后立即挂止盈卖单（GTC），卖单成交即完成整个动量循环
    # 关键约束（吃了大亏才记住）：
    #   Kalshi 二元市场 V2 单 book：side=bid 买 YES，side=ask 卖 YES(=买 NO)
    #   所以用户点「买 NO」实际发起的是 side=ask yes_price=1-no_price 的卖 YES 单，
    #   买单成交后持仓方向是 NO 腿，止盈卖单必须是 sell_no ≡ side=bid yes_price=1-sell_price。
    #   DeskAPI.to_book() 已经封装了这个映射，买卖两边都走它就不会搞反。

    async def _submit_momentum_trade(self) -> None:
        """动量下单：方向、买入价、止盈价全部自动，仅数量/倍率/子账户可设。

        流程：
          1. 下单瞬间重新检测上涨腿（不信任面板上的旧快照）
          2. 下单瞬间拉最新盘口，买入价取该腿卖一价（确保能吃单）
          3. 止盈价 = 买入价 × 倍率（向上取整到 0.01）
          4. 挂买单 → IOC 全成交立即挂止盈卖单 / 否则起协程轮询
        """
        ticker = ((self.tk_select.value if self.tk_select else "") or "").strip()
        if not ticker:
            self.notify("请先选择市场与 ticker", type="warning")
            return
        count = _num(self.qty_input.value)
        if not count or count < 1:
            self.notify("数量至少 1 张", type="warning")
            return
        count = int(count)
        try:
            mult = float(self.mo_mult_input.value or 1.1)
        except (TypeError, ValueError):
            mult = 1.1
        if not (1.01 <= mult <= 3.0):
            self.notify("止盈倍率需在 1.01 ~ 3.00 之间", type="warning")
            return
        buy_tif = self.tif_toggle.value or "immediate_or_cancel"
        sub = int(self.sub_input.value or 0)
        # === 1) 下单瞬间重新检测动量方向 ===
        direction, delta = await self._detect_momentum(ticker)
        action = "buy_yes" if direction == "yes" else "buy_no"
        # === 2) 下单瞬间拉最新盘口 → 最新可成交买价 ===
        try:
            live = await run.io_bound(self.api.quote, ticker)
        except Exception as ex:
            self.notify(f"无法获取最新盘口：{ex}", type="negative")
            return
        status = (live or {}).get("status")
        if status and status != "active":
            self.notify(f"市场当前状态 {status}，不可下单", type="negative")
            return
        self._quote = live or self._quote
        buy_price = self._momentum_buy_px(live or {}, direction)
        if buy_price is None:
            self.notify("当前盘口没有可成交的卖价，请稍后再试", type="warning")
            return
        if buy_price >= 0.99:
            self.notify(f"该腿卖一价已到 0.99（{buy_price:.2f}），无上涨空间，放弃",
                        type="warning")
            return
        # === 3) 止盈价 = 买价 × 倍率 ===
        sell_price = self._momentum_tp_px(buy_price, mult)
        if sell_price <= buy_price:
            self.notify("止盈价未高于买入价，请调高倍率", type="warning")
            return
        # 方向 → book side 映射（buy_no 会转成 side=ask + YES价=1-no价）
        buy_side, buy_yes_px = DeskAPI.to_book(action, buy_price)
        sell_action = action.replace("buy_", "sell_")
        sell_side, sell_yes_px = DeskAPI.to_book(sell_action, sell_price)
        pnl = count * (sell_price - buy_price)
        leg_name = "YES" if direction == "yes" else "NO"
        summary = (
            f"【动量买入】{ACTION_LABEL[action]}（{leg_name} 腿上涨 Δ{delta:+.3f}）\n"
            f"ticker　{ticker}\n"
            f"买入价 {buy_price:.2f}（最新卖一）　止盈价 {sell_price:.2f}"
            f"（{mult:.2f}×）　数量 {count} 张\n"
            f"买单 TIF {buy_tif}　子账户 {sub}　"
            f"预期毛盈亏 {usd(pnl, signed=True)}"
        )
        if not await self.confirm(summary):
            return
        # === 4) 挂买入单 ===
        try:
            buy_resp = await run.io_bound(
                lambda: self.api.place(ticker, buy_side, buy_yes_px, count,
                                        buy_tif, post_only=False, subaccount=sub))
        except Exception as ex:
            self._handle_place_error(ex)
            return
        buy_order_id = buy_resp.get("order_id") or ""
        if not buy_order_id:
            self.notify(f"买单响应异常：{buy_resp}", type="negative")
            return
        buy_filled = _num(buy_resp.get("fill_count_fp") or buy_resp.get("fill_count")) or 0.0
        buy_status = buy_resp.get("status") or "resting"
        if buy_status in ("executed", "filled") and buy_filled >= count:
            # IOC 立即全成交 → 直接挂止盈卖单，不等后台轮询
            self.notify(f"动量买入全成交（{buy_filled:g}/{count}），立即挂止盈卖单 "
                        f"{sell_price:.2f}", type="positive")
            await self._place_momentum_sell(buy_order_id, ticker, sell_side,
                                             sell_yes_px, count, sub)
            self.trade_dlg.close()
            await self._after_trade()
            return
        # 未全成交 → 后台轮询，成交后自动挂止盈
        self.notify(
            f"动量买单已挂：{ACTION_LABEL[action]} {buy_price:.2f} × {count}"
            f"（成交 {buy_filled:g}/{count}，{buy_status}）\n"
            f"成交后将自动挂止盈卖单 {sell_price:.2f}",
            type="positive")
        await self._spawn_momentum_watcher(
            buy_order_id, ticker, sell_side, sell_yes_px, count, sub,
            action, buy_price, sell_price,
            series=ticker.split("-")[0] if "-" in ticker else "")
        self.trade_dlg.close()
        await self._after_trade()

    async def _place_momentum_sell(self, buy_order_id: str, ticker: str,
                                    sell_side: str, sell_yes_px: float,
                                    count: int, subaccount: int,
                                    ctx: Optional[dict] = None) -> Optional[str]:
        """买单已确认成交后挂止盈卖单（GTC，post_only=True 优先 maker 成交）。

        post_only 被拒（价格已穿过卖一）时退回 post_only=False 以 taker 重挂，
        避免动量行情下止盈单挂不上、仓位裸奔。
        返回 sell_order_id（成功）或 None（失败）；传入 ctx 会把 sell_order_id 回填进去。
        """
        sell_resp = None
        last_ex: Optional[Exception] = None
        for post_only in (True, False):
            try:
                sell_resp = await run.io_bound(
                    lambda po=post_only: self.api.place(
                        ticker, sell_side, sell_yes_px, count,
                        tif="good_till_canceled", post_only=po,
                        subaccount=subaccount))
                break
            except Exception as ex:
                last_ex = ex
        if not isinstance(sell_resp, dict):
            self.notify(f"止盈卖单挂单失败：{last_ex}\n（买单已成交，可能需要手动止盈）",
                        type="negative")
            return None
        sell_status = sell_resp.get("status") or "resting"
        sell_filled = _num(sell_resp.get("fill_count_fp") or sell_resp.get("fill_count")) or 0.0
        sell_order_id = sell_resp.get("order_id") or ""
        self.notify(
            f"止盈卖单已挂：side={sell_side} YES价={sell_yes_px:.4f} × {count}\n"
            f"卖单 {sell_order_id}（成交 {sell_filled:g}/{count}，状态 {sell_status}）",
            type="positive")
        if ctx is not None:
            ctx["sell_order_id"] = sell_order_id
            ctx["sell_status"] = sell_status
        return sell_order_id or None

    async def _spawn_momentum_watcher(self, buy_order_id: str, ticker: str,
                                       sell_side: str, sell_yes_px: float,
                                       count: int, subaccount: int,
                                       action: str, buy_price: float,
                                       sell_price: float,
                                       _mo_writeback: bool = False,
                                       series: str = "",
                                       mo_cfg: Optional[dict] = None) -> None:
        """后台协程：轮询买单状态，全成交后挂止盈卖单。

        状态机（对齐 frac_spike_grid.py 的 GridLayerState）：
          idle → bidding（买单已挂） → tp_resting（止盈卖单已挂） → done（卖单成交 or 超时）
        _mo_writeback=True 表示这是自动引擎发的单，需要额外回写 DuckDB 动量日志。
        mo_cfg 传入机器人配置时才启用「超时未成交自动撤单」（手动动量单不撤）。
        """
        ctx = {
            "buy_order_id": buy_order_id,
            "ticker": ticker,
            "series": series,
            "sell_side": sell_side,
            "sell_yes_px": sell_yes_px,
            "count": count,
            "subaccount": subaccount,
            "action": action,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "state": "bidding",        # bidding / tp_resting / done
            "sell_order_id": "",
            "_mo_writeback": _mo_writeback,
            "_mo_cfg": mo_cfg,
            "buy_tif": (mo_cfg or {}).get("buy_tif", "immediate_or_cancel"),
            "direction": "yes" if action == "buy_yes" else "no",
        }
        self._momentum_watchers[buy_order_id] = ctx
        asyncio.create_task(self._run_momentum_fill_watcher(ctx))

    def _mo_writeback_on(self, ctx: dict) -> bool:
        """该 ctx 是否属于机器人单（需要回写 DuckDB）。"""
        return bool(ctx.get("_mo_writeback")) and self.api is not None

    async def _mo_order_state(self, order_id: str) -> tuple:
        """取订单 (status, 已成交张数)；失败返回 ("", 0)。"""
        try:
            o = await run.io_bound(self.api.get_order, order_id)
        except Exception as ex:
            print(f"[momentum] get_order 失败（忽略重试）：{ex}")
            return "", 0.0
        if not isinstance(o, dict):
            return "", 0.0
        status = (o.get("status") or "").lower()
        filled = _num(o.get("fill_count_fp") or o.get("fill_count")) or 0.0
        return status, filled

    async def _mo_cancel_order(self, order_id: str, ticker: str,
                                label: str) -> bool:
        """撤单；已成/已撤视作成功。"""
        try:
            await run.io_bound(self.api.cancel, order_id, ticker)
            return True
        except Exception as ex:
            msg = str(ex).lower()
            if any(k in msg for k in ("not_found", "not found", "already",
                                      "canceled", "cancelled", "filled")):
                return True
            print(f"[momentum] 撤{label} {order_id[:12]}… 失败：{ex}")
            return False

    async def _mo_on_buy_filled(self, ctx: dict, mo, status: str,
                                 buy_filled: float, tp_count: int) -> None:
        """买单（全部或部分）成交 → 挂止盈并等止盈终态。"""
        ticker = ctx["ticker"]
        ctx["state"] = "tp_resting"
        mo("buy_filled", buy_status=status, buy_count=int(buy_filled))
        if self._mo_writeback_on(ctx):
            env = self.api.env
            db.mo_log(env, "BUY_FILLED",
                      f"{ticker} 买单成交 {buy_filled:g}/{ctx['count']}，挂止盈 "
                      f"{ctx['sell_price']:.2f}",
                      ticker=ticker,
                      detail={"buy_order_id": ctx["buy_order_id"]})
        sell_id = await self._place_momentum_sell(
            ctx["buy_order_id"], ticker, ctx["sell_side"], ctx["sell_yes_px"],
            int(tp_count), ctx["subaccount"], ctx=ctx)
        if sell_id is not None:
            mo("tp_placed", sell_order_id=sell_id)
            await self._run_tp_watch(ctx, sell_id, buy_filled, int(tp_count), mo)
        elif self._mo_writeback_on(ctx):
            # 止盈挂不上（post_only 两次都失败/盘口消失）：绝不把仓位裸着，
            # 立即市价平掉并落终态，否则这行会永远卡在 buy_filled 锁死 ticker。
            flat_filled, flat_px, remaining = await self._mo_flatten_until_done(
                ctx, int(tp_count))
            pnl = (flat_px - ctx["buy_price"]) * flat_filled
            if remaining > 0:
                ctx["state"] = "error"
                ctx["error_ts"] = time.time()
                mo("error", sell_status="tp_failed_flatten_incomplete",
                   pnl=round(pnl, 4))
                db.mo_log(self.api.env, "FLATTEN_INCOMPLETE",
                          f"{ticker} 止盈挂单失败且平仓未完成，"
                          f"仍剩 {remaining} 张未平！", ticker=ticker,
                          detail={"buy_order_id": ctx["buy_order_id"],
                                  "remaining": remaining})
                self.notify(f"{ticker} 仍有 {remaining} 张未平掉，"
                            f"请立即手动处理", type="negative")
            else:
                mo("canceled", sell_status="tp_place_failed_flatten",
                   pnl=round(pnl, 4))
                db.mo_log(self.api.env, "TP_FAILED_FLATTEN",
                          f"{ticker} 止盈挂单失败，已市价平仓 {flat_filled:g} 张 "
                          f"@{flat_px:.2f}，pnl={pnl:+.4f}", ticker=ticker,
                          detail={"buy_order_id": ctx["buy_order_id"]})
        if ctx.get("state") != "error":   # 平仓未完成会置 error，不能覆盖
            ctx["state"] = "done"

    async def _mo_on_buy_dead(self, ctx: dict, mo, status: str,
                               filled: float, count: int) -> None:
        """买单进入终态。有成交则对已成交部分挂止盈，无成交则本局结束。"""
        ticker = ctx["ticker"]
        ctx["state"] = "done"
        if filled > 0:
            pc = int(filled) if filled == int(filled) else filled
            self.notify(
                f"动量买单 {ctx['buy_order_id'][:12]}… {status}（成交 {filled:g}/{count}），"
                f"对已成交 {pc:g} 张自动挂止盈卖单", type="warning")
            mo("buy_filled", buy_status=status, buy_count=int(pc))
            sell_id = await self._place_momentum_sell(
                ctx["buy_order_id"], ticker, ctx["sell_side"], ctx["sell_yes_px"],
                int(pc), ctx["subaccount"], ctx=ctx)
            if sell_id is not None:
                mo("tp_placed", sell_order_id=sell_id)
                await self._run_tp_watch(ctx, sell_id, filled, int(pc), mo)
            elif self._mo_writeback_on(ctx):
                flat_filled, flat_px, remaining = await self._mo_flatten_until_done(
                    ctx, int(pc))
                pnl = (flat_px - ctx["buy_price"]) * flat_filled
                if remaining > 0:
                    ctx["state"] = "error"
                    ctx["error_ts"] = time.time()
                    mo("error", sell_status="tp_failed_flatten_incomplete",
                       pnl=round(pnl, 4))
                    db.mo_log(self.api.env, "FLATTEN_INCOMPLETE",
                              f"{ticker} 止盈挂单失败且平仓未完成，"
                              f"仍剩 {remaining} 张未平！", ticker=ticker,
                              detail={"buy_order_id": ctx["buy_order_id"],
                                      "remaining": remaining})
                    self.notify(f"{ticker} 仍有 {remaining} 张未平掉，"
                                f"请立即手动处理", type="negative")
                else:
                    mo("canceled", sell_status="tp_place_failed_flatten",
                       pnl=round(pnl, 4))
                    db.mo_log(self.api.env, "TP_FAILED_FLATTEN",
                              f"{ticker} 止盈挂单失败，已市价平仓 {flat_filled:g} 张 "
                              f"@{flat_px:.2f}，pnl={pnl:+.4f}", ticker=ticker,
                              detail={"buy_order_id": ctx["buy_order_id"]})
            return
        self.notify(
            f"动量买单 {ctx['buy_order_id'][:12]}… {status}（成交 0/{count}），"
            f"无需自动止盈", type="warning")
        mo("canceled", buy_status=status)
        if self._mo_writeback_on(ctx):
            db.mo_log(self.api.env, "CANCELED",
                      f"{ticker} 买单 {status}（成交 0/{count}）",
                      ticker=ticker,
                      detail={"buy_order_id": ctx["buy_order_id"]})

    async def _mo_requote_buy(self, ctx: dict) -> bool:
        """买单撤单后按最新价追价重挂。动量消失/反向则返回 False。"""
        ticker = ctx["ticker"]
        env = self.api.env if self.api else "demo"
        direction = ctx.get("direction") or "yes"
        try:
            new_dir, delta = await self._detect_momentum(ticker)
        except Exception:
            return False
        if new_dir != direction or abs(delta) < 0.01:
            return False
        try:
            live = await run.io_bound(self.api.quote, ticker)
        except Exception as ex:
            print(f"[momentum] 重挂前拉 quote 失败：{ex}")
            return False
        mkt_status = (live or {}).get("status")
        if mkt_status and mkt_status != "active":
            return False
        buy_px = self._momentum_buy_px(live or {}, direction)
        if buy_px is None:
            return False
        tp_mult = await self._mo_tp_mult_cf(
            ctx.get("_mo_cfg") or {}, ticker, direction, live)
        sell_px = self._momentum_tp_px(buy_px, tp_mult)
        if sell_px <= buy_px:
            return False
        action = ctx["action"]
        buy_side, buy_yes_px = DeskAPI.to_book(action, buy_px)
        sell_action = action.replace("buy_", "sell_")
        sell_side, sell_yes_px = DeskAPI.to_book(sell_action, sell_px)
        try:
            resp = await run.io_bound(lambda: self.api.place(
                ticker, buy_side, buy_yes_px, int(ctx["count"]), ctx["buy_tif"],
                post_only=False, subaccount=ctx["subaccount"]))
        except Exception as ex:
            if self._mo_writeback_on(ctx):
                db.mo_log(env, "ERROR", f"{ticker} 撤单后重挂买单失败：{ex}",
                          ticker=ticker)
            return False
        new_id = (resp or {}).get("order_id") or ""
        if not new_id:
            return False
        old_id = ctx["buy_order_id"]
        if self._momentum_watchers.get(old_id) is ctx:
            self._momentum_watchers.pop(old_id, None)
        ctx["buy_order_id"] = new_id
        ctx["buy_price"] = buy_px
        ctx["sell_price"] = sell_px
        ctx["sell_side"] = sell_side
        ctx["sell_yes_px"] = sell_yes_px
        self._momentum_watchers[new_id] = ctx
        if self._mo_writeback_on(ctx):
            db.mo_upsert_trade(
                env, new_id, ticker=ticker, series=ctx.get("series", ""),
                direction=direction, delta=delta, buy_px=buy_px,
                buy_count=int(ctx["count"]), buy_tif=ctx["buy_tif"],
                buy_status=(resp or {}).get("status") or "resting",
                sell_px=sell_px, subaccount=int(ctx["subaccount"]),
                state="buy_placed")
            db.mo_log(env, "REQUOTE",
                      f"{ticker} 买单超时未成交，撤单后按 {buy_px:.2f} 重挂",
                      ticker=ticker,
                      detail={"old_order_id": old_id, "new_order_id": new_id})
        self.notify(f"动量买单超时未成交，已撤单并按最新价 {buy_px:.2f} 重挂",
                    type="info")
        return True

    async def _mo_flatten(self, ctx: dict, remaining: int,
                          level: int = 0) -> tuple:
        """撤掉止盈单后立即吃单平掉剩余持仓，返回 (已平张数, 成交价)。

        level 逐级加价保证能平掉：
          0 = 对手价（吃一档）
          1 = 对手价 -0.02
          2 = 对手价 -0.05
          3 = 直接挂 0.01，等同市价扫单
        """
        ticker = ctx["ticker"]
        env = self.api.env if self.api else "demo"
        sell_action = ctx["action"].replace("buy_", "sell_")
        px = None
        try:
            q = await run.io_bound(self.api.quote, ticker)
            px = DeskAPI.best_price(q or {}, sell_action)
        except Exception as ex:
            print(f"[momentum] 平仓前拉 quote 失败：{ex}")
        try:
            px = float(px) if px is not None else 0.01
        except (TypeError, ValueError):
            px = 0.01
        if level >= 3:
            px = 0.01            # 扫到最低价，保证吃单成交（等同市价）
        elif level == 2:
            px -= 0.05
        elif level == 1:
            px -= 0.02
        px = max(0.01, min(0.99, px))
        sell_side, sell_yes_px = DeskAPI.to_book(sell_action, px)
        try:
            resp = await run.io_bound(lambda: self.api.place(
                ticker, sell_side, sell_yes_px, int(remaining),
                "immediate_or_cancel", post_only=False,
                subaccount=ctx["subaccount"]))
        except Exception as ex:
            if self._mo_writeback_on(ctx):
                db.mo_log(env, "ERROR", f"{ticker} 撤止盈后市价平仓失败：{ex}",
                          ticker=ticker)
            self.notify(f"{ticker} 撤止盈后市价平仓失败：{ex}", type="negative")
            return 0.0, px
        oid = (resp or {}).get("order_id") or ""
        filled = _num((resp or {}).get("fill_count_fp")
                      or (resp or {}).get("fill_count")) or 0.0
        status = (resp or {}).get("status") or ""
        reason = ((resp or {}).get("rejection_reason")
                  or (resp or {}).get("message") or "")
        # IOC 单在下单响应里就已定局，不做 3 秒轮询；
        # 只有异常返回 resting（未定局）时才补查一次，避免无谓等待
        if filled < remaining and oid and status == "resting":
            await asyncio.sleep(0.2)
            _, filled2 = await self._mo_order_state(oid)
            filled = max(filled, filled2)
        if self._mo_writeback_on(ctx):
            db.mo_log(env, "FLATTEN",
                      f"{ticker} 平仓单 {sell_action} side={sell_side} "
                      f"YES价={sell_yes_px:.2f} ×{int(remaining)} → "
                      f"status={status or '?'} 成交 {filled:g}"
                      + (f"（{reason}）" if reason else ""),
                      ticker=ticker,
                      detail={"order_id": oid, "level": level,
                              "placed_px": px, "filled": filled,
                              "status": status, "reason": reason})
        return filled, px

    async def _mo_position_of(self, ticker: str) -> Optional[float]:
        """查交易所该 ticker 的真实净持仓（正=YES 张数，负=NO 张数）。

        这是判断「到底平没平掉」的唯一可信来源；查询失败返回 None。
        """
        try:
            rows = await run.io_bound(self.api.positions)
        except Exception as ex:
            print(f"[momentum] 查持仓失败：{ex}")
            return None
        for p in rows or []:
            if p.get("ticker") == ticker:
                return float(p.get("position") or 0.0)
        return 0.0

    async def _mo_flatten_until_done(self, ctx: dict, qty: int,
                                      deadline: float = 0) -> tuple:
        """反复市价平仓，直到交易所真实持仓归零或重试用尽。

        返回 (已平张数, 最后一次成交价, 剩余张数)。交易所持仓是唯一可信来源：
        每次下单前先查持仓，已是 0 就绝不再卖，避免成交回报解析异常时反向开仓。
        """
        ticker = ctx["ticker"]
        qty = int(qty)
        remaining = qty
        flat_filled = 0.0
        flat_px = float(ctx.get("sell_price") or 0.01)
        attempts = 0
        limit_ts = deadline or (time.time() + 20 * 60)
        while remaining > 0 and attempts < 4 and time.time() < limit_ts:
            attempts += 1
            # 第一次必须真发单：持仓接口有延迟、demo 环境甚至不返回持仓，
            # 拿它做拦截会导致「撤了单却一单没吃」。第 2 次起才用它防止多卖。
            if attempts > 1:
                pos = await self._mo_position_of(ticker)
                if pos is not None:
                    if abs(pos) < 0.5:
                        remaining = 0
                        break
                    remaining = int(abs(pos))
            # 逐级加价，最后一次直接按 0.01 扫单，保证一定吃掉
            f, px = await self._mo_flatten(
                ctx, remaining, level=min(attempts - 1, 3))
            flat_px = px
            if f > 0:
                flat_filled += f
                remaining = max(0, remaining - int(f))
            if remaining <= 0:
                break
            try:
                m2 = await run.io_bound(self.api.quote, ticker)
                st = ((m2 or {}).get("status") or "").lower()
            except Exception:
                st = ""
            if st in ("closed", "settled", "inactive"):
                break
            await asyncio.sleep(0.8)
        pos_final = await self._mo_position_of(ticker)
        if pos_final is not None and abs(pos_final) >= 0.5:
            # 交易所仍有持仓 → 以持仓为准（可能成交回报没解析出来）。
            # 注意：反过来不能用「持仓为 0」判定成功，持仓接口有延迟。
            remaining = int(abs(pos_final))
            flat_filled = max(0.0, float(qty - remaining))
        return flat_filled, flat_px, remaining

    async def _mo_tp_requote_px(self, ctx: dict) -> Optional[float]:
        """止盈单撤单后的重挂价：跟到卖腿当前卖一（join ask）。

        原来的目标价是开仓瞬间算的，价格回落之后一直挂着不成交；
        重挂时贴到当前卖一才有机会成交。拿不到盘口就沿用原目标价。
        """
        ticker = ctx["ticker"]
        sell_action = ctx["action"].replace("buy_", "sell_")
        try:
            q = await run.io_bound(self.api.quote, ticker)
        except Exception as ex:
            print(f"[momentum] 重挂止盈前拉 quote 失败：{ex}")
            return None
        q = q or {}
        key = "yes_ask" if sell_action == "sell_yes" else "no_ask"
        px = _num(q.get(key))
        if px is None:
            px = _num(ctx.get("sell_price"))
        if px is None:
            return None
        return max(0.01, min(0.99, float(px)))

    async def _run_momentum_fill_watcher(self, ctx: dict) -> None:
        """完整一局的状态机：买单挂单 → 买单成交 → 挂止盈卖单 → 止盈卖单终态 → 退出。

        关键约束（用户确认的铁律）：
          只有止盈卖单进入终态（成交/取消/过期/结算消失），这一局才算关闭，
          引擎才允许在同 ticker 开下一局。watcher 在此之前不 pop。
        撤单逻辑（仅机器人单，传了 mo_cfg 才启用）：
          买单超过 cancel_sec 未成交 → 撤单，动量仍在则按最新价追价重挂（最多 3 次）；
          止盈单超过 cancel_sec 未成交 → 撤单并立即以对手价市价平仓。
        """
        ticker = ctx["ticker"]
        count = ctx["count"]
        env = self.api.env if self.api else "demo"
        mo_writeback = ctx.get("_mo_writeback", False)
        mo_cfg = ctx.get("_mo_cfg") or {}
        try:
            cancel_sec = float(mo_cfg.get("cancel_sec") or 0) if mo_cfg else 0.0
        except (TypeError, ValueError):
            cancel_sec = 0.0
        buy_deadline = time.time() + 30 * 60  # 兜底：买单 30 分钟不成交就放弃
        poll_interval = 2.0
        max_requote = 3
        requotes = 0
        placed_at = time.time()

        def mo(state: str, **extra) -> None:
            """mo_writeback 开启时才回写 DuckDB（手动动量入口不回写）。"""
            if not mo_writeback or not self.api:
                return
            db.mo_upsert_trade(env, ctx["buy_order_id"],
                               **{"state": state, **extra})

        try:
            # ================= 阶段 1：等买单成交 =================
            while time.time() < buy_deadline:
                await asyncio.sleep(poll_interval)
                if ctx.get("state") != "bidding":
                    break
                oid = ctx["buy_order_id"]
                status, filled = await self._mo_order_state(oid)
                if not status:
                    continue
                print(f"[momentum] 买单 {oid[:12]}… status={status} "
                      f"filled={filled:g}/{count}")
                # === 买单全成交 → 挂止盈卖单，进入阶段 2 ===
                if status in ("executed", "filled") or filled >= count:
                    await self._mo_on_buy_filled(ctx, mo, status, filled, count)
                    break
                # === 买单终态（取消/过期/拒绝/部分成交后终止）===
                if status in ("canceled", "expired", "rejected") \
                        or (status not in ("resting", "created", "open")
                            and filled < count):
                    await self._mo_on_buy_dead(ctx, mo, status, filled, count)
                    break
                # === 仍在盘口：超过 cancel_sec 未成交 → 撤单 ===
                if cancel_sec > 0 and (time.time() - placed_at) >= cancel_sec:
                    self.notify(
                        f"动量买单 {oid[:12]}… {cancel_sec:.0f}s 未成交，撤单",
                        type="info")
                    await self._mo_cancel_order(oid, ticker, "买单")
                    status2, filled2 = await self._mo_order_state(oid)
                    if filled2 >= count:
                        await self._mo_on_buy_filled(
                            ctx, mo, status2 or "filled", filled2, count)
                        break
                    if filled2 > 0:
                        await self._mo_on_buy_dead(
                            ctx, mo, status2 or "canceled", filled2, count)
                        break
                    # 0 成交：旧单落库置 canceled，避免残留 buy_placed 记录
                    mo("canceled", buy_status="timeout_canceled")
                    # 0 成交 → 动量仍在就按最新价追价重挂
                    if requotes >= max_requote:
                        ctx["state"] = "done"
                        mo("canceled", buy_status="requote_exhausted")
                        if mo_writeback and self.api:
                            db.mo_log(env, "CANCELED",
                                      f"{ticker} 买单追价 {max_requote} 次仍未成交，"
                                      f"本轮放弃", ticker=ticker,
                                      detail={"buy_order_id": oid})
                        self.notify(
                            f"动量买单 {ticker} 追价 {max_requote} 次仍未成交，本轮放弃",
                            type="warning")
                        break
                    if not await self._mo_requote_buy(ctx):
                        ctx["state"] = "done"
                        mo("canceled", buy_status="momentum_gone")
                        if mo_writeback and self.api:
                            db.mo_log(env, "CANCELED",
                                      f"{ticker} 买单撤单后动量消失，放弃本轮",
                                      ticker=ticker, detail={"buy_order_id": oid})
                        break
                    requotes += 1
                    placed_at = time.time()
            else:
                # 30 分钟兜底超时
                ctx["state"] = "done"
                self.notify(
                    f"动量买单 {ctx['buy_order_id'][:12]}… 等待 30 分钟未全成交，"
                    f"已放弃自动止盈（买单可能仍挂在交易所）", type="warning")
                mo("canceled", buy_status="timeout")
                if mo_writeback and self.api:
                    db.mo_log(env, "TIMEOUT",
                              f"{ticker} 买单 30 分钟未全成交，放弃自动止盈",
                              ticker=ticker,
                              detail={"buy_order_id": ctx["buy_order_id"]})
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            # 关键：watcher 崩溃绝不能假装这一局已结束。真实情况下买单可能
            # 已成交、持仓还在交易所，若 pop 掉 ctx 引擎会立刻重新开单，
            # 造成同一 ticker 双倍持仓。这里置 error 并保留 ctx + DB 的
            # open 状态，由引擎超时清理兜底。
            ctx["state"] = "error"
            ctx["error_ts"] = time.time()
            import traceback
            traceback.print_exc()
            try:
                db.mo_log(env, "ERROR",
                          f"{ticker} 动量 watcher 异常，已锁定该系列禁止重复开单：{ex}",
                          ticker=ticker,
                          detail={"buy_order_id": ctx.get("buy_order_id"),
                                  "state": ctx.get("state")})
            except Exception:
                pass
            try:
                self.notify(
                    f"动量单 {ticker} 监控异常：{ex}\n"
                    f"为避免重复持仓，该系列已暂停开新单，请检查订单页确认持仓",
                    type="negative")
            except Exception:
                pass
        finally:
            # 异常退出时保留 ctx（不 pop），让引擎继续视其为「在途」，
            # 防止第一单实际还持仓、引擎却给同一 ticker 再开一单。
            # 由引擎的超时清理负责最终释放。追价换过 order_id 也要清干净。
            if ctx.get("state") != "error":
                for k, v in list(self._momentum_watchers.items()):
                    if v is ctx:
                        self._momentum_watchers.pop(k, None)

    async def _run_tp_watch(self, ctx: dict, sell_order_id: str,
                             buy_filled: float, tp_count: int,
                             mo) -> None:
        """阶段 2：轮询止盈卖单直到终态。

        关键：deadline 不是固定值，是 ticker 自身的 close_time（市场结算时间）。
        市场结算后交易所会自动取消所有未成交挂单、按结果派彩持仓。
        所以 close_time 一到，不管 sell order 状态是什么，这一局都必须结束。
        """
        env = self.api.env if self.api else "demo"
        ticker = ctx["ticker"]
        mo_writeback = ctx.get("_mo_writeback", False)
        # === 1) 查 ticker 的 close_time，算出 deadline ===
        try:
            mkt = await run.io_bound(self.api.quote, ticker)
            close_ts = _parse_close_time(mkt.get("close_time") if mkt else None)
        except Exception:
            close_ts = None
        if close_ts is not None and close_ts > time.time():
            sell_deadline = close_ts + 30  # 多给 30s 结算 grace period
        else:
            # 拿不到 close_time（比如一次性 one_off 市场），兜底 30min
            sell_deadline = time.time() + 30 * 60
            if close_ts is not None:
                print(f"[momentum] {ticker} close_time 已过期（{close_ts}），"
                      f"市场可能已结算，给 2min grace")
                sell_deadline = time.time() + 2 * 60
        poll_interval = 5.0
        tp_terminal = {"executed", "filled", "canceled", "expired", "rejected"}
        mo_cfg = ctx.get("_mo_cfg") or {}
        try:
            cancel_sec = float(mo_cfg.get("cancel_sec") or 0) if mo_cfg else 0.0
        except (TypeError, ValueError):
            cancel_sec = 0.0
        tp_placed_at = time.time()
        last_status = ""
        # 跨重挂累计：已卖出张数 / 已实现收入 / 当前挂单价 / 当前挂单张数
        sold_qty = 0.0
        proceeds = 0.0
        cur_px = float(ctx["sell_price"])
        cur_qty = int(tp_count)
        requotes = 0
        try:
            while time.time() < sell_deadline:
                await asyncio.sleep(poll_interval)
                s_status = ""
                # === 2) 先查 sell order 状态 ===
                try:
                    s = await run.io_bound(self.api.get_order, sell_order_id)
                    if isinstance(s, dict):
                        s_status = (s.get("status") or "").lower()
                except Exception as ex:
                    print(f"[momentum] tp get_order 失败（忽略重试）：{ex}")
                    continue
                s_filled = 0.0
                if s_status:
                    s_filled = _num(s.get("fill_count_fp") or s.get("fill_count")) or 0.0
                # === 3) 再查 market status（结算后交易所自动清所有挂单）===
                market_closed = False
                try:
                    mkt2 = await run.io_bound(self.api.quote, ticker)
                    mkt_status = (mkt2 or {}).get("status") or ""
                    if mkt_status.lower() in ("closed", "settled", "inactive"):
                        market_closed = True
                except Exception:
                    pass
                due_cancel = (cancel_sec > 0 and not market_closed
                              and s_status not in tp_terminal
                              and time.time() - tp_placed_at >= cancel_sec)
                if s_status == last_status and not market_closed and not due_cancel:
                    continue
                last_status = s_status
                ctx["sell_status"] = s_status or "unknown"
                if s_status:
                    print(f"[momentum] 止盈卖单 {sell_order_id[:12]}… status={s_status} "
                          f"filled={s_filled:g}/{cur_qty}")
                # === 4) sell order 进入终态 ===
                if s_status in tp_terminal:
                    pnl = (proceeds + cur_px * s_filled
                           - ctx["buy_price"] * (sold_qty + s_filled))
                    if s_status in ("executed", "filled"):
                        mo("tp_filled", sell_status=s_status,
                           sell_order_id=sell_order_id,
                           pnl=round(pnl, 4))
                        if mo_writeback and self.api:
                            db.mo_log(env, "TP_FILLED",
                                      f"{ctx['ticker']} 止盈成交 {s_filled:g}/{cur_qty}，"
                                      f"pnl={pnl:+.4f}",
                                      ticker=ctx["ticker"],
                                      detail={"buy_px": ctx["buy_price"],
                                              "sell_px": cur_px,
                                              "requotes": requotes,
                                              "pnl": pnl})
                            self.notify(
                                f"自动动量止盈成交：{ctx['ticker']} {s_filled:g} 张，"
                                f"pnl={pnl:+.2f}", type="positive")
                    else:
                        # 卖单被交易所取消/过期/拒绝：只要还有持仓就立刻转吃单，
                        # 不能只记一条 canceled 把仓位晾在那里。
                        sold_now = sold_qty + s_filled
                        remain_now = int(round(tp_count - sold_now))
                        if remain_now > 0 and not market_closed:
                            flat_filled, flat_px, left = await self._mo_flatten_until_done(
                                ctx, remain_now, sell_deadline)
                            closed_qty = sold_now + flat_filled
                            pnl2 = (proceeds + cur_px * s_filled
                                    + flat_px * flat_filled
                                    - ctx["buy_price"] * closed_qty)
                            if left > 0:
                                ctx["state"] = "error"
                                ctx["error_ts"] = time.time()
                                ctx["sell_status"] = "flatten_incomplete"
                                mo("error", sell_status="flatten_incomplete",
                                   sell_order_id=sell_order_id, pnl=round(pnl2, 4))
                                if mo_writeback and self.api:
                                    db.mo_log(
                                        env, "FLATTEN_INCOMPLETE",
                                        f"{ticker} 止盈卖单 {s_status} 后仍剩 "
                                        f"{left} 张未平！已锁定该 ticker",
                                        ticker=ticker,
                                        detail={"sell_order_id": sell_order_id,
                                                "remaining": left})
                                self.notify(
                                    f"{ticker} 平仓失败，仍有 {left} 张未平掉！"
                                    f"请立即到订单页手动处理", type="negative")
                                return
                            ctx["sell_status"] = "flattened"
                            mo("canceled", sell_status="flattened",
                               sell_order_id=sell_order_id, pnl=round(pnl2, 4))
                            if mo_writeback and self.api:
                                db.mo_log(env, "TP_CANCEL_FLATTEN",
                                          f"{ticker} 止盈卖单 {s_status}，"
                                          f"转吃单平仓 {flat_filled:g} 张 "
                                          f"@{flat_px:.2f}，pnl={pnl2:+.4f}",
                                          ticker=ticker,
                                          detail={"sell_order_id": sell_order_id,
                                                  "flat_filled": flat_filled,
                                                  "flat_px": flat_px})
                            self.notify(
                                f"{ticker} 止盈卖单 {s_status}，已转吃单平仓 "
                                f"{flat_filled:g} 张 @{flat_px:.2f}，pnl={pnl2:+.2f}",
                                type="warning" if pnl2 < 0 else "positive")
                            return
                        # 已无持仓（或市场已结算）：按取消收尾
                        mo("canceled", sell_status=s_status,
                           sell_order_id=sell_order_id)
                        if mo_writeback and self.api:
                            db.mo_log(env, "TP_CANCELED",
                                      f"{ctx['ticker']} 止盈卖单 {s_status}",
                                      ticker=ctx["ticker"],
                                      detail={"sell_order_id": sell_order_id})
                    return
                # === 5) market 已 closed/settled：结算会自动清挂单、派彩持仓 ===
                if market_closed:
                    # 此时 sell order 无论什么状态，结算后都不会再成交了
                    # pnl 已由交易所按结算结果记入，这里把这局标记 closed
                    ctx["sell_status"] = "market_closed"
                    mo("canceled", sell_status="market_closed",
                       sell_order_id=sell_order_id)
                    if mo_writeback and self.api:
                        db.mo_log(env, "MARKET_SETTLED",
                                  f"{ctx['ticker']} 市场已结算，止盈卖单未成交（"
                                  f"pnl 由结算结果决定）",
                                  ticker=ctx["ticker"],
                                  detail={"sell_order_id": sell_order_id})
                    self.notify(
                        f"{ctx['ticker']} 市场已结算，止盈卖单未成交（pnl 由结算决定）",
                        type="info")
                    return
                # === 5.5) 止盈单超过 cancel_sec 未成交 → 撤单 + 立即市价平仓 ===
                if due_cancel:
                    self.notify(
                        f"止盈卖单 {sell_order_id[:12]}… {cancel_sec:.0f}s 未成交，"
                        f"准备撤单重挂", type="info")
                    if not await self._mo_cancel_order(
                            sell_order_id, ticker, "止盈卖单"):
                        continue  # 撤单失败，下一轮重试，绝不裸卖
                    status2, s_filled2 = await self._mo_order_state(sell_order_id)
                    if s_filled2 > s_filled:
                        s_filled = s_filled2
                    if not status2:
                        continue  # 查不到订单状态，无法确认已撤，下一轮再试
                    if status2 in ("resting", "created", "open"):
                        continue  # 撤单尚未生效（罕见），下一轮再试
                    # 把这张单已经成交的部分先计入累计
                    if s_filled > 0:
                        sold_qty += s_filled
                        proceeds += cur_px * s_filled
                    if status2 in ("executed", "filled") and sold_qty >= tp_count:
                        # 撤单瞬间刚好全部成交
                        pnl = proceeds - ctx["buy_price"] * sold_qty
                        ctx["sell_status"] = status2
                        mo("tp_filled", sell_status=status2,
                           sell_order_id=sell_order_id, pnl=round(pnl, 4))
                        if mo_writeback and self.api:
                            db.mo_log(env, "TP_FILLED",
                                      f"{ticker} 撤单前止盈已成交 {sold_qty:g}/{tp_count}，"
                                      f"pnl={pnl:+.4f}", ticker=ticker,
                                      detail={"sell_order_id": sell_order_id,
                                              "pnl": pnl})
                        return
                    remaining = int(round(tp_count - sold_qty))
                    # ---- 先重挂一次止盈单（跟到当前卖一），仍不成交才吃单 ----
                    if remaining > 0 and requotes < 1:
                        new_px = await self._mo_tp_requote_px(ctx)
                        if new_px is not None:
                            old_id = sell_order_id
                            new_side, new_yes_px = DeskAPI.to_book(
                                ctx["action"].replace("buy_", "sell_"), new_px)
                            new_id = await self._place_momentum_sell(
                                ctx["buy_order_id"], ticker, new_side,
                                new_yes_px, remaining, ctx["subaccount"], ctx=ctx)
                            if new_id:
                                requotes += 1
                                sell_order_id = new_id
                                cur_px = new_px
                                cur_qty = remaining
                                tp_placed_at = time.time()
                                last_status = ""
                                mo("tp_requoted", sell_order_id=new_id)
                                if mo_writeback and self.api:
                                    db.mo_log(
                                        env, "TP_REQUOTE",
                                        f"{ticker} 止盈单 {cancel_sec:.0f}s 未成交，"
                                        f"撤单后按卖一 {new_px:.2f} 重挂 {remaining} 张",
                                        ticker=ticker,
                                        detail={"old_order_id": old_id,
                                                "new_order_id": new_id,
                                                "new_px": new_px,
                                                "count": remaining})
                                continue
                    # ---- 重挂失败或已重挂过仍不成交 → 吃单平仓，直到持仓归零 ----
                    flat_filled, flat_px, left = await self._mo_flatten_until_done(
                        ctx, remaining, sell_deadline)
                    closed_qty = sold_qty + flat_filled
                    pnl = (proceeds + flat_px * flat_filled
                           - ctx["buy_price"] * closed_qty)
                    if left > 0:
                        # 仓位没平干净：绝不能当成已结束，锁住该 ticker 等人工处理
                        ctx["state"] = "error"
                        ctx["error_ts"] = time.time()
                        ctx["sell_status"] = "flatten_incomplete"
                        mo("error", sell_status="flatten_incomplete",
                           sell_order_id=sell_order_id, pnl=round(pnl, 4))
                        if mo_writeback and self.api:
                            db.mo_log(
                                env, "FLATTEN_INCOMPLETE",
                                f"{ticker} 止盈单 {cancel_sec:.0f}s 未成交，撤单后"
                                f"仅平掉 {flat_filled:g}/{remaining} 张，"
                                f"仍剩 {left} 张未平！已锁定该 ticker",
                                ticker=ticker,
                                detail={"sell_order_id": sell_order_id,
                                        "remaining": left,
                                        "closed_qty": closed_qty,
                                        "pnl": pnl})
                        self.notify(
                            f"{ticker} 平仓失败，仍有 {left} 张未平掉！"
                            f"请立即到订单页手动处理", type="negative")
                        return
                    ctx["sell_status"] = "flattened"
                    mo("canceled", sell_status="flattened",
                       sell_order_id=sell_order_id, pnl=round(pnl, 4))
                    if mo_writeback and self.api:
                        db.mo_log(env, "TP_CANCEL_FLATTEN",
                                  f"{ticker} 止盈单 {cancel_sec:.0f}s 未成交，撤单后"
                                  f"市价平仓 {flat_filled:g} 张 @{flat_px:.2f}，"
                                  f"pnl={pnl:+.4f}", ticker=ticker,
                                  detail={"sell_order_id": sell_order_id,
                                          "flat_filled": flat_filled,
                                          "flat_px": flat_px})
                    self.notify(
                        f"{ticker} 止盈单撤单后市价平仓 {flat_filled:g} 张 "
                        f"@{flat_px:.2f}，pnl={pnl:+.2f}",
                        type="warning" if pnl < 0 else "positive")
                    return
            # === 6) 兜底：close_time 到了还没终态（极端异常） ===
            ctx["sell_status"] = "deadline"
            mo("tp_placed", sell_status="deadline", sell_order_id=sell_order_id)
            if mo_writeback and self.api:
                db.mo_log(env, "TP_DEADLINE",
                          f"{ctx['ticker']} close_time 已过，止盈卖单仍无终态",
                          ticker=ctx["ticker"],
                          detail={"sell_order_id": sell_order_id})
        except asyncio.CancelledError:
            raise
        except Exception as ex:
            print(f"[momentum] _run_tp_watch 异常：{ex}")

    @staticmethod
    def _parse_close_time(raw) -> Optional[float]:
        """把 close_time 各种格式都转成 unix 秒时间戳。"""
        if raw is None:
            return None
        try:
            v = float(raw)
            if v > 2e10:  # unix 毫秒
                return v / 1000
            return v
        except (TypeError, ValueError):
            pass
        s = str(raw).strip()
        if not s:
            return None
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return dt.timestamp()
        except ValueError:
            pass
        return None

    # ================= 动量机器人（自动下单） =================
    # 设计思路：
    #   引擎每 scan_interval 秒扫描监控 ticker，检测动量方向与强度，
    #   满足阈值且不在冷却期且并行数未超限时触发动量买入。
    #   买入后仍走 _spawn_momentum_watcher 挂止盈 watcher，
    #   但 watcher 额外回写 mo_trades + mo_log 到 DuckDB。
    #   面板定时器每 2 秒刷新状态卡、运行中交易表、历史成交表、日志表。

    def mo_start(self) -> None:
        """启动动量机器人引擎（幂等：已在跑则不重复）。

        状态写模块级 _MO_ENGINE，页面刷新后新实例也能正确显示「运行中」。
        """
        _MO_ENGINE["ui"] = self
        if _MO_ENGINE["running"]:
            self._sync_mo_ui(running=True)
            return
        if not self.api:
            self.notify("请先登录再启动动量机器人", type="warning")
            return
        _MO_ENGINE["running"] = True
        _MO_ENGINE["started_at"] = time.time()
        _MO_ENGINE["last_tick"] = 0.0
        self._mo_cfg_dlg = None
        _MO_ENGINE["task"] = asyncio.create_task(self._mo_engine())
        self._mo_log_safe("INFO", "动量机器人启动",
                          detail={"scan_interval": self.mo_cfg["scan_interval"],
                                  "series": self.mo_cfg.get("series") or []})
        self._sync_mo_ui(running=True)
        # 动量检测依赖本地成交数据：把监控系列加入 WS 订阅（增量，不影响用户在
        # 数据订阅页已选的系列），使其下活跃市场成交自动落库。
        asyncio.create_task(self._mo_ensure_ws())
        self.notify("动量机器人已启动，开始扫描", type="positive")

    def _mo_log_safe(self, level: str, message: str, ticker: str = "",
                     detail: Optional[dict] = None) -> None:
        """写动量日志但绝不因 DB 异常影响 UI 回调（避免按钮点击导致页面报错）。"""
        try:
            env = self.api.env if self.api else "demo"
            db.mo_log(env, level, message, ticker=ticker, detail=detail)
        except Exception as ex:
            print(f"[momentum] 写日志失败（忽略）：{ex}")

    def _sync_mo_ui(self, running: bool) -> None:
        """把模块级引擎状态同步到当前页面的面板元素（元素可能已销毁）。"""
        if self._el("mo_status"):
            if running:
                self.mo_status.set_text("运行中")
                self.mo_status.props('color="positive"')
            else:
                self.mo_status.set_text("已停止")
                self.mo_status.props('color="grey-5"')
        if self._el("mo_toggle"):
            if running:
                self.mo_toggle.props("color=negative").set_text("停止自动动量")
            else:
                self.mo_toggle.props("color=positive").set_text("启动自动动量")

    async def _mo_ensure_ws(self) -> None:
        """确保监控系列已被 WS 订阅，否则动量检测拿不到成交数据。

        注意：这里复用系统全局唯一的 TradeSubscriber（按 env+key_id 单例），
        只做 add_series 增量合并，绝不会新建第二条 WebSocket 连接。
        """
        if not self.api:
            return
        try:
            sub = self._ws_subscriber()
            was_running = sub.running
            for s in (self.mo_cfg.get("series") or []):
                await sub.add_series(s)
            if not sub.running:
                await sub.start()
            db.mo_log(self.api.env, "INFO",
                      "动量机器人复用系统 WS 订阅（无新增连接）",
                      detail={
                          "mo_series": self.mo_cfg.get("series") or [],
                          "shared_series": sorted(sub.series),
                          "ws_already_running": was_running,
                      })
        except Exception as ex:
            db.mo_log(self.api.env, "WARN", f"实时成交订阅启动失败：{ex}")
            self.notify(
                f"实时成交订阅启动失败：{ex}\n"
                f"动量检测将缺少成交数据，建议到「数据订阅」页手动启动连接",
                type="warning")

    def mo_stop(self) -> None:
        """停止引擎（幂等，任何页面实例都能停掉模块级单例引擎）。"""
        if not _MO_ENGINE["running"]:
            self._sync_mo_ui(running=False)
            return
        _MO_ENGINE["running"] = False
        task = _MO_ENGINE.get("task")
        if task is not None and not task.done():
            task.cancel()
        _MO_ENGINE["task"] = None
        self._mo_log_safe("INFO", "动量机器人停止")
        self._sync_mo_ui(running=False)
        self.notify("动量机器人已停止（已挂的 watcher 继续生效直到止盈/取消）",
                    type="info")

    async def _mo_engine(self) -> None:
        """引擎主循环：每轮取最新的 UI 宿主执行一次扫描。

        引擎不绑定某个 DeskUI 实例——页面刷新后 _MO_ENGINE['ui'] 会指向新实例，
        扫描继续用最新的 api / 配置 / notify，不会中断。
        所有异常都 catch 并记日志，不让引擎整体挂掉。
        """
        try:
            while _MO_ENGINE["running"]:
                ui = _MO_ENGINE.get("ui")
                if ui is None or not ui.api:
                    await asyncio.sleep(2)
                    continue
                env = ui.api.env
                cfg = ui.mo_cfg or store.MO_DEFAULT
                _MO_ENGINE["last_tick"] = time.time()
                try:
                    await self._mo_scan_round(ui, cfg, env)
                except asyncio.CancelledError:
                    raise
                except Exception as ex:
                    db.mo_log(env, "ERROR", f"扫描轮次异常：{ex}")
                await asyncio.sleep(max(2, int(cfg.get("scan_interval") or 5)))
        except asyncio.CancelledError:
            if self.api:
                db.mo_log(self.api.env, "INFO", "动量引擎协程被取消")
        except Exception as ex:
            _MO_ENGINE["running"] = False
            db.mo_log(self.api.env if self.api else "demo",
                      "ERROR", f"动量引擎异常终止：{ex}")

    async def _mo_scan_round(self, ui: "DeskUI", cfg: dict, env: str) -> None:
        """单轮扫描：确认订阅 → 收集 ticker → 检查并行上限 → 逐个尝试触发。"""
        # 确保监控系列仍在「共享的那一条 WS 订阅」里。
        # 数据订阅页保存时用的是 set_series（覆盖语义），可能把机器人加的系列
        # 冲掉；这里最多每 60 秒检查一次，只在缺失时增量补回，不重复建连。
        now = time.time()
        if now - _MO_ENGINE.get("last_ws_ensure", 0.0) > 60:
            _MO_ENGINE["last_ws_ensure"] = now
            try:
                sub = ui._ws_subscriber()
                want = {s.upper() for s in (cfg.get("series") or []) if s}
                missing = want - set(sub.series)
                if missing:
                    for s in sorted(missing):
                        await sub.add_series(s)
                    ui._mo_log_safe(
                        "INFO", f"共享订阅缺失，已增量补回：{sorted(missing)}",
                        detail={"shared_series": sorted(sub.series)})
            except Exception as ex:
                ui._mo_log_safe("WARN", f"检查共享订阅失败：{ex}")
        # 清理长期卡在 error 状态的 watcher，避免该系列被永久锁死。
        # 释放前把 DB 记录置为 failed 终态，并明确提示用户核对持仓。
        for oid, c in list(_MO_ENGINE["watchers"].items()):
            if c.get("state") == "error" and now - c.get("error_ts", 0) > 1800:
                _MO_ENGINE["watchers"].pop(oid, None)
                try:
                    db.mo_upsert_trade(env, oid, state="failed",
                                       sell_status="watcher_error")
                except Exception:
                    pass
                ui._mo_log_safe(
                    "WARN", f"{c.get('ticker')} watcher 异常已超 30 分钟，"
                            f"强制释放该系列（请核对持仓）", ticker=c.get("ticker", ""))
        candidates = await ui._mo_collect_tickers(cfg)
        if not candidates:
            return
        # 交易所真实持仓：有持仓的 ticker 绝不再开新仓，
        # 哪怕库里记录已是终态（防止平仓回报异常时重复开仓）
        held = set()
        try:
            rows = await run.io_bound(self.api.positions)
            held = {p.get("ticker") for p in (rows or [])
                    if abs(float(p.get("position") or 0)) >= 0.5}
        except Exception as ex:
            db.mo_log(env, "WARN", f"查询持仓失败，本轮仅用库内判据：{ex}")
        open_count = len(_MO_ENGINE["watchers"])
        if open_count >= cfg["max_parallel"]:
            db.mo_log(env, "DEBUG",
                      f"并行数已满 {open_count}/{cfg['max_parallel']}",
                      ticker=candidates[0][0])
            return
        budget = cfg["max_parallel"] - open_count
        triggered = 0
        for ticker, series in candidates:
            if triggered >= budget:
                break
            try:
                if await ui._mo_try_trade(ticker, series, cfg, held):
                    triggered += 1
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                db.mo_log(env, "ERROR", f"扫描 {ticker} 异常：{ex}", ticker=ticker)

    async def _mo_collect_tickers(self, cfg: dict) -> list[tuple[str, str]]:
        """候选市场 ticker：把配置的「系列」展开成当前活跃的市场 ticker。

        返回 [(市场 ticker, 所属系列), ...]。系列必须一起带出去，因为同系列
        互斥开单要按 series 判断，而滚场后市场 ticker 会变（...-30 → ...-45）。

        KXBTC15M 只是系列名，真正可交易的是带时间后缀的市场。每个 15 分钟
        系列同时活跃的通常只有 2~3 个（当前场、下一场），每轮扫描重新拉取。
        """
        series_list = [s for s in (cfg.get("series") or []) if s]
        pairs: list[tuple[str, str]] = []
        seen: set[str] = set()
        if series_list:
            for s in series_list:
                try:
                    mks = await run.io_bound(
                        self.api.markets_by_series, s, True, 1)
                    for m in mks or []:
                        t = m.get("ticker")
                        if t and t not in seen:
                            seen.add(t)
                            pairs.append((t, s))
                except Exception as ex:
                    db.mo_log(self.api.env, "WARN",
                              f"拉取系列 {s} 的活跃市场失败：{ex}")
            return pairs[:50]
        # 兜底：没配系列时用 WS 已订阅的活跃 tickers（无法判断系列，用空串）
        try:
            rows = await run.io_bound(db.market_trades_latest, self.api.env)
            pairs = [(t, "") for t in rows.keys()]
        except Exception:
            pairs = []
        return pairs[:50]

    async def _mo_try_trade(self, ticker: str, series: str, cfg: dict,
                             held: set = None) -> bool:
        """扫描单个市场 ticker，满足条件则下单。返回 True 表示本次触发。

        互斥铁律：同一「系列」同时只能有一笔动量单在途。因为 KXBTC15M 滚场后
        市场 ticker 会变（...-30 → ...-45），只按 ticker 去重会漏掉跨场次重复
        开单。所以同时用两道判据：
          1) 内存 watchers 里有同 series 的活动单
          2) DuckDB 里有同 series 的未完成记录（watcher 丢失时的兜底）
        """
        env = self.api.env
        now = time.time()
        # 冷却期
        cooldown_until = self._mo_cooldown_until.get(ticker, 0)
        if now < cooldown_until:
            return False
        # ---- 判据 0：交易所真实持仓 ----
        # 只要这个 ticker 还有仓位，就绝不开新仓（库内记录可能是错的）
        if held and ticker in held:
            db.mo_log(env, "DEBUG",
                      f"{ticker} 交易所仍有持仓，跳过开新仓", ticker=ticker)
            return False
        # ---- 判据 1：内存 watcher 同 ticker 去重 ----
        # 跨 ticker（哪怕同 series）= 旧场已滚场结算，不阻塞新 ticker。
        for ctx in self._momentum_watchers.values():
            if ctx["ticker"] == ticker:
                db.mo_log(env, "DEBUG",
                          f"内存 watcher 同 ticker {ticker} "
                          f"（状态 {ctx['state']}），跳过",
                          ticker=ticker)
                return False
        # ---- 判据 2：DB 未完成记录兜底（仅同 ticker 才阻塞） ----
        try:
            opens = await run.io_bound(db.mo_open_by_ticker, env, ticker, 60)
            if opens:
                o = opens[0]
                db.mo_log(env, "DEBUG",
                          f"同 ticker {ticker} 在库里有未完成单 "
                          f"（{o.get('state')}），跳过",
                          ticker=ticker)
                return False
        except Exception as ex:
            db.mo_log(env, "WARN", f"检查同 ticker 未完成单失败：{ex}",
                      ticker=ticker)
        # 拉最新盘口（状态 / frac 区间 / 定价共用，避免重复请求）
        try:
            live = await run.io_bound(self.api.quote, ticker)
        except Exception as ex:
            db.mo_log(env, "WARN", f"{ticker} 拉 quote 失败：{ex}", ticker=ticker)
            return False
        status = (live or {}).get("status")
        if status and status != "active":
            return False
        # ---- frac 区间：只在市场生命周期 [frac_start, frac_end] 内开单 ----
        frac = self._mo_market_frac(live or {})
        if frac is not None and not (cfg["frac_start"] <= frac <= cfg["frac_end"]):
            return False
        # 动量检测
        direction, delta = await self._detect_momentum(ticker)
        abs_delta = abs(delta)
        strength = "强" if abs_delta >= 0.03 else ("中" if abs_delta >= 0.01 else "弱")
        threshold_map = {"弱": 0.00, "中": 0.01, "强": 0.03}
        need_min_delta = threshold_map.get(cfg["min_strength"], 0.01)
        if abs_delta < max(cfg["min_delta"], need_min_delta):
            return False
        buy_price = self._momentum_buy_px(live or {}, direction)
        if buy_price is None:
            return False
        tp_mult = await self._mo_tp_mult_cf(cfg, ticker, direction, live)
        sell_price = self._momentum_tp_px(buy_price, tp_mult)
        if sell_price <= buy_price:
            return False
        count = int(cfg["qty"])
        action = "buy_yes" if direction == "yes" else "buy_no"
        buy_side, buy_yes_px = DeskAPI.to_book(action, buy_price)
        sell_action = action.replace("buy_", "sell_")
        sell_side, sell_yes_px = DeskAPI.to_book(sell_action, sell_price)
        # 挂单
        buy_order_id = ""
        try:
            resp = await run.io_bound(
                lambda: self.api.place(ticker, buy_side, buy_yes_px, count,
                                        cfg["buy_tif"], post_only=False,
                                        subaccount=int(cfg["subaccount"])))
            buy_order_id = resp.get("order_id") or ""
        except Exception as ex:
            db.mo_log(env, "ERROR", f"{ticker} 下单失败：{ex}", ticker=ticker,
                      detail={"delta": delta, "buy_px": buy_price, "sell_px": sell_price})
            return False
        if not buy_order_id:
            db.mo_log(env, "WARN", f"{ticker} 买单无 order_id：{resp}", ticker=ticker)
            return False
        # 落库：mo_trades 初始态 + mo_log
        db.mo_upsert_trade(env, buy_order_id,
                           ticker=ticker, series=series, direction=direction,
                           delta=delta, buy_px=buy_price, buy_count=count,
                           buy_tif=cfg["buy_tif"],
                           buy_status=resp.get("status") or "resting",
                           sell_px=sell_price, subaccount=int(cfg["subaccount"]),
                           state="buy_placed")
        db.mo_log(env, "TRADE",
                  f"买入 {ACTION_LABEL[action]} {ticker} @{buy_price:.2f} "
                  f"×{count}，Δ{delta:+.3f}（动量{strength}）→ 止盈 "
                  f"{sell_price:.2f}（×{tp_mult:.3f}）",
                  ticker=ticker,
                  detail={"buy_order_id": buy_order_id, "buy_side": buy_side,
                          "sell_side": sell_side, "buy_yes_px": buy_yes_px,
                          "sell_yes_px": sell_yes_px})
        # 起 watcher（多传两个参数：mo_upsert_trade / mo_log 回写）
        await self._spawn_momentum_watcher(
            buy_order_id, ticker, sell_side, sell_yes_px, count,
            int(cfg["subaccount"]), action, buy_price, sell_price,
            _mo_writeback=True, series=series, mo_cfg=cfg)
        # 冷却期
        self._mo_cooldown_until[ticker] = now + cfg["taker_interval"]
        return True

    # ================= 动量机器人 UI =================
    def build_momentum_bot(self) -> None:
        """动量机器人面板：状态卡 + 启停按钮 + 配置 + 运行中交易 + 历史 + 日志。"""
        running = bool(_MO_ENGINE["running"])
        with ui.row().classes("w-full items-center gap-3"):
            ui.label("动量机器人").classes("kd-section")
            self.mo_status = ui.label("运行中" if running else "已停止").classes("kd-key")
            if running:
                self.mo_status.props('color="positive"')
            ui.space()
            self.mo_cfg_btn = ui.button("配置参数", icon="tune",
                                        on_click=self._open_mo_cfg).props("flat dense")
            self.mo_toggle = ui.button(
                "停止自动动量" if running else "启动自动动量",
                icon="auto_graph",
                on_click=self._toggle_mo_engine_safe) \
                .props(f"unelevated dense color={'negative' if running else 'positive'}")
        # === 状态卡 ===
        with ui.row().classes("w-full gap-2"):
            self.mo_stat_total = ui.label("近24h动量单：0").classes("text-xs kd-mut")
            self.mo_stat_wins = ui.label("止盈：0").classes("text-xs kd-mut")
            self.mo_stat_tps = ui.label("运行中止盈：0").classes("text-xs kd-mut")
            self.mo_stat_cancel = ui.label("取消：0").classes("text-xs kd-mut")
            self.mo_stat_pnl = ui.label("pnl：$0.00").classes("text-xs kd-mut")
            self.mo_stat_watchers = ui.label("活动 watcher：0").classes("text-xs kd-mut")
            self.mo_stat_last = ui.label("上次扫描：—").classes("text-xs kd-mut")
        # === 运行中动量单 ===
        ui.label("运行中动量单").classes("kd-subsection")
        self.mo_open_table = ui.table(
            columns=[
                {"name": "created_ts", "label": "开单时间", "field": "created_ts",
                 "sortable": True, "align": "left"},
                {"name": "ticker", "label": "Ticker", "field": "ticker"},
                {"name": "direction", "label": "腿", "field": "direction"},
                {"name": "delta", "label": "Δ", "field": "delta", "format": "%.4f"},
                {"name": "buy_px", "label": "买入价", "field": "buy_px", "format": "%.2f"},
                {"name": "buy_count", "label": "张数", "field": "buy_count"},
                {"name": "buy_status", "label": "买单状态", "field": "buy_status"},
                {"name": "sell_px", "label": "止盈价", "field": "sell_px", "format": "%.2f"},
                {"name": "sell_status", "label": "卖单状态", "field": "sell_status"},
                {"name": "state", "label": "阶段", "field": "state"},
            ], rows=[], row_key="buy_order_id").classes("w-full")
        # === 历史动量单 ===
        ui.label("历史动量单（近 200 条）").classes("kd-subsection")
        self.mo_hist_table = ui.table(
            columns=[
                {"name": "created_ts", "label": "时间", "field": "created_ts",
                 "sortable": True, "align": "left"},
                {"name": "ticker", "label": "Ticker", "field": "ticker"},
                {"name": "direction", "label": "腿", "field": "direction"},
                {"name": "delta", "label": "Δ", "field": "delta", "format": "%.4f"},
                {"name": "buy_px", "label": "买价", "field": "buy_px", "format": "%.2f"},
                {"name": "sell_px", "label": "止盈", "field": "sell_px", "format": "%.2f"},
                {"name": "buy_count", "label": "张数", "field": "buy_count"},
                {"name": "state", "label": "最终状态", "field": "state"},
                {"name": "pnl", "label": "pnl", "field": "pnl", "format": "%.4f"},
            ], rows=[], row_key="buy_order_id").classes("w-full")
        # === 运行日志 ===
        ui.label("运行日志").classes("kd-subsection")
        self.mo_log_table = ui.table(
            columns=[
                {"name": "ts", "label": "时间", "field": "ts", "sortable": True,
                 "align": "left"},
                {"name": "level", "label": "级别", "field": "level"},
                {"name": "ticker", "label": "Ticker", "field": "ticker"},
                {"name": "message", "label": "消息", "field": "message"},
            ], rows=[], row_key="__idx__").classes("w-full")
        # 面板定时器：2 秒刷新
        with ui.card().classes("w-full").props("flat").style("display:none"):
            self._mo_panel_timer = ui.timer(2.0, self.refresh_momentum_panel)

    async def refresh_momentum_panel(self) -> None:
        """刷新动量机器人面板。所有 DB / 元素访问都必须容错：
        面板是 2 秒定时器驱动的，任何未捕获异常都会持续刷屏且可能影响页面。
        """
        if not self.api:
            return
        # 元素已被页面重建销毁时直接跳过
        if not self._el("mo_stat_total"):
            return
        try:
            self._refresh_momentum_panel_inner()
        except Exception as ex:
            print(f"[momentum] 面板刷新失败（忽略）：{ex}")

    def _refresh_momentum_panel_inner(self) -> None:
        env = self.api.env
        # === 状态卡 ===
        stats = db.mo_stats(env, 24)
        if self._el("mo_stat_total"):
            self.mo_stat_total.set_text(f"近24h动量单：{stats['total']}")
        if self._el("mo_stat_wins"):
            self.mo_stat_wins.set_text(f"止盈：{stats['wins']}")
        if self._el("mo_stat_tps"):
            self.mo_stat_tps.set_text(f"运行中止盈：{stats['tps_resting']}")
        if self._el("mo_stat_cancel"):
            self.mo_stat_cancel.set_text(f"取消：{stats['canceled']}")
        if self._el("mo_stat_pnl"):
            self.mo_stat_pnl.set_text(f"pnl：{usd(stats['pnl'], signed=True)}")
        if self._el("mo_stat_watchers"):
            self.mo_stat_watchers.set_text(
                f"活动 watcher：{len(_MO_ENGINE['watchers'])}")
        if self._el("mo_stat_last"):
            last = datetime.fromtimestamp(_MO_ENGINE["last_tick"]).strftime("%H:%M:%S") \
                if _MO_ENGINE["last_tick"] else "—"
            self.mo_stat_last.set_text(f"上次扫描：{last}")
        # 引擎状态与模块级标志保持一致（防止多页面不同步）
        if self._el("mo_status"):
            want = "运行中" if _MO_ENGINE["running"] else "已停止"
            if getattr(self.mo_status, "text", "") != want:
                self.mo_status.set_text(want)
                self.mo_status.props(
                    'color="positive"' if _MO_ENGINE["running"] else 'color="grey-5"')
        # === 运行中交易 ===
        opens = db.mo_trades(env, only_open=True, limit=50)
        mo_order_ids = {r["buy_order_id"] for r in opens}
        for ctx in _MO_ENGINE["watchers"].values():
            if ctx["buy_order_id"] not in mo_order_ids:
                opens.append({
                    "buy_order_id": ctx["buy_order_id"],
                    "ticker": ctx["ticker"],
                    "direction": "yes" if ctx["action"] == "buy_yes" else "no",
                    "delta": 0.0,
                    "buy_px": ctx["buy_price"],
                    "sell_px": ctx["sell_price"],
                    "buy_count": ctx["count"],
                    "buy_status": "active",
                    "sell_status": "—",
                    "state": ctx["state"],
                    "created_ts": datetime.now(),
                })
        if self._el("mo_open_table"):
            self.mo_open_table.rows = [self._fmt_mo_row(r, include_ticker=True)
                                       for r in opens]
        # === 历史 ===
        if self._el("mo_hist_table"):
            hist = db.mo_trades(env, only_open=False, limit=200)
            self.mo_hist_table.rows = [self._fmt_mo_row(r) for r in hist]
        # === 日志 ===
        if self._el("mo_log_table"):
            logs = db.mo_log_recent(env, limit=100)
            logs.reverse()   # TS DESC → ASC（UI 上倒序更自然）
            self.mo_log_table.rows = [
                {"__idx__": str(h.get("ts")),
                 "ts": fmt_ts(h.get("ts")),
                 "level": h.get("level"),
                 "ticker": h.get("ticker", ""),
                 "message": h.get("message")}
                for h in logs]

    @staticmethod
    def _fmt_mo_row(r: dict, include_ticker: bool = False) -> dict:
        out = dict(r)
        for key in ("buy_px", "sell_px", "delta", "pnl"):
            v = r.get(key)
            try:
                out[key] = round(float(v), 4) if v is not None else None
            except (TypeError, ValueError):
                out[key] = v
        out["created_ts"] = fmt_dt(r.get("created_ts"))
        return out

    def _toggle_mo_engine(self) -> None:
        if _MO_ENGINE["running"]:
            self.mo_stop()
        else:
            self.mo_start()

    async def _toggle_mo_engine_safe(self) -> None:
        """按钮入口的安全包装：启停过程任何异常都只在通知里提示，
        绝不冒泡到 NiceGUI 事件处理器（否则会触发 500 页面、看起来像“退出系统”）。"""
        try:
            self._toggle_mo_engine()
        except Exception as ex:
            import traceback
            traceback.print_exc()
            try:
                self.notify(f"启停动量机器人失败：{ex}", type="negative")
            except Exception:
                pass

    # ==== 配置对话框 ====
    def _open_mo_cfg(self) -> None:
        if self._mo_cfg_dlg is None:
            env = self.api.env if self.api else "demo"
            all_cats = db.categories(env)
            current_cat = self.mo_cfg.get("category") or "Crypto"
            if current_cat not in all_cats:
                current_cat = "Crypto" if "Crypto" in all_cats else (all_cats[0] if all_cats else "Crypto")
            series_opts = [r["ticker"] for r in db.series_by_category(env, current_cat)]
            if not series_opts:
                series_opts = ["KXBTC15M"]
            current_series = [s for s in (self.mo_cfg.get("series") or []) if s in series_opts] \
                or [s for s in ["KXBTC15M"] if s in series_opts] or series_opts[:1]
            dlg = ui.dialog().props("persistent")
            with dlg, ui.card().classes("w-[760px]"):
                ui.label("动量机器人配置").classes("text-lg font-semibold")
                with ui.grid(columns=2).classes("w-full gap-2"):
                    self.cfg_cat = ui.select(
                        options=all_cats if all_cats else ["Crypto"],
                        value=current_cat, label="品类（用于筛选系列）",
                        multiple=False).classes("w-full")
                    self.cfg_series = ui.select(
                        options=series_opts, value=current_series,
                        label="监控系列（可多选）", multiple=True,
                        with_input=True).classes("w-full")
                    self.cfg_tif = ui.toggle(
                        {"immediate_or_cancel": "IOC 立即吃单",
                         "good_till_canceled": "GTC 挂单"},
                        value=self.mo_cfg["buy_tif"]).props("dense").classes("w-full")
                    self.cfg_strength = ui.toggle(
                        {"弱": "弱", "中": "中", "强": "强"},
                        value=self.mo_cfg["min_strength"]).props("dense").classes("w-full")
                    self.cfg_frac_start = ui.number(
                        "开始 frac（默认 2/15）", value=self.mo_cfg["frac_start"],
                        min=0.0, max=0.99, step=0.01,
                        format="%.3f").classes("w-full")
                    self.cfg_frac_end = ui.number(
                        "结束 frac（默认 14/15）", value=self.mo_cfg["frac_end"],
                        min=0.01, max=1.0, step=0.01,
                        format="%.3f").classes("w-full")
                    self.cfg_qty = ui.number("每次张数", value=self.mo_cfg["qty"],
                                             min=1).classes("w-full")
                    self.cfg_tp = ui.number("止盈倍率", value=self.mo_cfg["tp_mult"],
                                            min=1.01, max=3.0, step=0.05,
                                            format="%.2f").classes("w-full")
                    self.cfg_tp_cf = ui.switch(
                        "参考 CF 差值动态止盈",
                        value=bool(self.mo_cfg["tp_cf_boost"])).classes("w-full")
                    self.cfg_tp_cf_max = ui.number(
                        "止盈倍率上限", value=self.mo_cfg["tp_cf_max"],
                        min=1.0, max=3.0, step=0.01,
                        format="%.2f").classes("w-full")
                    self.cfg_scan = ui.number("扫描间隔(秒)",
                                              value=self.mo_cfg["scan_interval"],
                                              min=2).classes("w-full")
                    self.cfg_cool = ui.number("冷却(秒)",
                                             value=self.mo_cfg["taker_interval"],
                                             min=0).classes("w-full")
                    self.cfg_max = ui.number("并行上限",
                                             value=self.mo_cfg["max_parallel"],
                                             min=1).classes("w-full")
                    self.cfg_cancel = ui.number("未成交撤单(秒)",
                                                value=self.mo_cfg["cancel_sec"],
                                                min=3, max=600).classes("w-full")
                    self.cfg_sub = ui.number("子账户",
                                             value=self.mo_cfg["subaccount"],
                                             min=0).classes("w-full")
                    self.cfg_delta = ui.number("最小 Δ(美元)",
                                               value=self.mo_cfg["min_delta"],
                                               min=0, step=0.001,
                                               format="%.3f").classes("w-full")
                # 活跃市场 ticker（系统自动发现，只读展示）
                with ui.row().classes("w-full items-center gap-2"):
                    ui.label("当前活跃市场 ticker（系统自动发现，无需手填）") \
                        .classes("text-xs kd-mut")
                    self.cfg_tick_count = ui.label("—").classes("text-xs kd-mut")
                    ui.space()
                    ui.button("立即刷新", icon="refresh",
                              on_click=lambda: asyncio.create_task(
                                  self._mo_cfg_refresh_markets())) \
                        .props("flat dense").classes("text-xs")
                self.cfg_tick_table = ui.table(
                    columns=[
                        {"name": "series", "label": "系列", "field": "series"},
                        {"name": "ticker", "label": "市场 ticker", "field": "ticker"},
                        {"name": "label", "label": "场次", "field": "label"},
                    ], rows=[], row_key="ticker").classes("w-full").props("dense")
                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("取消", on_click=dlg.close).props("flat")
                    ui.button("保存", icon="save",
                              on_click=lambda: self._save_mo_cfg(dlg)) \
                        .props("unelevated color=positive")
            self.cfg_cat.on_value_change(lambda e: self._mo_cfg_on_cat_change(e.value))
            self._mo_cfg_dlg = dlg
        self._mo_cfg_dlg.open()
        asyncio.create_task(self._mo_cfg_refresh_markets())

    def _mo_cfg_on_cat_change(self, category: str) -> None:
        """换品类 → 重新加载该品类下的系列选项。"""
        env = self.api.env if self.api else "demo"
        series_opts = [r["ticker"] for r in db.series_by_category(env, category or "")]
        if not series_opts:
            series_opts = ["KXBTC15M"]
        keep = [s for s in (self.cfg_series.value or []) if s in series_opts]
        self.cfg_series.options = series_opts
        self.cfg_series.value = keep or series_opts[:1]
        self.cfg_series.update()
        asyncio.create_task(self._mo_cfg_refresh_markets())

    async def _mo_cfg_refresh_markets(self) -> None:
        """拉取所选系列下当前活跃的市场 ticker（通常每个系列 2~3 个）。"""
        if not self.api or not self._el("cfg_series") or not self._el("cfg_tick_table"):
            return
        series_list = [s for s in (self.cfg_series.value or []) if s]
        rows: list[dict] = []
        errors: list[str] = []
        for s in series_list:
            try:
                mks = await run.io_bound(self.api.markets_by_series, s, True, 1)
                for m in mks or []:
                    rows.append({
                        "series": s,
                        "ticker": m.get("ticker"),
                        "label": m.get("label") or "",
                    })
            except Exception as ex:
                errors.append(f"{s}: {ex}")
        if self._el("cfg_tick_table"):
            self.cfg_tick_table.rows = rows
        if self._el("cfg_tick_count"):
            txt = f"{len(rows)} 个活跃市场 ticker"
            if errors:
                txt += f"（{len(errors)} 个系列拉取失败）"
            self.cfg_tick_count.set_text(txt)
        if errors:
            self.notify(f"部分系列拉取失败：{errors[0]}", type="warning")

    def _save_mo_cfg(self, dlg) -> None:
        try:
            env = self.api.env if self.api else "demo"
            category = str(self.cfg_cat.value or "").strip()
            series = [str(s).strip().upper() for s in (self.cfg_series.value or [])
                      if str(s).strip()]
            if not series:
                self.notify("请至少选择一个监控系列", type="warning")
                return
            new = {
                "buy_tif": self.cfg_tif.value,
                "min_strength": self.cfg_strength.value,
                "qty": int(self.cfg_qty.value or 1),
                "tp_mult": float(self.cfg_tp.value or 1.1),
                "tp_cf_boost": bool(self.cfg_tp_cf.value),
                "tp_cf_max": float(self.cfg_tp_cf_max.value or 1.1),
                "frac_start": float(self.cfg_frac_start.value
                                    if self.cfg_frac_start.value is not None else 0.1333),
                "frac_end": float(self.cfg_frac_end.value
                                  if self.cfg_frac_end.value is not None else 0.9333),
                "scan_interval": int(self.cfg_scan.value or 5),
                "taker_interval": int(self.cfg_cool.value or 60),
                "max_parallel": int(self.cfg_max.value or 3),
                "cancel_sec": int(self.cfg_cancel.value or 30),
                "subaccount": int(self.cfg_sub.value or 0),
                "min_delta": float(self.cfg_delta.value or 0.01),
                "category": category,
                "series": series,
                "enabled": _MO_ENGINE["running"],
                "stop_loss": 0.0,
            }
            store.save_momentum(new)
            self.mo_cfg = store.load_config()["momentum"]
            dlg.close()
            db.mo_log(env, "INFO", "动量配置已更新",
                      detail={"category": category, "series": series})
            self.notify(
                f"配置已保存：监控系列 {', '.join(series)}。\n"
                f"每个系列下活跃的市场 ticker 由系统自动发现并随滚场切换。",
                type="positive")
        except Exception as ex:
            self.notify(f"保存失败：{ex}", type="negative")


    # ================= 订单详情 / 撤单 =================
    async def open_order(self, order_id: Optional[str]) -> None:
        o = self.order_by_id.get(order_id)
        if not o:
            return
        settle = None
        settle_msg = ""
        if o.get("status") in ("executed", "filled"):
            try:
                rows = await run.io_bound(db.settlements, self.api.env, o.get("ticker"))
                settle = next((x for x in rows if x.get("ticker") == o.get("ticker")), None)
                if settle is None:  # 本地没有则回源一次并落库
                    rows = await run.io_bound(self.api.settlements, o.get("ticker"))
                    if rows:
                        await run.io_bound(db.save_settlements, self.api.env, rows)
                    settle = next((x for x in rows if x.get("ticker") == o.get("ticker")), None)
                if settle is None:
                    settle_msg = "该市场尚未结算，暂无结算记录"
            except Exception as ex:
                settle_msg = f"结算信息获取失败：{ex}"
        self.order_dlg.clear()
        with self.order_dlg, ui.card().classes("w-[620px] max-w-[96vw] gap-2"):
            with ui.row().classes("w-full items-center"):
                ui.label("订单详情").classes("text-lg font-semibold")
                ui.space()
                ui.button(icon="close", on_click=self.order_dlg.close).props("flat round dense")
            for label, value in (
                ("订单号", o.get("order_id")),
                ("client_order_id", o.get("client_order_id")),
                ("市场", o.get("ticker")),
                ("方向", o.get("side_txt")),
                ("价格", usd(o.get("price"))),
                ("数量", f"{(o.get('count') or 0):g}"),
                ("已成交 / 剩余", f"{(o.get('filled') or 0):g} / {(o.get('remaining') or 0):g}"),
                ("状态", o.get("status")),
                ("TIF", o.get("tif")),
                ("手续费", usd(o.get("fees"))),
                ("shard", o.get("exchange_index")),
                ("创建时间", fmt_ts(o.get("created"))),
            ):
                with ui.row().classes("w-full justify-between"):
                    ui.label(label).classes("text-xs kd-mut")
                    ui.label("—" if value is None else str(value)).classes("text-sm font-mono")
            if o.get("status") in ("executed", "filled"):
                ui.separator()
                ui.label("结算信息").classes("text-sm font-semibold")
                if settle:
                    result = (settle.get("market_result") or "").lower()
                    result_txt = {"yes": "YES 胜出", "no": "NO 胜出"}.get(result,
                                                                        result or "—")
                    payout = ((settle["yes_count"] if result == "yes" else 0.0)
                              + (settle["no_count"] if result == "no" else 0.0))
                    net = payout - settle["yes_cost"] - settle["no_cost"] - settle["fee"]
                    for label, value in (
                        ("结算结果", result_txt),
                        ("结算时间", fmt_ts(settle.get("settled_time"))),
                        ("YES 张数 / 成本", f"{settle['yes_count']:g} 张 / {usd(settle['yes_cost'])}"),
                        ("NO 张数 / 成本", f"{settle['no_count']:g} 张 / {usd(settle['no_cost'])}"),
                        ("派彩", usd(payout)),
                        ("结算手续费", usd(settle["fee"])),
                        ("净盈亏", usd(net, signed=True)),
                    ):
                        with ui.row().classes("w-full justify-between"):
                            ui.label(label).classes("text-xs kd-mut")
                            ui.label(value).classes("text-sm font-mono")
                else:
                    ui.label(settle_msg).classes("text-xs kd-mut")
            if o.get("status") == "resting":
                with ui.row().classes("w-full justify-end"):
                    self._api_btn("撤单", icon="cancel",
                                  coro=lambda: self.cancel_order(o)) \
                        .props("unelevated color=negative")
        self.order_dlg.open()

    async def cancel_order(self, o: dict) -> None:
        if not await self.confirm(f"撤销订单？\n{o.get('ticker')}  {o.get('side_txt')}  "
                                  f"剩余 {(o.get('remaining') or 0):g} 张"):
            return
        try:
            await run.io_bound(self.api.cancel, o.get("order_id"), o.get("ticker"))
            self.notify("已撤单", type="positive")
            self.order_dlg.close()
            await self._after_trade()
        except Exception as ex:
            self.notify(f"撤单失败：{ex}", type="negative")

    # ================= 资金操作 =================
    async def do_transfer_sub(self) -> None:
        try:
            frm = int(self.t_from.value or 0)
            to = int(self.t_to.value or 0)
            amt = float(self.t_amt.value or 0)
            shard = self.t_shard.value
            shard = None if shard is None or shard == "" else int(shard)
        except (TypeError, ValueError):
            ui.notify("转账参数不合法", type="warning")
            return
        if amt <= 0:
            ui.notify("金额必须大于 0", type="warning")
            return
        if frm == to and shard is None:
            ui.notify("同 shard 内不能转给同一子账户", type="warning")
            return
        text = f"子账户 {frm} → {to}，金额 {usd(amt)}" + (f"，shard {shard}" if shard is not None else "")
        if not await self.confirm(text):
            return
        try:
            await run.io_bound(lambda: self.api.transfer_subaccounts(frm, to, amt, shard))
            ui.notify("转账已提交", type="positive")
            await self.refresh_all(manual=True)
            await self.refresh_transfers()
        except Exception as ex:
            ui.notify(f"转账失败：{ex}", type="negative")

    async def do_transfer_shard(self) -> None:
        try:
            frm = int(self.x_from.value or 0)
            to = int(self.x_to.value or 0)
            amt = float(self.x_amt.value or 0)
        except (TypeError, ValueError):
            ui.notify("转账参数不合法", type="warning")
            return
        if frm == to:
            ui.notify("源 shard 与目标 shard 不能相同", type="warning")
            return
        if amt <= 0:
            ui.notify("金额必须大于 0", type="warning")
            return
        src, dst = self.x_src.value, self.x_dst.value
        if not await self.confirm(f"跨 shard 转账：shard {frm} → {to}\n金额 {usd(amt)}"
                                  f"（{src} → {dst}）"):
            return
        try:
            r = await run.io_bound(lambda: self.api.transfer_across_shards(
                frm, to, amt, src, dst))
            tid = str((r or {}).get("transfer_id") or "")
            self.notify(f"跨 shard 转账成功：shard {frm} → {to}，{usd(amt)}"
                        + (f"（{tid[:8]}）" if tid else ""), type="positive")
            await self.refresh_all(manual=True)
            await self.refresh_transfers()
        except Exception as ex:
            self.notify(f"跨 shard 转账失败：{ex}", type="negative")

    async def do_create_subaccount(self) -> None:
        shard = self.new_sub_shard.value
        shard = None if shard is None or shard == "" else int(shard)
        if not await self.confirm("创建一个新的子账户？" + (f"（shard {shard}）" if shard is not None else "")):
            return
        try:
            r = await run.io_bound(lambda: self.api.create_subaccount(shard))
            ui.notify(f"子账户已创建：{r}", type="positive")
            await self.refresh_all(manual=True)
        except Exception as ex:
            ui.notify(f"创建子账户失败：{ex}", type="negative")


@ui.page("/")
def _index() -> None:
    DeskUI().start()


def _pick_port(start: int = 8090) -> int:
    """优先用环境变量 KALSHI_DESK_PORT，否则从 8090 起找一个空闲端口。"""
    env = os.environ.get("KALSHI_DESK_PORT", "").strip()
    if env:
        return int(env)
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def main() -> None:
    app.on_shutdown(ws.stop_all)
    ui.run(title="Kalshi 交易工作台", host="0.0.0.0", port=_pick_port(), dark=True,
           reload=False, show=True,reconnect_timeout=1200)
