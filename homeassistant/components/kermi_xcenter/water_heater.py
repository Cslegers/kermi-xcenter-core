"""Water heater platform — domestic hot water on a storage module.

The controller exposes a constant setpoint plus a one-shot ("Einmalladung")
charge with its own target. The one-shot charge maps onto the high-demand
operation, since that is exactly what it is: heat the tank harder, once.
"""

from typing import Any

from homeassistant.components.water_heater import (
    STATE_HIGH_DEMAND,
    STATE_PERFORMANCE,
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KermiConfigEntry, KermiCoordinator
from .entity import KermiEntity

# Modules that can carry a hot water tank.
HOT_WATER_MODULES = ("storage_hot_water", "storage_heating")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a water heater for each storage module that reports a tank."""
    coordinator = entry.runtime_data
    entities = []
    for module in HOT_WATER_MODULES:
        storage = getattr(coordinator.device, module, None)
        if storage is None:
            continue
        # A module fitted for heating leaves the hot water block at zero; only
        # the one actually serving a tank reports a temperature.
        if storage.hot_water.temperature_actual is None:
            continue
        entities.append(KermiWaterHeater(coordinator, module))
    async_add_entities(entities)


class KermiWaterHeater(KermiEntity, WaterHeaterEntity):
    """The domestic hot water tank."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = [STATE_PERFORMANCE, STATE_HIGH_DEMAND]
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE
        | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_name = "Hot water"
    _attr_min_temp = 0
    _attr_max_temp = 85

    def __init__(self, coordinator: KermiCoordinator, module: str) -> None:
        """Initialize the water heater."""
        super().__init__(
            coordinator,
            EntityDescription(key=f"{module}_hot_water"),
            module,
            "hot_water",
        )

    @property
    def current_temperature(self) -> float | None:
        """Return the measured tank temperature."""
        return self._value("temperature_actual")

    @property
    def target_temperature(self) -> float | None:
        """Return the effective target, which follows the active charge mode."""
        if self._value("boost_active"):
            return self._value("boost_setpoint")
        return self._value("constant_setpoint")

    @property
    def current_operation(self) -> str | None:
        """Return whether a one-shot charge is running."""
        boost = self._value("boost_active")
        if boost is None:
            return None
        return STATE_HIGH_DEMAND if boost else STATE_PERFORMANCE

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature of whichever charge mode is active."""
        temperature = kwargs[ATTR_TEMPERATURE]
        attribute = (
            "boost_setpoint" if self._value("boost_active") else "constant_setpoint"
        )
        await self._async_write(attribute, temperature)

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Start or stop a one-shot charge."""
        await self._async_write("boost_active", operation_mode == STATE_HIGH_DEMAND)
