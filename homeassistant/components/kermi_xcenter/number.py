"""Number platform — the writable setpoints, including photovoltaic surplus.

The photovoltaic feed-in entity is the one an automation writes to: point it at
whatever your inverter reports as surplus and the controller modulates the heat
pump against it. It only exists where Kermi has enabled that register.
"""

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KermiConfigEntry, KermiCoordinator
from .entity import KermiEntity


@dataclass(frozen=True, kw_only=True)
class KermiNumberDescription(NumberEntityDescription):
    """Describes a writable numeric setpoint."""

    module: str
    component: str | None
    attribute: str


NUMBERS: tuple[KermiNumberDescription, ...] = (
    # Kermi enables this register per installation; where it is not enabled the
    # module is absent and this entity is never created.
    KermiNumberDescription(
        key="pv_feed_surplus_power",
        name="Photovoltaic surplus",
        module="pv_feed",
        component=None,
        attribute="surplus_power",
        device_class=NumberDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        native_min_value=0,
        native_max_value=6553.5,
        native_step=0.1,
        mode=NumberMode.BOX,
    ),
    KermiNumberDescription(
        key="heat_pump_pv_heating_setpoint",
        name="Photovoltaic heating setpoint",
        module="heat_pump",
        component="pv_modulation",
        attribute="heating_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=85,
        native_step=0.1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    KermiNumberDescription(
        key="heat_pump_pv_hot_water_setpoint",
        name="Photovoltaic hot water setpoint",
        module="heat_pump",
        component="pv_modulation",
        attribute="hot_water_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=85,
        native_step=0.1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
)

_CIRCUIT_NUMBERS: tuple[tuple[str, str, str, float, float], ...] = (
    ("summer_threshold", "Summer threshold", "°C", 0, 50),
    ("winter_threshold", "Winter threshold", "°C", 0, 50),
    ("cooling_on_threshold", "Cooling on threshold", "°C", 0, 50),
    ("cooling_off_threshold", "Cooling off threshold", "°C", 0, 50),
)


def _circuit_descriptions(module: str) -> tuple[KermiNumberDescription, ...]:
    """Build the heating curve setpoints for one module's circuit."""
    return (
        *(
            KermiNumberDescription(
                key=f"{module}_heating_circuit_{attribute}",
                name=name,
                module=module,
                component="heating_circuit",
                attribute=attribute,
                device_class=NumberDeviceClass.TEMPERATURE,
                native_unit_of_measurement=UnitOfTemperature.CELSIUS,
                native_min_value=minimum,
                native_max_value=maximum,
                native_step=0.1,
                mode=NumberMode.BOX,
                entity_category=EntityCategory.CONFIG,
            )
            for attribute, name, _unit, minimum, maximum in _CIRCUIT_NUMBERS
        ),
        KermiNumberDescription(
            key=f"{module}_heating_circuit_curve_offset",
            name="Heating curve offset",
            module=module,
            component="heating_circuit",
            attribute="curve_offset",
            native_unit_of_measurement=UnitOfTemperature.KELVIN,
            native_min_value=-5,
            native_max_value=5,
            native_step=0.1,
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the writable setpoints for the modules this installation has."""
    coordinator = entry.runtime_data
    descriptions = [
        *NUMBERS,
        *_circuit_descriptions("storage_heating"),
        *_circuit_descriptions("universal_module"),
    ]
    async_add_entities(
        KermiNumber(coordinator, description)
        for description in descriptions
        if getattr(coordinator.device, description.module, None) is not None
    )


class KermiNumber(KermiEntity, NumberEntity):
    """A writable setpoint on the x-center."""

    entity_description: KermiNumberDescription

    def __init__(
        self, coordinator: KermiCoordinator, description: KermiNumberDescription
    ) -> None:
        """Initialize the number."""
        super().__init__(
            coordinator, description, description.module, description.component
        )

    @property
    def native_value(self) -> float | None:
        """Return the current setpoint."""
        return self._value(self.entity_description.attribute)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new setpoint to the controller."""
        await self._async_write(self.entity_description.attribute, value)
