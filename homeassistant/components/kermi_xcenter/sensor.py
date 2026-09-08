"""Sensor platform — measurements, efficiency figures and run time counters.

Setpoints that can be changed live on the climate, water heater and number
entities; what remains here is read-only.
"""

from dataclasses import dataclass

from kermi_xcenter_modbus import HeatPumpStatus

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import KermiConfigEntry, KermiCoordinator
from .entity import KermiEntity

_STATE_OPTIONS = [state.name.lower() for state in HeatPumpStatus]


@dataclass(frozen=True, kw_only=True)
class KermiSensorDescription(SensorEntityDescription):
    """Describes a sensor reading one attribute of one sub-system."""

    module: str
    component: str
    attribute: str


def _temperature(
    module: str,
    component: str,
    attribute: str,
    name: str,
    *,
    enabled: bool = True,
    diagnostic: bool = True,
) -> KermiSensorDescription:
    return KermiSensorDescription(
        key=f"{module}_{component}_{attribute}",
        name=name,
        module=module,
        component=component,
        attribute=attribute,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC if diagnostic else None,
        entity_registry_enabled_default=enabled,
    )


def _power(
    module: str, component: str, attribute: str, name: str, *, enabled: bool = True
) -> KermiSensorDescription:
    return KermiSensorDescription(
        key=f"{module}_{component}_{attribute}",
        name=name,
        module=module,
        component=component,
        attribute=attribute,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=enabled,
    )


def _cop(
    module: str, component: str, attribute: str, name: str, *, enabled: bool = True
) -> KermiSensorDescription:
    """A coefficient of performance: a ratio, so no unit and no device class."""
    return KermiSensorDescription(
        key=f"{module}_{component}_{attribute}",
        name=name,
        module=module,
        component=component,
        attribute=attribute,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=enabled,
    )


def _hours(
    module: str, component: str, attribute: str, name: str
) -> KermiSensorDescription:
    return KermiSensorDescription(
        key=f"{module}_{component}_{attribute}",
        name=name,
        module=module,
        component=component,
        attribute=attribute,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    )


HEAT_PUMP: tuple[KermiSensorDescription, ...] = (
    _temperature(
        "heat_pump",
        "energy_source",
        "outdoor_temperature",
        "Outdoor temperature",
        diagnostic=False,
    ),
    _temperature("heat_pump", "energy_source", "exit_temperature", "Source outlet"),
    _temperature("heat_pump", "energy_source", "inlet_temperature", "Source inlet"),
    _temperature("heat_pump", "charging_circuit", "flow_temperature", "Flow"),
    _temperature("heat_pump", "charging_circuit", "return_temperature", "Return"),
    KermiSensorDescription(
        key="heat_pump_charging_circuit_flow_rate",
        name="Flow rate",
        module="heat_pump",
        component="charging_circuit",
        attribute="flow_rate",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.LITERS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    _cop("heat_pump", "power", "cop", "COP"),
    _cop("heat_pump", "power", "cop_heating", "COP heating", enabled=False),
    _cop("heat_pump", "power", "cop_hot_water", "COP hot water", enabled=False),
    _cop("heat_pump", "power", "cop_cooling", "COP cooling", enabled=False),
    _power("heat_pump", "power", "thermal_power", "Thermal power"),
    _power("heat_pump", "power", "electrical_power", "Electrical power"),
    _power(
        "heat_pump",
        "power",
        "thermal_power_heating",
        "Thermal power heating",
        enabled=False,
    ),
    _power(
        "heat_pump",
        "power",
        "thermal_power_hot_water",
        "Thermal power hot water",
        enabled=False,
    ),
    _power(
        "heat_pump",
        "power",
        "thermal_power_cooling",
        "Thermal power cooling",
        enabled=False,
    ),
    _power(
        "heat_pump",
        "power",
        "electrical_power_heating",
        "Electrical power heating",
        enabled=False,
    ),
    _power(
        "heat_pump",
        "power",
        "electrical_power_hot_water",
        "Electrical power hot water",
        enabled=False,
    ),
    _power(
        "heat_pump",
        "power",
        "electrical_power_cooling",
        "Electrical power cooling",
        enabled=False,
    ),
    _hours("heat_pump", "operating_hours", "compressor", "Compressor run time"),
    _hours("heat_pump", "operating_hours", "fan", "Fan run time"),
    _hours(
        "heat_pump",
        "operating_hours",
        "storage_loading_pump",
        "Storage pump run time",
    ),
    KermiSensorDescription(
        key="heat_pump_status_state",
        name="State",
        module="heat_pump",
        component="status",
        attribute="state",
        device_class=SensorDeviceClass.ENUM,
        options=_STATE_OPTIONS,
    ),
)

_STORAGE_SENSORS: tuple[tuple[str, str, str], ...] = (
    ("storage", "heating_temperature", "Heating store"),
    ("storage", "heating_setpoint", "Heating store setpoint"),
    ("sensors", "t1", "Sensor T1"),
    ("sensors", "t2", "Sensor T2"),
    ("sensors", "t3", "Sensor T3"),
    ("sensors", "t4", "Sensor T4"),
    ("sensors", "outdoor_temperature_averaged", "Averaged outdoor temperature"),
)


def _storage_descriptions(module: str) -> tuple[KermiSensorDescription, ...]:
    """Build the sensor set for one storage module."""
    return (
        *(
            _temperature(module, component, attribute, name, enabled=False)
            for component, attribute, name in _STORAGE_SENSORS
        ),
        _hours(module, "operating_hours", "circuit_pump", "Circuit pump run time"),
        _hours(
            module,
            "operating_hours",
            "external_heat_generator",
            "External heat generator run time",
        ),
    )


# Reported in whole watts, unlike the heat pump's kilowatt figures.
PV_FEED: tuple[KermiSensorDescription, ...] = (
    KermiSensorDescription(
        key="heat_pump_pv_modulation_power",
        name="Photovoltaic modulation power",
        module="heat_pump",
        component="pv_modulation",
        attribute="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: KermiConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors for the modules this installation has."""
    coordinator = entry.runtime_data
    descriptions = [
        *HEAT_PUMP,
        *PV_FEED,
        *_storage_descriptions("storage_heating"),
        *_storage_descriptions("storage_hot_water"),
    ]
    async_add_entities(
        KermiSensor(coordinator, description)
        for description in descriptions
        if getattr(coordinator.device, description.module, None) is not None
    )


class KermiSensor(KermiEntity, SensorEntity):
    """One reading from the x-center."""

    entity_description: KermiSensorDescription

    def __init__(
        self, coordinator: KermiCoordinator, description: KermiSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator, description, description.module, description.component
        )

    @property
    def native_value(self) -> float | int | str | None:
        """Return the current value."""
        value = self._value(self.entity_description.attribute)
        if isinstance(value, HeatPumpStatus):
            return value.name.lower()
        return value
