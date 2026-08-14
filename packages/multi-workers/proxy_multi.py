"""
proxy_multi.py — Multi-provider LLM proxy.

Starts independent LocalProxyServer instances on separate ports for each
worker CLI type. Managed by mw serve; do not run directly in production.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time

from timi_proxy_cli.config import DEFAULT_MODEL_MAP
from timi_proxy_cli.proxy import LocalProxyServer

# Default upstream: timi proxy (same as timi-proxy-cli defaults)
_DEFAULT_UPSTREAM_HOST = os.environ.get("MW_UPSTREAM_HOST", "api.timiai.woa.com")
_DEFAULT_UPSTREAM_PORT = int(os.environ.get("MW_UPSTREAM_PORT", "80"))
_DEFAULT_UPSTREAM_BASE_PATH = os.environ.get(
    "MW_UPSTREAM_BASE_PATH", "/ai_api_manage/llmproxy"
)

def _make_proxy(bind_port: int, upstream_host: str, upstream_port: int, upstream_base_path: str) -> LocalProxyServer:
    return LocalProxyServer(
        bind_host="127.0.0.1",
        bind_port=bind_port,
        upstream_host=upstream_host,
        upstream_port=upstream_port,
        upstream_base_path=upstream_base_path,
        model_map=DEFAULT_MODEL_MAP,
        unsupported_params=[],
        logger=None,
    )


def run(pi_port: int, claude_port: int, deepseek_port: int | None = None) -> None:
    """Start proxy servers and block until interrupted."""
    pi_proxy = _make_proxy(
        pi_port,
        _DEFAULT_UPSTREAM_HOST,
        _DEFAULT_UPSTREAM_PORT,
        _DEFAULT_UPSTREAM_BASE_PATH,
    )
    claude_proxy = _make_proxy(
        claude_port,
        _DEFAULT_UPSTREAM_HOST,
        _DEFAULT_UPSTREAM_PORT,
        _DEFAULT_UPSTREAM_BASE_PATH,
    )

    proxies = [pi_proxy, claude_proxy]
    status_parts = [f"pi={pi_port}", f"claude-cli={claude_port}"]

    if deepseek_port is not None:
        deepseek_proxy = _make_proxy(
            deepseek_port,
            _DEFAULT_UPSTREAM_HOST,
            _DEFAULT_UPSTREAM_PORT,
            _DEFAULT_UPSTREAM_BASE_PATH,
        )
        proxies.append(deepseek_proxy)
        status_parts.append(f"deepseek={deepseek_port}")

    for p in proxies:
        p.start()

    print(f"[proxy_multi] listening: {' '.join(status_parts)}", flush=True)

    stop_event = threading.Event()

    def _shutdown(signum: int, frame: object) -> None:  # noqa: ARG001
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    if sys.platform != "win32":
        signal.signal(signal.SIGINT, _shutdown)

    try:
        while not stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in proxies:
            p.stop()
        print("[proxy_multi] stopped", flush=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-provider LLM proxy")
    parser.add_argument("--pi-port", type=int, default=7001)
    parser.add_argument("--claude-port", type=int, default=7003)
    parser.add_argument("--deepseek-port", type=int, default=None)
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.pi_port, args.claude_port, args.deepseek_port)
