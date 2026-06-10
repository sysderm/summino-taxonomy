"""Shared utilities for Phase 1.0 harvest parsers.

Every parser imports from here so the normalized output schema, HTTP manners
(polite User-Agent, retry on transient failure), and logging are identical
across sources.

Normalized raw schema written to raw/<source>.json:

    {
      "source": "<slug>",
      "version": "<source_version_or_date>",
      "harvested_at": "<iso8601>",
      "node_count": <int>,
      "nodes": [
        {"id", "name", "parents": [...], "aliases": [...],
         "definition": null|str, "extras": {...}}
      ]
    }
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

# --- paths -----------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "raw"
LOG_DIR = REPO_ROOT / "log"
RAW_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# --- manners ---------------------------------------------------------------
USER_AGENT = "summino-taxonomy/1.0 (alexander.navarini@gmail.com)"
DEFAULT_HEADERS = {"User-Agent": USER_AGENT}

# Exceptions worth retrying: network errors, timeouts, and 5xx (raised by
# response.raise_for_status() as HTTPStatusError -- we re-raise only on 5xx).
TRANSIENT = (httpx.TransportError, httpx.TimeoutException)


def get_logger(source: str) -> logging.Logger:
    """A logger that writes to both stdout and log/harvest-<source>.log."""
    logger = logging.getLogger(f"harvest.{source}")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    fh = logging.FileHandler(LOG_DIR / f"harvest-{source}.log", mode="w")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def make_client(timeout: float = 60.0, **kwargs: Any) -> httpx.Client:
    headers = dict(DEFAULT_HEADERS)
    headers.update(kwargs.pop("headers", {}))
    return httpx.Client(
        headers=headers,
        timeout=timeout,
        follow_redirects=True,
        **kwargs,
    )


def _is_retryable_status(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def fetch(
    client: httpx.Client,
    url: str,
    logger: logging.Logger,
    *,
    method: str = "GET",
    **kwargs: Any,
) -> httpx.Response:
    """GET/POST with up to 3 retries on transient (network/timeout/5xx)."""

    @retry(
        retry=(
            retry_if_exception_type(TRANSIENT)
            | retry_if_exception_type(httpx.HTTPStatusError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _do() -> httpx.Response:
        resp = client.request(method, url, **kwargs)
        # Only retry server errors; 4xx are permanent (auth walls, not-found).
        if resp.status_code >= 500:
            resp.raise_for_status()
        return resp

    return _do()


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def normalize_node(
    id: str,
    name: str,
    parents: Iterable[str] | None = None,
    aliases: Iterable[str] | None = None,
    definition: str | None = None,
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(id),
        "name": name,
        "parents": list(parents or []),
        "aliases": list(aliases or []),
        "definition": definition,
        "extras": extras or {},
    }


def write_raw(
    source: str,
    version: str,
    nodes: list[dict[str, Any]],
    logger: logging.Logger,
) -> Path:
    """Write the normalized snapshot idempotently (overwrites)."""
    payload = {
        "source": source,
        "version": version,
        "harvested_at": now_iso(),
        "node_count": len(nodes),
        "nodes": nodes,
    }
    out = RAW_DIR / f"{source}.json"
    tmp = out.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1, sort_keys=False)
    tmp.replace(out)
    logger.info("wrote %s (%d nodes, version=%s)", out, len(nodes), version)
    return out


class SkipSource(Exception):
    """Raised by a parser when a source must be skipped (e.g. auth wall).

    The orchestrator treats this as a non-fatal skip, not a failure.
    """


def run_parser(source: str, fn: Callable[[logging.Logger], Any]) -> int:
    """Wrap a parser main(): handle SkipSource, log exceptions, set exit code."""
    logger = get_logger(source)
    try:
        fn(logger)
        return 0
    except SkipSource as e:
        logger.warning("SKIPPED %s: %s", source, e)
        # Exit 0 on skip -- orchestrator distinguishes via raw file presence.
        return 0
    except Exception:  # noqa: BLE001 -- top-level parser boundary
        logger.exception("FAILED %s", source)
        return 1
