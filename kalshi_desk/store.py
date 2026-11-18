# -*- coding: utf-8 -*-
"""PEM 私钥与登录会话的本地持久化。

存放位置：
- 打包运行（exe）：可执行文件同级 data/ 目录（便携，拷走 exe+data 即可迁移）
- 源码运行：工程根 data/ 目录
data/ 已在 .gitignore 中，*.pem 也被忽略。
"""
from __future__ import annotations

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from cryptography.hazmat.primitives import serialization


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    return Path(__file__).resolve().parent.parent / "data"


DATA_DIR = _data_dir()
PEM_PATH = DATA_DIR / "key.pem"
SESSION_PATH = DATA_DIR / "session.json"
CONFIG_PATH = DATA_DIR / "config.json"

PROXY_DEFAULT = {
    "enabled": False,
    "host": "127.0.0.1",
    "port": 1080,
    "username": "",
    "password": "",
}
AUTH_DEFAULT = {"username": "admin", "password": "admin"}
REFRESH_DEFAULT = 60  # 自动刷新间隔（秒）
USERS_DEFAULT = [{"username": "admin", "password": "admin", "role": "admin"}]
AI_DEFAULT = {
    "providers": [{
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "model": "gpt-4o-mini",
    }],
    "active": 0,
}
# 动量机器人默认配置
# series: 监控的系列列表（如 KXBTC15M）。每个系列下当前活跃的市场 ticker
#         由系统自动发现（通常 2~3 个：当前场 + 下一场），永不手填。
MO_DEFAULT = {
    "enabled": False,
    "series": ["KXBTC15M"],       # 监控系列（默认只有 BTC 15 分钟）
    "category": "Crypto",         # 仅用于过滤系列下拉的品类
    "min_delta": 0.01,
    "min_strength": "中",
    "scan_interval": 5,
    "taker_interval": 60,
    "qty": 1,
    "tp_mult": 1.10,
    "buy_tif": "immediate_or_cancel",
    "subaccount": 0,
    "max_parallel": 3,
    "stop_loss": 0.00,
    "cancel_sec": 30,              # 买单/止盈单超过该秒数未成交即撤单
    "tp_cf_boost": False,          # 是否参考 CF 指数与水位线（strike）差值动态放大止盈
    "tp_cf_max": 1.10,             # 动态止盈倍率上限
    "frac_start": 0.1333,          # 市场生命周期进度下限（15 分钟市场≈第 2 分钟）
    "frac_end": 0.9333,            # 市场生命周期进度上限（15 分钟市场≈结束前 1 分钟）
}


# ================= 代理配置 =================
def load_config() -> dict:
    """读取本地配置（代理、登录账户等），缺失时返回默认值。"""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            cfg = {}
    except (OSError, ValueError):
        cfg = {}
    proxy = dict(PROXY_DEFAULT)
    saved = cfg.get("proxy")
    if isinstance(saved, dict):
        proxy.update({k: saved[k] for k in PROXY_DEFAULT if k in saved})
    cfg["proxy"] = proxy
    auth = dict(AUTH_DEFAULT)
    saved = cfg.get("auth")
    if isinstance(saved, dict):
        auth.update({k: saved[k] for k in AUTH_DEFAULT if saved.get(k)})
    cfg["auth"] = auth
    cfg["users"] = _normalize_users(cfg.get("users"), auth)
    cfg["ai"] = _normalize_ai(cfg.get("ai"))
    cfg["momentum"] = _normalize_mo(cfg.get("momentum"))
    try:
        seconds = int(cfg.get("refresh_interval") or REFRESH_DEFAULT)
    except (TypeError, ValueError):
        seconds = REFRESH_DEFAULT
    cfg["refresh_interval"] = min(max(seconds, 5), 3600)
    return cfg


def _normalize_mo(mo) -> dict:
    d = dict(MO_DEFAULT)
    if isinstance(mo, dict):
        for k, v in mo.items():
            if k in d:
                d[k] = v
    # series 必须是字符串列表；旧配置没有 series 就用默认 KXBTC15M
    if not isinstance(d.get("series"), list):
        d["series"] = list(MO_DEFAULT["series"])
    d["series"] = [str(s).strip().upper() for s in d["series"] if str(s).strip()]
    if not d["series"]:
        d["series"] = list(MO_DEFAULT["series"])
    # 数值字段兜底
    for key in ("min_delta", "scan_interval", "taker_interval", "qty",
                "tp_mult", "subaccount", "max_parallel", "stop_loss",
                "cancel_sec", "tp_cf_max", "frac_start", "frac_end"):
        try:
            d[key] = float(d[key])
        except (TypeError, ValueError):
            d[key] = MO_DEFAULT[key]
    d["qty"] = max(1, int(d["qty"]))
    d["scan_interval"] = max(2, int(d["scan_interval"]))
    d["taker_interval"] = max(0, int(d["taker_interval"]))
    d["max_parallel"] = max(1, int(d["max_parallel"]))
    d["cancel_sec"] = max(3, min(600, int(d["cancel_sec"])))
    d["tp_mult"] = max(1.01, min(3.0, d["tp_mult"]))
    d["tp_cf_boost"] = bool(d.get("tp_cf_boost"))
    d["tp_cf_max"] = max(d["tp_mult"], min(3.0, d["tp_cf_max"]))
    d["frac_start"] = max(0.0, min(0.99, d["frac_start"]))
    d["frac_end"] = max(d["frac_start"], min(1.0, d["frac_end"]))
    d["min_strength"] = str(d["min_strength"]) if d["min_strength"] in ("弱", "中", "强") else "中"
    d["buy_tif"] = "good_till_canceled" if d["buy_tif"] == "good_till_canceled" else "immediate_or_cancel"
    d["category"] = str(d["category"] or "")
    return d


def save_momentum(mo: dict) -> None:
    """持久化动量机器人配置到 config.json。"""
    cfg = load_config()
    cfg["momentum"] = _normalize_mo(mo)
    try:
        CONFIG_PATH.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as ex:
        raise RuntimeError(f"保存配置失败：{ex}") from ex


def _normalize_users(users, legacy_auth: dict) -> list:
    """用户列表归一化；老配置里只有 auth 时迁移成管理员账户。"""
    out = []
    if isinstance(users, list):
        for u in users:
            if not isinstance(u, dict):
                continue
            name = str(u.get("username") or "").strip()
            if not name:
                continue
            out.append({
                "username": name,
                "password": str(u.get("password") or ""),
                "role": "admin" if u.get("role") == "admin" else "viewer",
            })
    if not out:
        out = [{"username": legacy_auth["username"],
                "password": legacy_auth["password"], "role": "admin"}]
    if not any(u["role"] == "admin" for u in out):
        out[0]["role"] = "admin"
    return out


def _normalize_ai(ai) -> dict:
    providers = []
    if isinstance(ai, dict) and isinstance(ai.get("providers"), list):
        for p in ai["providers"]:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            if not name:
                continue
            providers.append({
                "name": name,
                "base_url": str(p.get("base_url") or "").strip().rstrip("/"),
                "api_key": str(p.get("api_key") or ""),
                "model": str(p.get("model") or "").strip(),
            })
    if not providers:
        providers = [dict(AI_DEFAULT["providers"][0])]
    try:
        active = int((ai or {}).get("active") or 0)
    except (TypeError, ValueError):
        active = 0
    return {"providers": providers, "active": min(max(active, 0), len(providers) - 1)}


def save_refresh_interval(seconds: int) -> int:
    """保存自动刷新间隔（5 ~ 3600 秒），返回生效值。"""
    try:
        value = int(seconds)
    except (TypeError, ValueError):
        raise ValueError("刷新间隔必须是整数秒")
    if not (5 <= value <= 3600):
        raise ValueError("刷新间隔需在 5 ~ 3600 秒之间")
    cfg = load_config()
    cfg["refresh_interval"] = value
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


def load_users() -> list:
    return load_config()["users"]


def save_users(users: list) -> list:
    """保存用户列表：用户名唯一、密码非空、至少保留一个 admin。"""
    cleaned = []
    seen = set()
    for u in users or []:
        name = str((u or {}).get("username") or "").strip()
        pwd = str((u or {}).get("password") or "")
        role = "admin" if (u or {}).get("role") == "admin" else "viewer"
        if not name:
            raise ValueError("用户名不能为空")
        if not pwd:
            raise ValueError(f"用户 {name} 的密码不能为空")
        if name in seen:
            raise ValueError(f"用户名重复：{name}")
        seen.add(name)
        cleaned.append({"username": name, "password": pwd, "role": role})
    if not cleaned:
        raise ValueError("至少需要保留一个用户")
    if not any(u["role"] == "admin" for u in cleaned):
        raise ValueError("至少需要保留一个管理员（admin 权限）用户")
    cfg = load_config()
    cfg["users"] = cleaned
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return cleaned


def check_login(username: str, password: str) -> Optional[dict]:
    """校验工作台账户，成功返回用户记录（含 role），失败返回 None。"""
    name = (username or "").strip()
    for u in load_config()["users"]:
        if u["username"] == name and u["password"] == (password or ""):
            return u
    return None


def save_ai(providers: list, active: int = 0) -> dict:
    """保存 AI 服务商配置（OpenAI 兼容接口）。"""
    cfg = load_config()
    cfg["ai"] = _normalize_ai({"providers": providers, "active": active})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return cfg["ai"]


def save_proxy(proxy: dict) -> dict:
    """保存 SOCKS5 代理配置，返回归一化后的配置。

    校验失败抛 ValueError；密码属于敏感信息，同 PEM 一样只留在本机 data/。
    """
    p = dict(PROXY_DEFAULT)
    p.update({k: (proxy or {}).get(k, p[k]) for k in PROXY_DEFAULT})
    p["enabled"] = bool(p["enabled"])
    p["host"] = str(p.get("host") or "").strip()
    p["username"] = str(p.get("username") or "").strip()
    p["password"] = str(p.get("password") or "")
    try:
        p["port"] = int(p.get("port") or 0)
    except (TypeError, ValueError):
        raise ValueError("代理端口必须是数字")
    if p["enabled"]:
        if not p["host"]:
            raise ValueError("代理地址不能为空")
        if not (0 < p["port"] < 65536):
            raise ValueError("代理端口需在 1 ~ 65535 之间")

    cfg = load_config()
    cfg["proxy"] = p
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    return p


def proxy_url(proxy: Optional[dict] = None) -> Optional[str]:
    """把代理配置转成 requests 可用的 URL；未启用返回 None。

    使用 socks5h：域名交给代理端解析，避免本机 DNS 污染 / 无法解析。
    """
    p = proxy if proxy is not None else load_config()["proxy"]
    if not p or not p.get("enabled"):
        return None
    host = str(p.get("host") or "").strip()
    if not host:
        return None
    try:
        port = int(p.get("port") or 1080)
    except (TypeError, ValueError):
        port = 1080
    auth = ""
    if p.get("username"):
        auth = quote(str(p["username"]), safe="")
        if p.get("password"):
            auth += ":" + quote(str(p["password"]), safe="")
        auth += "@"
    if ":" in host and not host.startswith("["):  # IPv6
        host = f"[{host}]"
    return f"socks5h://{auth}{host}:{port}"


_PEM_KEYS = ("private_key", "privateKey", "pem", "key", "secret", "value", "content")


def _to_text(data) -> str:
    """bytes / str 统一成文本（容忍 UTF-8 BOM 与 Windows 换行）。"""
    if isinstance(data, str):
        return data
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return data.decode("latin-1", "ignore")


def _clean_pem_text(text: str) -> str:
    """归一化常见非标准 PEM：BOM、JSON 包装、字面量 \\n、外层引号。"""
    t = (text or "").strip().lstrip("\ufeff").strip()
    if t.startswith("{"):  # Kalshi / 配置文件里的 {"private_key": "-----BEGIN..."}
        try:
            obj = json.loads(t)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            for k in _PEM_KEYS:
                v = obj.get(k)
                if isinstance(v, str) and "PRIVATE KEY" in v:
                    return _clean_pem_text(v)
    if "\\n" in t and "\n" not in t:  # 整段写成了一行：-----\nMIIE...
        t = t.replace("\\r\\n", "\n").replace("\\n", "\n")
    if t[:1] in ("'", '"'):
        t = t.strip("\"'").strip()
    return t


def _pem_hint(text: str) -> str:
    """给出可操作的中文错误提示。"""
    t = (text or "").strip()
    head = t.splitlines()[0][:60] if t else ""
    if not head:
        return "文件为空，请重新选择私钥文件"
    if head.lstrip().startswith("<"):
        return "文件内容是 HTML 网页，不是私钥；请确认下载的是 .pem 私钥文件"
    if "BEGIN" not in t:
        return ("不是 PEM 私钥（缺少 -----BEGIN ... PRIVATE KEY----- 头）。"
                f"首行：{head}")
    return "PEM 结构不完整或不是私钥，请重新从 Kalshi 下载私钥文件"


def _load_key(data):
    """解析私钥，返回 (私钥对象, 标准 PEM 文本)。

    依次兼容：标准 PEM / JSON 包装 / 单行转义换行 / 裸 DER 与 base64。
    """
    text = _clean_pem_text(_to_text(data))
    if "-----BEGIN" in text:
        try:
            return serialization.load_pem_private_key(text.encode("utf-8"), password=None), text
        except TypeError as ex:  # 私钥带密码
            raise ValueError("私钥已加密，请提供未加密的 PEM 私钥文件") from ex
        except ValueError as ex:
            raise ValueError(_pem_hint(text)) from ex

    candidates = []
    body = "".join(text.split())
    if body and not text.startswith(("<", "{", "[")):
        try:  # 纯 base64 的 DER（常见于手工复制的密钥）
            candidates.append(base64.b64decode(body, validate=True))
        except (ValueError, TypeError):
            pass
    if isinstance(data, bytes) and not text.startswith(("<", "{", "[")):
        candidates.append(data)
    for der in candidates:
        try:
            key = serialization.load_der_private_key(der, password=None)
            pem = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ).decode("utf-8")
            return key, pem
        except Exception:
            continue
    raise ValueError(_pem_hint(text))


def normalize_pem(data) -> str:
    """把上传内容归一化为标准 PEM 文本；无法识别时抛 ValueError。"""
    return _load_key(data)[1]


def validate_pem(pem_text) -> None:
    """校验私钥可用，失败抛异常（兼容 str / bytes / 非标准 PEM 写法）。"""
    _load_key(pem_text)


def stage_pem(pem_text: str) -> Path:
    """把待验证的私钥写到临时文件（验证连接成功后再落正式会话）。"""
    pem_text = normalize_pem(pem_text)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "staged.pem"
    path.write_text(pem_text.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def _pem_for(env: str) -> Path:
    return DATA_DIR / f"key_{env or 'prod'}.pem"


def _read_sessions() -> dict:
    """读取全部环境的会话，兼容老的单会话格式。"""
    try:
        data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    sessions = data.get("sessions")
    if isinstance(sessions, dict) and sessions:
        return {k: v for k, v in sessions.items() if isinstance(v, dict)}
    if data.get("key_id") and data.get("pem_path"):
        env = data.get("env") if data.get("env") in ("prod", "demo") else "prod"
        return {env: data}
    return {}


def save_session(key_id: str, pem_text: str, env: str) -> dict:
    key_id = (key_id or "").strip()
    if not key_id:
        raise ValueError("API Key ID 不能为空")
    if not (pem_text or "").strip():
        raise ValueError("PEM 文件内容为空")
    pem_text = normalize_pem(pem_text)
    env = env if env in ("prod", "demo") else "prod"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    pem = _pem_for(env)
    pem.write_text(pem_text.strip() + "\n", encoding="utf-8")
    try:
        os.chmod(pem, 0o600)
    except OSError:
        pass

    sess = {
        "key_id": key_id,
        "env": env,
        "pem_path": str(pem),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    sessions = _read_sessions()
    sessions[env] = sess
    payload = {"sessions": sessions, "last_env": env}
    SESSION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    try:
        os.chmod(SESSION_PATH, 0o600)
    except OSError:
        pass
    return sess


def load_session(env: Optional[str] = None) -> Optional[dict]:
    """读取指定环境的会话；不传 env 时返回上次使用的环境。"""
    sessions = _read_sessions()
    if env:
        sess = sessions.get(env)
    else:
        try:
            last = json.loads(SESSION_PATH.read_text(encoding="utf-8")).get("last_env")
        except (OSError, ValueError, AttributeError):
            last = None
        sess = sessions.get(last or "") or next(iter(sessions.values()), None)
    if not sess:
        return None
    pem = Path(sess.get("pem_path") or PEM_PATH)
    if not pem.exists():
        return None
    if sess.get("env") not in ("prod", "demo"):
        sess = {**sess, "env": "prod"}
    return sess


def save_last_env(env: str) -> None:
    """记录最近使用的环境，供下次启动自动连接。"""
    payload = {"sessions": _read_sessions(),
               "last_env": env if env in ("prod", "demo") else "prod"}
    SESSION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def clear_session() -> None:
    for p in (PEM_PATH, SESSION_PATH, DATA_DIR / "staged.pem",
              _pem_for("prod"), _pem_for("demo")):
        try:
            p.unlink()
        except OSError:
            pass


def mask_key(key_id: str) -> str:
    k = key_id or ""
    if len(k) <= 10:
        return k
    return f"{k[:6]}…{k[-4:]}"
