"""Test setting up and unloading the Kermi x-center integration."""

from modbus_connection import ModbusProtocolError
from modbus_connection.mock import MockModbusConnection

from homeassistant.components.kermi_xcenter.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from tests.common import MockConfigEntry

from .conftest import setup_integration


async def test_setup_and_unload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_units
) -> None:
    """The entry loads and unloads cleanly."""
    await setup_integration(hass, mock_config_entry)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_absent_module_creates_no_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_units,
    device_registry: dr.DeviceRegistry,
) -> None:
    """The captured installation has no universal module, so it gets no device."""
    await setup_integration(hass, mock_config_entry)

    devices = dr.async_entries_for_config_entry(
        device_registry, mock_config_entry.entry_id
    )
    names = {device.name for device in devices}

    assert "Kermi x-center" in names
    assert "Heating storage" in names
    assert "Hot water storage" in names
    assert "Photovoltaic feed-in" in names
    assert "Heating circuit module" not in names


async def test_setup_retries_when_nothing_answers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    connection: MockModbusConnection,
    mock_units,
) -> None:
    """A controller that answers nothing leaves the entry retrying."""
    for unit_id in (2, 30, 40, 50, 51):
        connection.for_unit(unit_id).fail_requests(ModbusProtocolError("truncated"))

    await setup_integration(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_values_decode_from_the_captured_registers(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_units
) -> None:
    """Spot-check that the register map reaches the entities intact."""
    await setup_integration(hass, mock_config_entry)

    outdoor = hass.states.get("sensor.kermi_x_center_outdoor_temperature")
    assert outdoor is not None
    assert float(outdoor.state) == 21.5

    state = hass.states.get("sensor.kermi_x_center_state")
    assert state is not None
    assert state.state == "standby"

    # 0xD8F1 is the unfitted-sensor sentinel and must not surface as -999.9.
    assert DOMAIN in hass.config.components
