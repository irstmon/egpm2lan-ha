"""EG-PM2-LAN Coordinator - asyncio queue daemon.

All device communication is strictly serialized:
    Login -> Action (optional) -> Status -> Logout

Only one session is ever open at a time. A mandatory cooldown between
operations prevents the device from crashing on rapid successive requests.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_INTER_OP_DELAY, DEFAULT_TIMEOUT, DOMAIN, NUMBER_OF_SOCKETS

_LOGGER = logging.getLogger(__name__)

SocketStates = dict[int, bool]


class EGPMCoordinator(DataUpdateCoordinator[SocketStates]):
    """Manages all communication with the EG-PM2-LAN power strip.

    A single background task (_daemon_loop) processes one operation at a time
    from an asyncio.Queue. HA polling and switch entities both enqueue their
    requests and await the result via asyncio.Future - no race conditions,
    no overlapping sessions, guaranteed Login->Action->Logout per operation.

    A mandatory cooldown of DEFAULT_INTER_OP_DELAY seconds is enforced after
    every operation to prevent the device from crashing on rapid requests.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        ip: str,
        password: str,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._ip = ip
        self._password = password
        self._queue: asyncio.Queue = asyncio.Queue()
        self._daemon_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Daemon lifecycle
    # ------------------------------------------------------------------

    def start_daemon(self) -> None:
        """Start the serial queue processor as a HA background task."""
        self._daemon_task = self.hass.async_create_background_task(
            self._daemon_loop(),
            name=f"{DOMAIN}_daemon",
        )
        _LOGGER.debug("EGPM2LAN daemon started")

    def stop_daemon(self) -> None:
        """Stop the daemon cleanly on integration unload."""
        if self._daemon_task and not self._daemon_task.done():
            self._daemon_task.cancel()
            self._daemon_task = None
        _LOGGER.debug("EGPM2LAN daemon stopped")

    async def _daemon_loop(self) -> None:
        """Serial queue processor - runs until cancelled."""
        while True:
            try:
                operation, future = await self._queue.get()
            except asyncio.CancelledError:
                break

            if future.cancelled():
                self._queue.task_done()
                continue

            try:
                result = await self._execute(operation)
                if not future.done():
                    future.set_result(result)
            except Exception as exc:  # noqa: BLE001
                _LOGGER.error(
                    "EGPM2LAN operation '%s' failed: %s",
                    operation.get("type"),
                    exc,
                )
                if not future.done():
                    future.set_exception(exc)
            finally:
                self._queue.task_done()

            # Mandatory cooldown - device crashes if requests arrive too fast.
            # Runs AFTER logout is complete and task_done(), BEFORE the next
            # operation is dequeued. Applies to all operation types.
            _LOGGER.debug(
                "EGPM2LAN: cooldown %ds before next operation",
                DEFAULT_INTER_OP_DELAY,
            )
            await asyncio.sleep(DEFAULT_INTER_OP_DELAY)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> SocketStates:
        """Called by HA polling timer - routed through the queue."""
        try:
            return await self._enqueue({"type": "status"})
        except Exception as exc:
            raise UpdateFailed(f"Status poll failed: {exc}") from exc

    async def async_switch_socket(self, socket_nr: int, turn_on: bool) -> None:
        """Switch one socket and immediately push fresh state to all entities.

        Flow: Login -> Switch POST -> Read Status -> Logout
        Result is pushed via async_set_updated_data so all 4 entities
        update at once without waiting for the next poll interval.
        """
        new_states = await self._enqueue(
            {"type": "switch", "socket": socket_nr, "state": 1 if turn_on else 0}
        )
        self.async_set_updated_data(new_states)

    # ------------------------------------------------------------------
    # Queue helper
    # ------------------------------------------------------------------

    async def _enqueue(self, operation: dict) -> SocketStates:
        """Put an operation in the queue and await its result."""
        future: asyncio.Future = self.hass.loop.create_future()
        await self._queue.put((operation, future))
        return await future

    # ------------------------------------------------------------------
    # Device communication - always: Login -> [Action] -> Status -> Logout
    # ------------------------------------------------------------------

    async def _execute(self, operation: dict) -> SocketStates:
        """Execute one operation inside a single fresh session."""
        timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
        jar = aiohttp.CookieJar(unsafe=True)

        async with aiohttp.ClientSession(cookie_jar=jar, timeout=timeout) as session:
            await self._login(session)
            try:
                if operation["type"] == "switch":
                    await self._do_switch(
                        session, operation["socket"], operation["state"]
                    )
                return await self._fetch_status(session)
            finally:
                # Logout ALWAYS runs, even on exception
                await self._logout(session)

    async def _login(self, session: aiohttp.ClientSession) -> None:
        url = f"http://{self._ip}/login.html"
        _LOGGER.debug("EGPM2LAN: logging in to %s", self._ip)
        await session.post(url, data={"pw": self._password})

    async def _logout(self, session: aiohttp.ClientSession) -> None:
        """Best-effort logout - must never raise."""
        url = f"http://{self._ip}/login.html"
        _LOGGER.debug("EGPM2LAN: logging out from %s", self._ip)
        try:
            await session.get(url)
        except Exception:  # noqa: BLE001
            pass

    async def _do_switch(
        self, session: aiohttp.ClientSession, socket_nr: int, state: int
    ) -> None:
        """POST switch command for one socket.

        Only the target socket gets 1 or 0.
        All other sockets get empty string - no accidental state change.
        """
        url = f"http://{self._ip}/"
        post_data = {
            f"cte{i}": str(state) if i == socket_nr else ""
            for i in range(1, NUMBER_OF_SOCKETS + 1)
        }
        _LOGGER.debug(
            "EGPM2LAN: socket %d -> %s (post_data: %s)",
            socket_nr,
            "on" if state else "off",
            post_data,
        )
        await session.post(url, data=post_data)

    async def _fetch_status(self, session: aiohttp.ClientSession) -> SocketStates:
        """GET root page and parse all 4 socket states in one request."""
        url = f"http://{self._ip}/"
        resp = await session.get(url)
        html = await resp.text()
        return self._parse_status(html)

    # ------------------------------------------------------------------
    # Status parsing
    # ------------------------------------------------------------------

    def _parse_status(self, html: str) -> SocketStates:
        """Parse socket states from device HTML.

        New firmware:  var sockstates = [0,1,0,1];
        Old firmware:  bare pattern 0,1,0,1 anywhere in page
        """
        # Modern firmware: JavaScript array
        match = re.search(r"sockstates\s*=\s*\[\s*([01](?:\s*,\s*[01]){3})\s*\]", html)
        if match:
            raw = [int(x.strip()) for x in match.group(1).split(",")]
            if len(raw) == NUMBER_OF_SOCKETS:
                states = {i + 1: bool(raw[i]) for i in range(NUMBER_OF_SOCKETS)}
                _LOGGER.debug("EGPM2LAN status (new fw): %s", states)
                return states

        # Legacy firmware: bare 0,1,0,1 pattern
        match = re.search(r"\b([01]),([01]),([01]),([01])\b", html)
        if match:
            states = {i: bool(int(match.group(i))) for i in range(1, 5)}
            _LOGGER.debug("EGPM2LAN status (legacy fw): %s", states)
            return states

        _LOGGER.error("EGPM2LAN: cannot parse status. HTML snippet: %.300s", html)
        raise UpdateFailed(
            "Cannot parse socket states from device - check IP and password"
        )
