"""Runs the Vectana MCP server (Node, mcp/) in HTTP mode next to the API, so
/mcp can be offered as a remote MCP endpoint. Started from the API's lifespan
when MCP_SCRIPT points at the built server (the Docker image sets it)."""

import asyncio
import contextlib
import logging
import os
import shutil
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("vectana.mcp")


def enabled() -> bool:
    return bool(settings.mcp_script) and Path(settings.mcp_script).is_file()


async def _run_forever() -> None:
    node = shutil.which(settings.mcp_node) or settings.mcp_node
    env = {
        **os.environ,
        "VECTANA_URL": settings.mcp_api_url,
        "VECTANA_MCP_HOST": "127.0.0.1",
        "VECTANA_MCP_PORT": str(settings.mcp_port),
    }
    delay = 1.0
    while True:
        try:
            proc = await asyncio.create_subprocess_exec(
                node, settings.mcp_script, "--http", env=env
            )
        except OSError as e:
            logger.error("cannot start the MCP server: %s", e)
            return
        try:
            code = await proc.wait()
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                proc.terminate()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(proc.wait(), 5)
            raise
        logger.warning("MCP server exited with %s; restarting in %.0fs", code, delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 60)


@contextlib.asynccontextmanager
async def running():  # type: ignore[no-untyped-def]
    if not enabled():
        yield
        return
    task = asyncio.create_task(_run_forever())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
