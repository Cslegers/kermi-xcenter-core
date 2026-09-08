"""Config flow for the Kermi x-center integration."""

from typing import Any

from kermi_xcenter_modbus import async_module_present
from modbus_connection import ModbusError, ModbusTcpParams
import voluptuous as vol

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import CONF_UNIT_ID_HEAT_PUMP, DEFAULT_UNIT_IDS, DOMAIN, UNIT_ID_KEYS

DEFAULT_PORT = 502


def _unit_id_selector() -> NumberSelector:
    """Return a selector for a Modbus device address."""
    return NumberSelector(
        NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)
    )


STEP_USER = vol.Schema(
    {
        vol.Required(CONF_HOST): TextSelector(),
        vol.Required(CONF_PORT, default=DEFAULT_PORT): NumberSelector(
            NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)
        ),
        **{
            vol.Required(key, default=default): _unit_id_selector()
            for key, default in DEFAULT_UNIT_IDS.items()
        },
    }
)


class KermiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Kermi x-center."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the connection details and check the heat pump answers."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_HOST: user_input[CONF_HOST],
                CONF_PORT: int(user_input[CONF_PORT]),
                **{key: int(user_input[key]) for key in UNIT_ID_KEYS},
            }
            await self.async_set_unique_id(f"{data[CONF_HOST]}_{data[CONF_PORT]}")
            self._abort_if_unique_id_configured()

            if await self._async_heat_pump_answers(data):
                return self.async_create_entry(title="Kermi x-center", data=data)
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER, errors=errors
        )

    async def _async_heat_pump_answers(self, data: dict[str, Any]) -> bool:
        """Return whether the heat pump responds on the given connection.

        Only the heat pump is required. The storage, universal and
        photovoltaic feed-in modules vary per installation and are probed at
        setup, so their absence must not block configuration.
        """
        params = ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])
        try:
            async with async_get_temporary_unit(
                self.hass, params, data[CONF_UNIT_ID_HEAT_PUMP]
            ) as unit:
                # Register 3 is the outdoor temperature sensor: present on
                # every heat pump, and reading it is free of side effects.
                return await async_module_present(unit, 3)
        except (HomeAssistantError, ModbusError, OSError, ValueError):
            return False
