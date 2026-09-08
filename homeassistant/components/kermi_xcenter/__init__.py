"""The Kermi x-center integration.

An x-center is a Modbus device, and this integration does not own its
connection. It collects the connection details in its own config flow, then
asks the ``modbus`` integration for one ``ModbusUnit`` per device address the
installation uses. Every unit sits on the same shared connection, which
``modbus`` closes once the last config entry holding a unit on it unloads.
"""

from kermi_xcenter_modbus import KermiXCenter
from modbus_connection import ModbusTcpParams

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import UNIT_ID_KEYS
from .coordinator import KermiConfigEntry, KermiCoordinator

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.WATER_HEATER,
]


async def async_setup_entry(hass: HomeAssistant, entry: KermiConfigEntry) -> bool:
    """Set up a Kermi x-center from a config entry."""
    params = ModbusTcpParams(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
    )

    # One unit per configured device address, all on the same connection.
    # Nothing is read here, so a controller that is powered down does not hold
    # up startup; the coordinator's first refresh decides what is reachable.
    unit_ids = {
        module: entry.data[key]
        for key, module in UNIT_ID_KEYS.items()
        if entry.data.get(key) is not None
    }
    units = {
        unit_id: async_get_unit(hass, entry, params, unit_id)
        for unit_id in set(unit_ids.values())
    }

    device = KermiXCenter(units, unit_ids=unit_ids)
    coordinator = KermiCoordinator(hass, entry, device)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    # The borrowed units are bound to the connection modbus holds now. When it
    # drops, modbus rebuilds it; reload so we re-borrow on the fresh connection
    # rather than keeping dead units.
    for unit in units.values():
        entry.async_on_unload(
            unit.on_connection_lost(
                lambda: hass.config_entries.async_schedule_reload(entry.entry_id)
            )
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: KermiConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
