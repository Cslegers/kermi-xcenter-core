"""Climate platform — one entity per heating circuit.

The circuit's season override maps onto the HVAC mode and its energy mode onto
the preset, which is the closest honest fit: the controller decides flow
temperature from its own heating curve, so the setpoint here is reported, not
commanded. Use the number entities to shift the curve.
"""

from typing import Any

from kermi_xcenter_modbus import EnergyMode, SeasonSelection

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KermiConfigEntry, KermiCoordinator
from .entity import KermiEntity

# The controller's season override and Home Assistant's HVAC modes.
SEASON_TO_HVAC: dict[SeasonSelection, HVACMode] = {
    SeasonSelection.AUTO: HVACMode.AUTO,
    SeasonSelection.HEATING: HVACMode.HEAT,
    SeasonSelection.COOLING: HVACMode.COOL,
    SeasonSelection.OFF: HVACMode.OFF,
}
HVAC_TO_SEASON = {hvac: season for season, hvac in SEASON_TO_HVAC.items()}

# The controller's energy mode and Home Assistant's presets. These are the
# controller's own labels rather than Home Assistant's standard presets,
# because "eco"/"comfort" here are named modes on the device.
ENERGY_TO_PRESET: dict[EnergyMode, str] = {
    EnergyMode.OFF: "off",
    EnergyMode.ECO: "eco",
    EnergyMode.NORMAL: "normal",
    EnergyMode.COMFORT: "comfort",
    EnergyMode.CUSTOM: "custom",
}
PRESET_TO_ENERGY = {preset: mode for mode, preset in ENERGY_TO_PRESET.items()}

# Modules that can carry a heating circuit.
CIRCUIT_MODULES = ("storage_heating", "storage_hot_water", "universal_module")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a climate entity per heating circuit this installation has."""
    coordinator = entry.runtime_data
    async_add_entities(
        KermiClimate(coordinator, module)
        for module in CIRCUIT_MODULES
        if getattr(coordinator.device, module, None) is not None
    )


class KermiClimate(KermiEntity, ClimateEntity):
    """One heating circuit."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF]
    _attr_preset_modes = list(PRESET_TO_ENERGY)
    _attr_supported_features = ClimateEntityFeature.PRESET_MODE
    _attr_name = "Heating circuit"

    def __init__(self, coordinator: KermiCoordinator, module: str) -> None:
        """Initialize the heating circuit."""
        super().__init__(
            coordinator,
            EntityDescription(key=f"{module}_heating_circuit"),
            module,
            "heating_circuit",
        )

    @property
    def current_temperature(self) -> float | None:
        """Return the measured circuit flow temperature."""
        return self._value("temperature_actual")

    @property
    def target_temperature(self) -> float | None:
        """Return the flow temperature the controller is working towards."""
        return self._value("setpoint")

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the circuit's season override."""
        season = self._value("season_selection")
        return None if season is None else SEASON_TO_HVAC.get(season)

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return what the circuit is doing right now."""
        mode = self._value("operating_mode")
        if mode is None:
            return None
        return {
            0: HVACAction.OFF,
            1: HVACAction.HEATING,
            2: HVACAction.COOLING,
        }.get(int(mode))

    @property
    def preset_mode(self) -> str | None:
        """Return the circuit's energy mode."""
        energy = self._value("energy_mode")
        return None if energy is None else ENERGY_TO_PRESET.get(energy)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the circuit's season override."""
        await self._async_write("season_selection", HVAC_TO_SEASON[hvac_mode])

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set the circuit's energy mode."""
        await self._async_write("energy_mode", PRESET_TO_ENERGY[preset_mode])

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the circuit's own status word, which has no HVAC equivalent."""
        status = self._value("status")
        return None if status is None else {"circuit_status": status.name.lower()}
