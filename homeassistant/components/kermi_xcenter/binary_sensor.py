"""Binary sensor platform — the alarm flag and mode indicators."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import KermiConfigEntry, KermiCoordinator
from .entity import KermiEntity

#: How far apart the feed-in value and register 301 must be to count, in watts.
PV_FEED_MISMATCH_THRESHOLD = 100
#: How long both values must sit unchanged and apart before reporting a problem.
PV_FEED_MISMATCH_DURATION = timedelta(minutes=30)
#: The poll labels of the two sub-systems the mismatch sensor compares.
_PV_FEED_MISMATCH_SOURCES = frozenset({"pv_feed", "heat_pump.pv_modulation"})


@dataclass(frozen=True, kw_only=True)
class KermiBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a two-state reading of one sub-system."""

    module: str
    component: str
    attribute: str


BINARY_SENSORS: tuple[KermiBinarySensorDescription, ...] = (
    KermiBinarySensorDescription(
        key="heat_pump_status_alarm",
        name="Alarm",
        module="heat_pump",
        component="status",
        attribute="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    KermiBinarySensorDescription(
        key="heat_pump_pv_modulation_active",
        name="Photovoltaic modulation",
        module="heat_pump",
        component="pv_modulation",
        attribute="active",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
)


PV_FEED_MISMATCH = BinarySensorEntityDescription(
    key="pv_feed_mismatch",
    name="Photovoltaic feed-in mismatch",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)


def _circuit_flags(module: str) -> tuple[KermiBinarySensorDescription, ...]:
    """Summer and cooling mode indicators for one module's circuit."""
    return tuple(
        KermiBinarySensorDescription(
            key=f"{module}_heating_circuit_{attribute}",
            name=name,
            module=module,
            component="heating_circuit",
            attribute=attribute,
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        for attribute, name in (
            ("summer_mode", "Summer mode"),
            ("cooling_mode", "Cooling mode"),
        )
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors for the modules this installation has."""
    coordinator = entry.runtime_data
    descriptions = [
        *BINARY_SENSORS,
        *_circuit_flags("storage_heating"),
        *_circuit_flags("universal_module"),
    ]
    async_add_entities(
        KermiBinarySensor(coordinator, description)
        for description in descriptions
        if getattr(coordinator.device, description.module, None) is not None
    )
    device = coordinator.device
    if device.heat_pump is not None and device.pv_feed is not None:
        async_add_entities([KermiPvFeedMismatchBinarySensor(coordinator)])


class KermiBinarySensor(KermiEntity, BinarySensorEntity):
    """A two-state reading from the x-center."""

    entity_description: KermiBinarySensorDescription

    def __init__(
        self,
        coordinator: KermiCoordinator,
        description: KermiBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            coordinator, description, description.module, description.component
        )

    @property
    def is_on(self) -> bool | None:
        """Return the current state."""
        return self._value(self.entity_description.attribute)


class KermiPvFeedMismatchBinarySensor(KermiEntity, BinarySensorEntity):
    """Whether register 301 has stopped following the feed-in value.

    Compares the two as whole watts, which is what one installation sees; where
    register 301 scales differently this reports a mismatch that is only a
    difference in units. The timer lives on the entity, so it carries across
    polls but restarts with Home Assistant or a reload of the integration. A
    poll that could not read either value leaves the timer alone, because that
    says nothing about whether the values moved.
    """

    def __init__(self, coordinator: KermiCoordinator) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, PV_FEED_MISMATCH, "heat_pump", "pv_modulation")
        self._values: tuple[int, int] | None = None
        self._apart_since: datetime | None = None
        self._observe()

    @property
    def _reading_is_fresh(self) -> bool:
        """Whether the last poll read both values."""
        return (
            self.coordinator.last_update_success
            and not _PV_FEED_MISMATCH_SOURCES & self.coordinator.failing
        )

    def _observe(self) -> None:
        """Start, keep or clear the timer from the latest reading."""
        if not self._reading_is_fresh:
            return
        pv_feed = self.coordinator.device.pv_feed
        surplus = None if pv_feed is None else pv_feed.surplus_power
        power = self._value("power")
        if surplus is None or power is None:
            self._values = self._apart_since = None
            return
        values = (surplus, power)
        if abs(surplus - power) <= PV_FEED_MISMATCH_THRESHOLD:
            self._apart_since = None
        elif values != self._values or self._apart_since is None:
            self._apart_since = dt_util.utcnow()
        self._values = values

    @callback
    def _handle_coordinator_update(self) -> None:
        """Take in the new reading before writing the state."""
        self._observe()
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Whether both compared values are present and current."""
        return (
            super().available
            and self.coordinator.device.pv_feed is not None
            and self._reading_is_fresh
        )

    @property
    def is_on(self) -> bool | None:
        """Return whether the values have sat apart for too long."""
        if self._values is None:
            return None
        if self._apart_since is None:
            return False
        return dt_util.utcnow() - self._apart_since > PV_FEED_MISMATCH_DURATION
