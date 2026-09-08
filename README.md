# Kermi x-center — Home Assistant core integration

> **Not an official Kermi integration.** Independent and community-built, **not
> affiliated with, endorsed by, or supported by Kermi GmbH**.

Staging repository for the `kermi_xcenter` integration, laid out at Home
Assistant core's own paths so it can be dropped into a `home-assistant/core`
checkout:

```
homeassistant/components/kermi_xcenter/
tests/components/kermi_xcenter/
```

This is not installable on its own. To try the integration on a real system,
use [`ha-kermi-xcenter`](https://github.com/Cslegers/ha-kermi-xcenter),
which packages the same code for HACS.

## What it does

Talks to a Kermi x-center heat pump controller over local Modbus TCP. The
protocol lives in
[`kermi-xcenter-modbus`](https://github.com/Cslegers/kermi-xcenter-modbus)
and is pulled in through `requirements`, as core's architecture expects; this
repository holds only the Home Assistant layer.

Platforms: `sensor`, `binary_sensor`, `climate`, `water_heater`, `number`.

## Design notes

**It does not own its Modbus connection.** The config flow collects host and
port, then `async_setup_entry` asks the `modbus` integration for one
`ModbusUnit` per device address:

```python
unit = async_get_unit(hass, entry, ModbusTcpParams(host=host, port=port), unit_id)
```

An x-center spreads across several Modbus device addresses on one link — the
heat pump at 40, storage modules at 50/51, an optional universal module at 30 —
so several units are requested against the same `ModbusTcpParams`. The `modbus`
integration refcounts them onto a single shared connection and closes it when
the last config entry unloads.

> This requires **Home Assistant 2026.9.0 or newer**; `modbus.async_get_unit`
> first shipped in that release.

**Modules are discovered, not assumed.** Which modules an installation has
varies, so each is probed at setup and the absent ones produce no device. Only
the heat pump is required.

**One device per module.** The heat pump is the main device; every other module
is a sub-device linked with `via_device`.

**Photovoltaic feed-in.** Kermi releases an excess-solar function per
installation — separately from enabling Modbus at all — which exposes a device
address accepting solar surplus power. It is undocumented, so it is treated as
optional throughout and simply does not appear when absent.

## Development

```bash
python -m venv .venv && .venv/bin/pip install ruff
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
```

`pyproject.toml` carries Home Assistant core's own ruff configuration (copied
from core 2026.9.1) so this is checked against the rules a core pull request is
checked with. Two caveats when linting outside a core checkout: `tests` does not
resolve as core does, so import grouping and the `tests` banned-api rule are
handled by a documented per-file ignore. Re-run `ruff` and `pytest` inside a
core checkout before opening a pull request.

To run the tests, copy both trees into a core checkout and run:

```bash
pytest tests/components/kermi_xcenter
python -m script.hassfest
```

## Before opening a pull request

1. `kermi-xcenter-modbus` must be published to PyPI first — core requires the
   dependency to be available — and `requirements` in `manifest.json` pinned to
   that release.
2. A matching documentation pull request against `home-assistant.io` is
   required.
3. Brand images (`home-assistant/brands`) are needed; `quality_scale.yaml`
   currently records `brands: todo`.
4. Read
   [the Open Home Foundation AI policy](https://developers.home-assistant.io/docs/ai_policy).
   Contributions must be reviewed and understood by the contributor, and you
   must be able to explain every change in your own words.

## Credits and licence

Apache License 2.0 — see [LICENSE](LICENSE).

- The file layout and the entity, coordinator and config-flow patterns follow
  the `trovis557x` integration on the
  [trovis557x-integration](https://github.com/home-assistant/core/tree/trovis557x-integration/homeassistant/components/trovis557x)
  branch of [home-assistant/core](https://github.com/home-assistant/core)
  (Apache-2.0), corrected onto the `modbus.async_get_unit` API that actually
  shipped. `pyproject.toml` carries core's own ruff configuration.
- The device library is
  [Cslegers/kermi-xcenter-modbus](https://github.com/Cslegers/kermi-xcenter-modbus);
  see its `NOTICE.md` for what that builds on.
- Register numbers, names, ranges and defaults come from Kermi's
  *Kurzanleitung – Einbindung in externe Systeme* (D00028482/05-2024).

Licensed under the Apache License 2.0 — see [LICENSE](LICENSE).
