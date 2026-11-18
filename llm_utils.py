"""
LLM 调用基础设施：日志、重试、错误分类。

仅依赖标准库，便于独立测试：
  - get_logger()      返回带 RotatingFileHandler 的 logger，写 logs/agent.log
  - with_retry()      指数退避重试，只重试"可恢复"错误（限流/网络/5xx）
  - classify_error()  把异常翻译成给最终用户看的中文提示
"""
import logging
import os
import time
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "agent"
_setup_done = False


def get_logger():
    """获取全局 agent logger（幂等，重复调用返回同一实例）"""
    global _setup_done
    logger = logging.getLogger(LOGGER_NAME)
    if _setup_done:
        return logger

    logger.setLevel(logging.INFO)
    if not logger.handlers:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)

        # 文件：INFO 全量，1MB × 3 轮转，UTF-8
        fh = RotatingFileHandler(
            os.path.join(log_dir, "agent.log"),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)

        # 控制台：只显示 WARNING 以上，避免刷屏
        sh = logging.StreamHandler()
        sh.setLevel(logging.WARNING)
        sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(sh)

    _setup_done = True
    return logger


# ---- 重试策略 ----

# 这些错误重试没有意义（密钥错、模型名错、参数错）
_NON_RETRYABLE = {
    "AuthenticationError",
    "PermissionDeniedError",
    "BadRequestError",
    "NotFoundError",
    "UnprocessableEntityError",
}
# 这些错误名明确可重试（openai SDK 的异常类名）
_RETRYABLE_NAMES = {
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
}


def is_retryable(exc):
    """判断异常是否值得重试（基于异常类名与 HTTP 状态码，不依赖 openai 包）"""
    name = type(exc).__name__
    if name in _NON_RETRYABLE:
        return False
    if name in _RETRYABLE_NAMES:
        return True
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status == 429 or status >= 500
    # 底层网络异常
    return isinstance(exc, (ConnectionError, TimeoutError))


def with_retry(fn, *args, retries=3, base_delay=1.0, logger=None, **kwargs):
    """
    执行 fn(*args, **kwargs)，遇到可重试错误则指数退避：
    第 1 次失败等 1s，第 2 次等 2s，第 3 次等 4s…（最多 retries 次尝试）。
    不可重试的错误立即抛出。
    """
    last_exc = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if not is_retryable(e) or attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            if logger:
                logger.warning(
                    "调用失败(第%d/%d次) %s: %s，%.1fs 后重试",
                    attempt + 1, retries, type(e).__name__, e, delay,
                )
            time.sleep(delay)
    raise last_exc  # 理论上不可达


# ---- 错误分类（面向最终用户） ----

def classify_error(exc):
    """把异常翻译成给用户看的中文提示，附带下一步该做什么"""
    name = type(exc).__name__
    if name in ("AuthenticationError", "PermissionDeniedError"):
        return "🔑 API Key 无效或无权限，请检查 `.env` 中的 `LLM_API_KEY` 后重启应用。"
    if name == "RateLimitError":
        return "🚦 请求太频繁或额度已用尽，请稍后再试。"
    if name in ("APIConnectionError", "APITimeoutError", "TimeoutError", "ConnectionError", "OSError"):
        return "🌐 网络连接超时，请检查网络后重试。"
    if name == "NotFoundError":
        return "🔍 模型名不存在，请检查 `.env` 中的 `LLM_MODEL` 配置。"
    if name in ("BadRequestError", "UnprocessableEntityError"):
        return f"⚠️ 请求被模型服务拒绝：{exc}"
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status >= 500:
        return "🛠 模型服务端暂时故障，请稍后重试。"
    return f"⚠️ 调用出错：{exc}"
