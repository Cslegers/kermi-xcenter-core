"""Test the Kermi x-center config flow."""

from unittest.mock import patch

from modbus_connection import ModbusProtocolError
from modbus_connection.mock import MockModbusConnection

from homeassistant.components.kermi_xcenter.const import DEFAULT_UNIT_IDS, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from tests.common import MockConfigEntry

from .conftest import HOST, setup_integration

USER_INPUT = {CONF_HOST: HOST, CONF_PORT: 502, **DEFAULT_UNIT_IDS}


def _patch_temporary_unit(connection: MockModbusConnection):
    """Hand the flow a unit from the mock connection."""

    class _Ctx:
        def __init__(self, unit_id: int) -> None:
            self._unit_id = unit_id

        async def __aenter__(self):
            return connection.for_unit(self._unit_id)

        async def __aexit__(self, *args) -> None:
            return None

    return patch(
        "homeassistant.components.kermi_xcenter.config_flow.async_get_temporary_unit",
        side_effect=lambda hass, params, unit_id: _Ctx(unit_id),
    )


async def test_user_flow(hass: HomeAssistant, connection: MockModbusConnection) -> None:
    """A reachable heat pump creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with _patch_temporary_unit(connection):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kermi x-center"
    assert result["data"][CONF_HOST] == HOST
    assert result["result"].unique_id == f"{HOST}_502"


async def test_cannot_connect(
    hass: HomeAssistant, connection: MockModbusConnection
) -> None:
    """An unreachable heat pump shows an error and lets the user retry."""
    connection.for_unit(40).fail_read(3, ModbusProtocolError("truncated"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_temporary_unit(connection):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    # Recovering on the retry.
    connection.for_unit(40).fail_read(3, None)
    with _patch_temporary_unit(connection):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_is_aborted(
    hass: HomeAssistant,
    connection: MockModbusConnection,
    mock_config_entry: MockConfigEntry,
    mock_units,
) -> None:
    """The same controller cannot be added twice."""
    await setup_integration(hass, mock_config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with _patch_temporary_unit(connection):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
