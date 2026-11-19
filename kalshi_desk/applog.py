# -*- coding: utf-8 -*-
"""动量机器人的文件日志。

测试期要回答「为什么一单不下」，所以每次扫描的决策都必须落文件：
  data/logs/momentum.log（10MB × 5 轮转，同时回显到控制台）

不依赖 DuckDB：数据库锁、面板刷新异常都不会让日志消失。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .store import DATA_DIR

LOG_DIR = DATA_DIR / "logs"
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP = 5
_ready = False


def setup(level: int = logging.INFO) -> logging.Logger:
    """初始化 kalshi 日志器（幂等），返回 logger。"""
    global _ready
    log = logging.getLogger("kalshi")
    if _ready:
        return log
    fmt = logging.Formatter("%(asctime)s %(levelname)-5s %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(LOG_DIR / "momentum.log", maxBytes=_MAX_BYTES,
                                 backupCount=_BACKUP, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
    except OSError:
        pass  # 目录不可写时至少还有控制台
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    log.addHandler(sh)
    log.setLevel(level)
    log.propagate = False
    _ready = True
    return log


def mo() -> logging.Logger:
    return setup()
