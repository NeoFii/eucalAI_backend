"""
日志工具模块
提供统一的日志配置和记录功能
"""

import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from typing import Any, Dict, Optional

from app.config import settings


class ColoredFormatter(logging.Formatter):
    """带颜色的日志格式化器（控制台输出）"""

    # 颜色代码
    COLORS = {
        "DEBUG": "\033[36m",  # 青色
        "INFO": "\033[32m",  # 绿色
        "WARNING": "\033[33m",  # 黄色
        "ERROR": "\033[31m",  # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录"""
        # 添加颜色
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        return super().format(record)


class SensitiveDataFilter(logging.Filter):
    """敏感信息过滤过滤器"""

    # 需要过滤的敏感字段
    SENSITIVE_FIELDS = {
        "password",
        "pwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "code",
        "verification_code",
        "smtp_password",
        "jwt_secret_key",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤敏感信息"""
        if hasattr(record, "msg"):
            msg = str(record.msg)
            for field in self.SENSITIVE_FIELDS:
                # 替换敏感字段值
                import re

                # 匹配 password=xxx, "password": "xxx" 等模式
                msg = re.sub(
                    rf'({field})["\']?\s*[:=]\s*["\']?([^"\'\s,]*)["\']?',
                    rf'\1=***',
                    msg,
                    flags=re.IGNORECASE,
                )
            record.msg = msg
        return True


def get_log_level(level: str = None) -> int:
    """获取日志级别"""
    level = level or settings.LOG_LEVEL
    return getattr(logging, level.upper(), logging.INFO)


def setup_logger(
    name: str = None,
    log_file: str = None,
    level: int = None,
    console: bool = True,
) -> logging.Logger:
    """
    配置日志记录器

    Args:
        name: 日志记录器名称
        log_file: 日志文件名（不含路径）
        level: 日志级别
        console: 是否输出到控制台

    Returns:
        配置好的日志记录器
    """
    global _loggers_initialized

    logger = logging.getLogger(name or __name__)

    # 热重载时如果已经初始化过，跳过重新配置
    if _loggers_initialized and logger.handlers:
        return logger

    # 清除已有的处理器（防止重复）
    logger.handlers.clear()
    logger.setLevel(level or get_log_level())

    # 确保日志目录存在
    log_dir = settings.LOG_DIR
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    # 日志格式
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件日志处理器（按天轮转）
    if log_file and log_dir:
        file_path = os.path.join(log_dir, log_file)
        file_handler = TimedRotatingFileHandler(
            filename=file_path,
            when="midnight",
            interval=1,
            backupCount=settings.LOG_MAX_DAYS,
            encoding="utf-8",
        )
        file_handler.setLevel(get_log_level())
        # 文件日志使用普通格式化器（无颜色）
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(SensitiveDataFilter())
        logger.addHandler(file_handler)

    # 控制台日志处理器
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(get_log_level())
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(SensitiveDataFilter())
        logger.addHandler(console_handler)

    # 标记已初始化，防止热重载时重复配置
    _loggers_initialized = True

    return logger


def get_logger(name: str = None) -> logging.Logger:
    """
    获取日志记录器的便捷方法

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器
    """
    # 避免重复创建
    logger = logging.getLogger(name or __name__)
    if not logger.handlers:
        return setup_logger(name=name)
    return logger


# 标记日志是否已初始化（防止热重载时重复配置）
_loggers_initialized = False

# 预定义的日志记录器
# 应用主日志
app_logger = get_logger("app")
app_logger.propagate = False  # 不传播到根日志

# 访问日志
access_logger = get_logger("access")
access_logger.propagate = False  # 不传播到根日志
# 错误日志
error_logger = get_logger("error")
error_logger.propagate = False


def log_access(
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration: float,
    ip: str = None,
    user_agent: str = None,
) -> None:
    """
    记录访问日志

    Args:
        request_id: 请求ID
        method: HTTP 方法
        path: 请求路径
        status_code: 响应状态码
        duration: 请求耗时（毫秒）
        ip: 客户端IP
        user_agent: 用户代理
    """
    log_data = {
        "request_id": request_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration, 2),
        "ip": ip,
        "user_agent": user_agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    access_logger.info(f"访问日志: {log_data}")


def log_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    记录错误日志

    Args:
        error: 异常对象
        context: 额外的上下文信息
    """
    error_msg = f"错误: {type(error).__name__} - {str(error)}"
    if context:
        error_msg += f" | 上下文: {context}"
    error_logger.error(error_msg, exc_info=True)
