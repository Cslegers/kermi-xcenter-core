"""Fixtures for the Kermi x-center tests.

Registers are seeded from a capture of a real x-center IFM, so a decode or
address mistake shows up as a wrong temperature rather than a passing test.
The installation captured has a heat pump, both storage modules and the
photovoltaic feed-in register, but no universal module.
"""

from collections.abc import Generator
from unittest.mock import patch

from modbus_connection import ModbusProtocolError
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest

from homeassistant.components.kermi_xcenter.const import DEFAULT_UNIT_IDS, DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from tests.common import MockConfigEntry

HOST = "192.168.1.50"

CAPTURE: dict[int, dict[int, int]] = {
    2: {1: 0},
    40: {
        1: 237,
        2: 215,
        3: 215,
        50: 235,
        51: 226,
        52: 0,
        100: 0,
        101: 0,
        102: 0,
        103: 0,
        104: 0,
        105: 0,
        106: 0,
        107: 0,
        108: 0,
        109: 0,
        110: 0,
        111: 0,
        150: 50179,
        151: 59748,
        152: 49898,
        200: 0,
        250: 0,
        300: 0,
        301: 0,
        302: 400,
        303: 550,
    },
    50: {
        1: 360,
        2: 258,
        50: 0,
        51: 0,
        100: 0,
        101: 0,
        102: 480,
        103: 0,
        104: 500,
        150: 1,
        151: 460,
        152: 259,
        153: 1,
        154: 0,
        155: 2,
        156: 0,
        157: 1,
        158: 180,
        159: 160,
        160: 220,
        161: 200,
        162: 0,
        163: 0,
        200: 0,
        201: 0,
        202: 0,
        203: 0,
        250: 360,
        251: 0xD8F1,
        252: 460,
        253: 0xD8F1,
        254: 215,
        255: 180,
        300: 23339,
        301: 301,
    },
    51: {
        1: 0,
        2: 0,
        50: 0,
        51: 0,
        100: 442,
        101: 480,
        102: 480,
        103: 0,
        104: 500,
        150: 9,
        151: 0,
        152: 350,
        153: 0,
        154: 0,
        155: 2,
        156: 0,
        157: 0,
        158: 180,
        159: 160,
        160: 220,
        161: 200,
        162: 0,
        163: 0,
        200: 0,
        201: 0,
        202: 0,
        203: 0,
        250: 444,
        251: 0xD8F1,
        252: 0xD8F1,
        253: 0xD8F1,
        254: 0,
        255: 0,
        300: 0,
        301: 577,
    },
}


@pytest.fixture
def connection() -> MockModbusConnection:
    """Return a mock connection carrying the captured installation."""
    conn = MockModbusConnection()
    for unit_id, registers in CAPTURE.items():
        unit = conn.for_unit(unit_id)
        for address, value in registers.items():
            unit.holding[address] = value
    # No universal module. A real controller signals that with a truncated
    # frame rather than a Modbus exception, so reproduce that here.
    for address in (150, 250, 300):
        conn.for_unit(30).fail_read(
            address, ModbusProtocolError("Invalid response PDU length")
        )
    return conn


@pytest.fixture
def mock_units(connection: MockModbusConnection) -> Generator[MockModbusUnit]:
    """Hand the integration units from the mock connection."""
    with patch(
        "homeassistant.components.kermi_xcenter.async_get_unit",
        side_effect=lambda hass, entry, params, unit_id: connection.for_unit(unit_id),
    ):
        yield connection


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a configured entry for the captured installation."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Kermi x-center",
        data={CONF_HOST: HOST, CONF_PORT: 502, **DEFAULT_UNIT_IDS},
        unique_id=f"{HOST}_502",
    )


async def setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry
) -> MockConfigEntry:
    """Add and set up *entry*."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry
