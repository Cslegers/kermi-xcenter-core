"""Constants for the Kermi x-center integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "kermi_xcenter"

# An x-center installation spreads over several Modbus device addresses on one
# connection. These are the addresses Kermi ships; an installer can change
# them, so each is offered in the config flow.
CONF_UNIT_ID_HEAT_PUMP: Final = "unit_id_heat_pump"
CONF_UNIT_ID_STORAGE_HEATING: Final = "unit_id_storage_heating"
CONF_UNIT_ID_STORAGE_HOT_WATER: Final = "unit_id_storage_hot_water"
CONF_UNIT_ID_UNIVERSAL: Final = "unit_id_universal_module"
CONF_UNIT_ID_PV_FEED: Final = "unit_id_pv_feed"

DEFAULT_UNIT_ID_HEAT_PUMP: Final = 40
DEFAULT_UNIT_ID_STORAGE_HEATING: Final = 50
DEFAULT_UNIT_ID_STORAGE_HOT_WATER: Final = 51
DEFAULT_UNIT_ID_UNIVERSAL: Final = 30
DEFAULT_UNIT_ID_PV_FEED: Final = 2

# Maps each config key onto the module name the library uses.
UNIT_ID_KEYS: Final[dict[str, str]] = {
    CONF_UNIT_ID_HEAT_PUMP: "heat_pump",
    CONF_UNIT_ID_STORAGE_HEATING: "storage_heating",
    CONF_UNIT_ID_STORAGE_HOT_WATER: "storage_hot_water",
    CONF_UNIT_ID_UNIVERSAL: "universal_module",
    CONF_UNIT_ID_PV_FEED: "pv_feed",
}

DEFAULT_UNIT_IDS: Final[dict[str, int]] = {
    CONF_UNIT_ID_HEAT_PUMP: DEFAULT_UNIT_ID_HEAT_PUMP,
    CONF_UNIT_ID_STORAGE_HEATING: DEFAULT_UNIT_ID_STORAGE_HEATING,
    CONF_UNIT_ID_STORAGE_HOT_WATER: DEFAULT_UNIT_ID_STORAGE_HOT_WATER,
    CONF_UNIT_ID_UNIVERSAL: DEFAULT_UNIT_ID_UNIVERSAL,
    CONF_UNIT_ID_PV_FEED: DEFAULT_UNIT_ID_PV_FEED,
}

# The controller changes slowly, but its power and efficiency figures move
# with the compressor, so poll at a fixed short interval.
SCAN_INTERVAL: Final = timedelta(seconds=30)
