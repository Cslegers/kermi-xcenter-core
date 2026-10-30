"""Test the photovoltaic diagnostics of the Kermi x-center integration."""

from collections.abc import AsyncGenerator
from datetime import timedelta
import logging

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import ModbusError
from modbus_connection.mock import MockModbusConnection, WriteEvent
import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.kermi_xcenter.const import (
    CONF_UNIT_ID_PV_FEED,
    DEFAULT_UNIT_IDS,
    DOMAIN,
)
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from tests.common import MockConfigEntry

HEAT_PUMP = 40
PV_FEED = 2
REGISTER_301 = 301
REGISTER_MAX = 65535
FEED_IN_REGISTER = 1

MISMATCH_KEY = "pv_feed_mismatch"
TARGET_KEY = "heat_pump_pv_modulation_power_target"
COORDINATOR_LOGGER = "homeassistant.components.kermi_xcenter.coordinator"


class Installation:
    """A configured integration and the mock bus behind it."""

    def __init__(self, hass: HomeAssistant, entry: MockConfigEntry) -> None:
        """Bind to a set-up entry."""
        self.hass = hass
        self.entry = entry
        self.coordinator = entry.runtime_data

    def entity_id(self, platform: str, key: str) -> str | None:
        """Return the entity id for *key*, if the entity was created."""
        return er.async_get(self.hass).async_get_entity_id(
            platform, DOMAIN, f"{self.entry.entry_id}_{key}"
        )

    @property
    def mismatch(self) -> str:
        """Return the state of the mismatch sensor."""
        state = self.hass.states.get(self.entity_id("binary_sensor", MISMATCH_KEY))
        assert state is not None
        return state.state

    async def poll(self) -> None:
        """Run one coordinator refresh."""
        await self.coordinator.async_refresh()


@pytest.fixture
def bus(connection: MockModbusConnection, mock_units) -> MockModbusConnection:
    """Return the captured controller, set to 8000 W against 0 W."""
    connection.for_unit(PV_FEED).holding[FEED_IN_REGISTER] = 8000
    connection.for_unit(HEAT_PUMP).holding[REGISTER_301] = 0
    return connection


async def _async_install(
    hass: HomeAssistant,
    *,
    with_pv_feed: bool = True,
    enable: tuple[str, ...] = (),
) -> Installation:
    """Set the integration up."""
    data = {CONF_HOST: "192.0.2.1", CONF_PORT: 502, **DEFAULT_UNIT_IDS}
    if not with_pv_feed:
        del data[CONF_UNIT_ID_PV_FEED]
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id="192.0.2.1_502")
    entry.add_to_hass(hass)

    # A registry entry created up front keeps a disabled-by-default entity on.
    for key in enable:
        er.async_get(hass).async_get_or_create(
            "number",
            DOMAIN,
            f"{entry.entry_id}_{key}",
            config_entry=entry,
            disabled_by=None,
        )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return Installation(hass, entry)


@pytest.fixture
async def installation(
    hass: HomeAssistant, bus: MockModbusConnection
) -> AsyncGenerator[Installation]:
    """Return an installation with both photovoltaic modules."""
    installed = await _async_install(hass)
    yield installed
    await hass.config_entries.async_unload(installed.entry.entry_id)


# -- number entity -----------------------------------------------------------


async def test_power_target_is_disabled_config_entity(
    hass: HomeAssistant, installation: Installation
) -> None:
    """The register 301 entity exists, but only for someone who opts in."""
    entity_id = installation.entity_id("number", TARGET_KEY)
    assert entity_id is not None

    entry = er.async_get(hass).async_get(entity_id)
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert entry.entity_category is EntityCategory.CONFIG
    assert entry.original_name == "Photovoltaic modulation power target"
    assert entry.original_device_class is NumberDeviceClass.POWER
    assert entry.unit_of_measurement == "W"
    assert hass.states.get(entity_id) is None


async def test_power_target_writes_register_301_only(
    hass: HomeAssistant, bus: MockModbusConnection
) -> None:
    """Setting the entity writes the number as given, and only to 301."""
    installed = await _async_install(hass, enable=(TARGET_KEY,))
    entity_id = installed.entity_id("number", TARGET_KEY)
    state = hass.states.get(entity_id)
    assert float(state.state) == 0
    assert state.attributes["min"] == 0
    assert state.attributes["max"] == REGISTER_MAX
    assert state.attributes["step"] == 1
    assert state.attributes["mode"] == NumberMode.BOX

    heat_pump: list[WriteEvent] = []
    feed_in: list[WriteEvent] = []
    bus.for_unit(HEAT_PUMP).on_write(heat_pump.append)
    bus.for_unit(PV_FEED).on_write(feed_in.append)

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id, "value": 2800},
        blocking=True,
    )

    assert [(e.address, e.values) for e in heat_pump] == [(REGISTER_301, [2800])]
    assert feed_in == []
    await hass.config_entries.async_unload(installed.entry.entry_id)


async def test_surplus_write_does_not_touch_register_301(
    hass: HomeAssistant, bus: MockModbusConnection, installation: Installation
) -> None:
    """The surplus entity keeps writing the feed-in register alone."""
    heat_pump: list[WriteEvent] = []
    feed_in: list[WriteEvent] = []
    bus.for_unit(HEAT_PUMP).on_write(heat_pump.append)
    bus.for_unit(PV_FEED).on_write(feed_in.append)

    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": installation.entity_id("number", "pv_feed_surplus_power"),
            "value": 3500,
        },
        blocking=True,
    )

    assert [(e.address, e.values) for e in feed_in] == [(FEED_IN_REGISTER, [3500])]
    assert heat_pump == []


# -- partial poll failure logging --------------------------------------------


def _messages(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    """Return the sub-system lines logged at exactly *level*.

    The base coordinator logs its own outage and recovery on the same logger.
    """
    return [
        record.getMessage()
        for record in caplog.records
        if record.name == COORDINATOR_LOGGER
        and record.levelno == level
        and record.getMessage().startswith("Sub-system")
    ]


async def test_failure_warns_once_and_recovery_logs_info(
    bus: MockModbusConnection,
    installation: Installation,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing sub-system logs on the change, not on every poll."""
    caplog.set_level(logging.DEBUG, logger=COORDINATOR_LOGGER)
    bus.for_unit(PV_FEED).fail_read(FEED_IN_REGISTER, ModbusError("refused"))

    for _ in range(3):
        await installation.poll()

    warnings = _messages(caplog, logging.WARNING)
    assert len(warnings) == 1
    assert "pv_feed" in warnings[0]
    assert "refused" in warnings[0]
    assert _messages(caplog, logging.INFO) == []
    assert _messages(caplog, logging.DEBUG) == []
    assert installation.coordinator.failing == {"pv_feed"}

    bus.for_unit(PV_FEED).fail_read(FEED_IN_REGISTER, None)
    for _ in range(3):
        await installation.poll()

    infos = _messages(caplog, logging.INFO)
    assert len(infos) == 1
    assert "pv_feed" in infos[0]
    assert len(_messages(caplog, logging.WARNING)) == 1
    assert installation.coordinator.failing == set()


async def test_failures_are_tracked_per_sub_system(
    bus: MockModbusConnection,
    installation: Installation,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A second sub-system failing warns even while the first still fails."""
    caplog.set_level(logging.INFO, logger=COORDINATOR_LOGGER)
    bus.for_unit(PV_FEED).fail_read(FEED_IN_REGISTER, ModbusError("refused"))
    await installation.poll()
    bus.for_unit(HEAT_PUMP).fail_read(REGISTER_301, ModbusError("refused"))
    await installation.poll()
    await installation.poll()

    labels = ("pv_feed", "heat_pump.pv_modulation")
    warnings = _messages(caplog, logging.WARNING)
    assert len(warnings) == len(labels)
    assert all(
        label in warning for label, warning in zip(labels, warnings, strict=True)
    )


async def test_failure_survives_full_outage_without_a_second_warning(
    bus: MockModbusConnection,
    installation: Installation,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A poll where nothing answers says nothing about the failing sub-system."""
    caplog.set_level(logging.INFO, logger=COORDINATOR_LOGGER)
    bus.for_unit(PV_FEED).fail_read(FEED_IN_REGISTER, ModbusError("refused"))
    await installation.poll()

    units = [bus.for_unit(unit_id) for unit_id in DEFAULT_UNIT_IDS.values()]
    for unit in units:
        unit.fail_requests(ModbusError("gone"))
    await installation.poll()
    assert not installation.coordinator.last_update_success
    for unit in units:
        unit.fail_requests(None)
    await installation.poll()

    assert len(_messages(caplog, logging.WARNING)) == 1
    assert _messages(caplog, logging.INFO) == []


# -- mismatch sensor ---------------------------------------------------------


async def test_mismatch_entity_description(
    hass: HomeAssistant, installation: Installation
) -> None:
    """The sensor is a diagnostic problem sensor."""
    entity_id = installation.entity_id("binary_sensor", MISMATCH_KEY)
    entry = er.async_get(hass).async_get(entity_id)
    assert entry.original_name == "Photovoltaic feed-in mismatch"
    assert entry.original_device_class is BinarySensorDeviceClass.PROBLEM
    assert entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entry.disabled_by is None


async def test_mismatch_turns_on_only_after_thirty_minutes(
    freezer: FrozenDateTimeFactory, installation: Installation
) -> None:
    """Exactly 30 minutes is not over 30 minutes; polls do not reset the timer."""
    assert installation.mismatch == STATE_OFF

    for _ in range(6):
        freezer.tick(timedelta(minutes=5))
        await installation.poll()
    assert installation.mismatch == STATE_OFF

    freezer.tick(timedelta(seconds=1))
    await installation.poll()
    assert installation.mismatch == STATE_ON


async def test_mismatch_stays_off_within_threshold(
    freezer: FrozenDateTimeFactory,
    bus: MockModbusConnection,
    installation: Installation,
) -> None:
    """A difference of exactly 100 W is not a mismatch, in either direction."""
    for feed_in, register_301 in ((3100, 3000), (3000, 3100)):
        bus.for_unit(PV_FEED).holding[FEED_IN_REGISTER] = feed_in
        bus.for_unit(HEAT_PUMP).holding[REGISTER_301] = register_301
        await installation.poll()
        freezer.tick(timedelta(hours=1))
        await installation.poll()
        assert installation.mismatch == STATE_OFF


async def test_mismatch_just_over_threshold_counts(
    freezer: FrozenDateTimeFactory,
    bus: MockModbusConnection,
    installation: Installation,
) -> None:
    """A difference of 101 W counts."""
    bus.for_unit(PV_FEED).holding[FEED_IN_REGISTER] = 3101
    bus.for_unit(HEAT_PUMP).holding[REGISTER_301] = 3000
    await installation.poll()
    freezer.tick(timedelta(minutes=31))
    await installation.poll()
    assert installation.mismatch == STATE_ON


@pytest.mark.parametrize(
    ("unit_id", "address"), [(PV_FEED, FEED_IN_REGISTER), (HEAT_PUMP, REGISTER_301)]
)
async def test_change_in_either_value_restarts_the_timer(
    freezer: FrozenDateTimeFactory,
    bus: MockModbusConnection,
    installation: Installation,
    unit_id: int,
    address: int,
) -> None:
    """A moved value, still apart, starts the 30 minutes again."""
    freezer.tick(timedelta(minutes=29))
    await installation.poll()

    bus.for_unit(unit_id).holding[address] = 5000
    await installation.poll()

    freezer.tick(timedelta(minutes=29))
    await installation.poll()
    assert installation.mismatch == STATE_OFF

    freezer.tick(timedelta(minutes=2))
    await installation.poll()
    assert installation.mismatch == STATE_ON


async def test_change_clears_a_reported_mismatch(
    freezer: FrozenDateTimeFactory,
    bus: MockModbusConnection,
    installation: Installation,
) -> None:
    """The problem clears when the values agree, and the timer starts over."""
    freezer.tick(timedelta(minutes=31))
    await installation.poll()
    assert installation.mismatch == STATE_ON

    bus.for_unit(HEAT_PUMP).holding[REGISTER_301] = 8000
    await installation.poll()
    assert installation.mismatch == STATE_OFF

    bus.for_unit(HEAT_PUMP).holding[REGISTER_301] = 0
    await installation.poll()
    assert installation.mismatch == STATE_OFF


async def test_partial_failure_holds_the_timer(
    freezer: FrozenDateTimeFactory,
    bus: MockModbusConnection,
    installation: Installation,
) -> None:
    """Stale values neither reset the timer nor report a result."""
    freezer.tick(timedelta(minutes=20))
    await installation.poll()

    bus.for_unit(PV_FEED).fail_read(FEED_IN_REGISTER, ModbusError("refused"))
    await installation.poll()
    assert installation.mismatch == STATE_UNAVAILABLE

    freezer.tick(timedelta(minutes=11))
    await installation.poll()
    assert installation.mismatch == STATE_UNAVAILABLE

    bus.for_unit(PV_FEED).fail_read(FEED_IN_REGISTER, None)
    await installation.poll()
    assert installation.mismatch == STATE_ON


async def test_full_outage_holds_the_timer(
    freezer: FrozenDateTimeFactory,
    bus: MockModbusConnection,
    installation: Installation,
) -> None:
    """A failed refresh leaves the timer running through the outage."""
    freezer.tick(timedelta(minutes=20))
    await installation.poll()

    units = [bus.for_unit(unit_id) for unit_id in DEFAULT_UNIT_IDS.values()]
    for unit in units:
        unit.fail_requests(ModbusError("gone"))
    await installation.poll()
    assert installation.mismatch == STATE_UNAVAILABLE

    freezer.tick(timedelta(minutes=11))
    for unit in units:
        unit.fail_requests(None)
    await installation.poll()
    assert installation.mismatch == STATE_ON


async def test_mismatch_is_not_created_without_pv_feed(
    hass: HomeAssistant, bus: MockModbusConnection
) -> None:
    """An installation without the feed-in module has nothing to compare."""
    installed = await _async_install(hass, with_pv_feed=False)
    assert installed.coordinator.device.pv_feed is None
    assert installed.entity_id("binary_sensor", MISMATCH_KEY) is None
    assert installed.entity_id("number", TARGET_KEY) is not None
    await hass.config_entries.async_unload(installed.entry.entry_id)


async def test_module_going_absent_resets_the_timer(
    freezer: FrozenDateTimeFactory, installation: Installation
) -> None:
    """Losing the feed-in module clears the timer rather than raising."""
    device = installation.coordinator.device
    pv_feed = device.pv_feed

    freezer.tick(timedelta(minutes=29))
    await installation.poll()

    device.pv_feed = None
    await installation.poll()
    assert installation.mismatch == STATE_UNAVAILABLE

    device.pv_feed = pv_feed
    freezer.tick(timedelta(minutes=2))
    await installation.poll()
    assert installation.mismatch == STATE_OFF

    freezer.tick(timedelta(minutes=31))
    await installation.poll()
    assert installation.mismatch == STATE_ON
