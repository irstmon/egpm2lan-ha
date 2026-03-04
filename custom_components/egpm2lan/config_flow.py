"""Config flow - UI-based setup with live connection test."""

from __future__ import annotations

import re

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_INTER_OP_DELAY,
    CONF_IP,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    DEFAULT_INTER_OP_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


class EGPMConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial UI setup of an EG-PM2-LAN device."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input[CONF_IP].strip()
            password = user_input.get(CONF_PASSWORD, "")
            scan_interval = int(
                user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
            inter_op_delay = int(
                user_input.get(CONF_INTER_OP_DELAY, DEFAULT_INTER_OP_DELAY)
            )

            try:
                await _test_connection(ip, password)
            except aiohttp.ClientConnectorError:
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "not_egpm_device"
            else:
                await self.async_set_unique_id(ip)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"EG-PM2-LAN ({ip})",
                    data={CONF_IP: ip, CONF_PASSWORD: password},
                    options={
                        CONF_SCAN_INTERVAL: scan_interval,
                        CONF_INTER_OP_DELAY: inter_op_delay,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(CONF_PASSWORD, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(
                        CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5, max=3600, step=5, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_INTER_OP_DELAY, default=DEFAULT_INTER_OP_DELAY
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=30, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Allow changing IP and/or password after initial setup."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors: dict[str, str] = {}

        if user_input is not None:
            ip = user_input[CONF_IP].strip()
            password = user_input.get(CONF_PASSWORD, "")

            try:
                await _test_connection(ip, password)
            except aiohttp.ClientConnectorError:
                errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except ValueError:
                errors["base"] = "not_egpm_device"
            else:
                await self.async_set_unique_id(ip)
                self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_IP: ip, CONF_PASSWORD: password},
                    reason="reconfigure_successful",
                )

        current = {
            CONF_IP: entry.data.get(CONF_IP, ""),
            CONF_PASSWORD: entry.data.get(CONF_PASSWORD, ""),
        }

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP, default=current[CONF_IP]): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.TEXT)
                    ),
                    vol.Optional(
                        CONF_PASSWORD, default=current[CONF_PASSWORD]
                    ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EGPMOptionsFlow:
        return EGPMOptionsFlow()


async def _test_connection(ip: str, password: str) -> None:
    """Login -> fetch status -> logout. Raise on failure or wrong device."""
    timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
    jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=jar, timeout=timeout) as session:
        await session.post(f"http://{ip}/login.html", data={"pw": password})
        resp = await session.get(f"http://{ip}/")
        html = await resp.text()
        try:
            await session.get(f"http://{ip}/login.html")
        except Exception:  # noqa: BLE001
            pass
    has_new = "sockstates" in html
    has_legacy = bool(re.search(r"\b[01],[01],[01],[01]\b", html))
    if not has_new and not has_legacy:
        raise ValueError("Not an EG-PM2-LAN device")


class EGPMOptionsFlow(config_entries.OptionsFlow):
    """Change scan_interval and inter_op_delay after initial setup."""

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_INTER_OP_DELAY: int(user_input[CONF_INTER_OP_DELAY]),
                }
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5, max=3600, step=5, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(
                        CONF_INTER_OP_DELAY,
                        default=self.config_entry.options.get(
                            CONF_INTER_OP_DELAY, DEFAULT_INTER_OP_DELAY
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=30, step=1, mode=NumberSelectorMode.BOX
                        )
                    ),
                }
            ),
        )
