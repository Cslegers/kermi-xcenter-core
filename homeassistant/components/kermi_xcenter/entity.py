"""Base entity for the Kermi x-center.

The heat pump is the main device. Each other Modbus module an installation has
becomes a sub-device linked to it with ``via_device``, so the storage modules
and the photovoltaic feed-in register show up as their own devices rather than
crowding the heat pump.
"""

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KermiCoordinator

#: Display name of each module, used for its sub-device.
MODULE_NAMES: dict[str, str] = {
    "heat_pump": "Heat pump",
    "storage_heating": "Heating storage",
    "storage_hot_water": "Hot water storage",
    "universal_module": "Heating circuit module",
    "pv_feed": "Photovoltaic feed-in",
}


class KermiEntity(CoordinatorEntity[KermiCoordinator]):
    """Common identity and device info for every x-center entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: KermiCoordinator,
        description: EntityDescription,
        module: str,
        component: str | None = None,
    ) -> None:
        """Initialize the entity.

        *module* is the Modbus module it reads from, *component* the
        sub-system within it. The photovoltaic feed-in module is a single
        component, so it passes ``None``.
        """
        super().__init__(coordinator)
        self.entity_description = description
        self._module = module
        self._component = component

        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

        if module == "heat_pump":
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                manufacturer="Kermi",
                model="x-center",
                name="Kermi x-center",
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_{module}")},
                manufacturer="Kermi",
                name=MODULE_NAMES.get(module, module),
                via_device=(DOMAIN, entry.entry_id),
            )

    @property
    def _subsystem(self) -> Any | None:
        """The library object this entity reads from, or None if not fitted."""
        module = getattr(self.coordinator.device, self._module, None)
        if module is None or self._component is None:
            return module
        return getattr(module, self._component, None)

    @property
    def available(self) -> bool:
        """Whether the sub-system this entity reads from answered."""
        return super().available and self._subsystem is not None

    def _value(self, attribute: str) -> Any:
        """Read *attribute* off this entity's sub-system."""
        subsystem = self._subsystem
        return None if subsystem is None else getattr(subsystem, attribute, None)

    async def _async_write(self, attribute: str, value: Any) -> None:
        """Write *value* to *attribute*, then refresh."""
        subsystem = self._subsystem
        if subsystem is None:
            raise RuntimeError(f"{self._module} is not fitted")
        await subsystem.write(attribute, value)
        await self.coordinator.async_request_refresh()
