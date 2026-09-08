"""Binary sensor platform — the alarm flag and mode indicators."""

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KermiConfigEntry, KermiCoordinator
from .entity import KermiEntity


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
