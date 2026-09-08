"""DataUpdateCoordinator that polls the x-center."""

import logging

from kermi_xcenter_modbus import KermiXCenter
from modbus_connection import ModbusError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type KermiConfigEntry = ConfigEntry[KermiCoordinator]


class KermiCoordinator(DataUpdateCoordinator[KermiXCenter]):
    """Refreshes every module of an installation on a schedule.

    ``async_update`` fans out to each sub-system, and each reads only its own
    registers, so adding or removing entities never changes what is polled.
    One sub-system failing does not take the rest of the poll with it; the
    ``modbus`` integration owns the connection, this only reads.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: KermiConfigEntry,
        device: KermiXCenter,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=SCAN_INTERVAL,
        )
        self.device = device

    async def _async_update_data(self) -> KermiXCenter:
        """Refresh every module, failing only if nothing answered."""
        try:
            report = await self.device.async_update()
        except ModbusError as err:
            raise UpdateFailed(f"Error communicating with the x-center: {err}") from err

        if not report.updated:
            raise UpdateFailed("The x-center did not answer any sub-system")

        for label, error in report.failed.items():
            _LOGGER.debug("Sub-system %s did not answer: %s", label, error)

        return self.device
