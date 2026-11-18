# esphome-solarman

ESPHome external component that reads **Deye hybrid inverters** over the local
network, through the Solarman V5 protocol spoken by the WiFi logger stick
(TCP port 8899). No cloud, no Home Assistant required.

The logger's IP is found automatically by UDP broadcast, so the only thing a
user has to supply is the **logger serial number** — and even that can be typed
in at runtime from the web UI instead of being hardcoded in YAML.

> **Status: confirmed on a Deye 8K SG05LP1** (2026-08-22). Every sensor below
> was read from a live installation and cross-checked for internal consistency:
> scaling, the 32-bit word order of the energy totals, and the battery power
> sign all come from measured values rather than documentation.
>
> **One thing is still open**: the Grid Power sign convention. It read 0 W for
> the whole test, so the direction could not be observed.
>
> Other Deye models place these values at different addresses. On unfamiliar
> hardware, run `scan_registers()` first — see
> [Confirming the register map](#confirming-the-register-map).
>
> **This fork** (`xolarkodak/esphome-solarman`) adds grid voltage and
> frequency, battery capacity (Ah and kWh), battery current and temperature,
> PV3/PV4 strings, per-string current and total PV power — and fixes two
> reply-parsing bugs (see [Changes in this fork](#changes-in-this-fork)).
> The new addresses come from the Deye single-phase Modbus map and the
> ha-solarman `deye_hybrid` profile; they have not yet been cross-checked on
> live hardware the way the original set was.

## Read-only by design

This component only ever emits Modbus function code **0x03** (read holding
registers). It contains no write function code (0x05 / 0x06 / 0x0F / 0x10) and
no code path that could alter an inverter setting — it is safe to point at a
live installation. The constant is named and commented in the source so that
adding a write would have to be a deliberate change rather than an accident.

## Requirements

- An **ESP32** (the component uses POSIX sockets; ESP8266 is not supported)
- Either `arduino` or `esp-idf` framework
- The ESP32 on the **same LAN** as the inverter's WiFi logger stick

## Installation

```yaml
external_components:
  - source: github://xolarkodak/esphome-solarman@v0.6.0
    components: [solarman_minimal]
```

This is all ESPHome Builder (the Home Assistant add-on) needs: it fetches the
component from GitHub at build time. The repository has to be public.

Pin a tag, not a branch. A branch moves under you, and the first sign is a build
that fails without you having changed anything.

## Usage

```yaml
solarman_minimal:
  id: solarman
  update_interval: 30s
  # serial: 2712345678   # optional — otherwise set at runtime, see below
  # host: 192.168.1.100  # optional — otherwise found by UDP discovery

  battery_soc:
    name: "Battery SOC"
  battery_power:
    name: "Battery power"       # signed: + discharging, - charging
  grid_power:
    name: "Grid power"          # signed; direction not yet confirmed
  load_power:
    name: "Load power"
  pv1_power:
    name: "PV1 power"
  pv2_power:
    name: "PV2 power"
  pv3_power:
    name: "PV3 power"
  pv3_voltage:
    name: "PV3 voltage"
  pv3_current:
    name: "PV3 current"
  pv_power:
    name: "PV total power"      # PV1 + PV2 + PV3 + PV4
  grid_voltage:
    name: "Grid voltage"        # AC input of the inverter, L1-N
  grid_frequency:
    name: "Grid frequency"
  battery_capacity:
    name: "Battery capacity"    # Ah, as configured on the inverter
  battery_capacity_energy:
    name: "Battery capacity kWh" # Ah x battery_nominal_voltage
  daily_production:
    name: "Daily production"
  total_production:
    name: "Total production"
  daily_consumption:
    name: "Daily consumption"
  daily_energy_bought:
    name: "Daily energy bought"
  daily_energy_sold:
    name: "Daily energy sold"
  device_state:
    name: "Device state"        # 0 standby, 1 self-test, 2 normal, 3 alarm, 4 fault
  grid_connected:
    name: "Grid connected"      # 1 tied to the utility, 0 islanded
```

All sensors are optional — declare only what you need. Also available:
`battery_voltage`, `battery_current` (signed, + discharging),
`battery_temperature`, `pv1_voltage`/`pv2_voltage`/`pv4_voltage`,
`pv1_current`/`pv2_current`/`pv4_current`, `pv4_power`,
`total_consumption`, `daily_battery_charge`, `daily_battery_discharge`.

`battery_nominal_voltage` (default `51.2V`, a 16-cell LiFePO4 bank) is used only
to turn the Ah capacity into `battery_capacity_energy`. Set it to `48V` or
whatever your bank is rated at.

### Full register map

| Key | Register | Scale | Notes |
|---|---|---|---|
| `device_state` | 0x003B | 1 | 0 standby, 1 self-test, 2 normal, 3 alarm, 4 fault |
| `daily_battery_charge` / `_discharge` | 0x0046 / 0x0047 | 0.1 kWh | |
| `daily_energy_bought` / `_sold` | 0x004C / 0x004D | 0.1 kWh | |
| `grid_frequency` | 0x004F | 0.01 Hz | **new** |
| `daily_consumption` | 0x0054 | 0.1 kWh | |
| `total_consumption` | 0x0055-56 | 0.1 kWh | 32-bit, low word first |
| `total_production` | 0x0060-61 | 0.1 kWh | 32-bit, low word first |
| `daily_production` | 0x006C | 0.1 kWh | |
| `pvN_voltage` | 0x006D + 2(N-1) | 0.1 V | PV3/PV4 **new** |
| `pvN_current` | 0x006E + 2(N-1) | 0.1 A | **new** |
| `grid_voltage` | 0x0096 | 0.1 V | **new**, grid side L1-N |
| `grid_power` | 0x00A9 | 1 W | signed, direction unconfirmed |
| `load_power` | 0x00B2 | 1 W | |
| `battery_temperature` | 0x00B6 | 0.1 °C, −100 | **new**, NaN when 0 (no probe) |
| `battery_voltage` | 0x00B7 | 0.01 V | |
| `battery_soc` | 0x00B8 | 1 % | |
| `pvN_power` | 0x00BA + (N-1) | 1 W | PV3/PV4 **new** |
| `battery_power` | 0x00BE | 1 W | signed, + discharging |
| `battery_current` | 0x00BF | 0.01 A | **new**, signed, + discharging |
| `grid_connected` | 0x00C2 | 0/1 | |
| `battery_capacity` | 0x00CC | 1 Ah | **new**, the inverter's Batt Capacity setting |

Still two TCP round trips per poll: 0x003B-0x0074 and 0x0096-0x00CC.

`device_state` and `grid_connected` are numeric rather than text or binary
sensors: this component creates its own entities, and one entity type keeps a
single code path. Map the value to a word where you display it.

### Setting the serial at runtime

Rather than hardcoding the serial, expose a text entity and let the user type it
once. It is persisted to flash (NVS) and survives reboots.

```yaml
web_server:
  port: 80

text:
  - platform: template
    name: "Logger Serial"
    mode: text
    restore_value: true
    optimistic: true
    on_value:
      - lambda: id(solarman).set_serial_from_text(x);
```

## Confirming the register map

Deye firmware variants place registers at different addresses. Single-phase
low-voltage hybrids (`SUN-xK-SG0xLP1`) use the low block this component reads
(0x003B-0x00CC). Three-phase hybrids (`SG0xLP3`, `SG0xHP3`) keep battery, PV,
grid and load around registers 500-700 instead, and are **not** supported by
the built-in map. `scan_registers()` reads both
families and logs every **non-zero** register, so one run identifies the layout:

```yaml
button:
  - platform: template
    name: "Scan Registers"
    on_press:
      - lambda: id(solarman).scan_registers();
```

Set `logger: level: DEBUG`, press the button, and read the log. Each value is
printed unsigned, signed and ×0.1 so the scaling is obvious. Then adjust the
register constants at the top of `solarman_minimal.cpp`.

### Finding the serial number if you don't know it

It is printed on the logger stick and shown in the SolarmanPV app. Failing that:
enter any number, and watch the log at `DEBUG` level. Discovery logs **every**
UDP reply before filtering by serial, so the logger's real serial appears in:

```
[D][solarman] UDP reply from 192.168.1.50: ...,...,2712345678
```

## How it works

Solarman V5 wraps a standard Modbus RTU frame in its own envelope:

```
[0xA5][len LE][0x4510 LE][seq LE][logger serial LE]
  [0x02 frame type][sensor type][12 timestamp bytes]
  [Modbus RTU: slave + FC03 + address + count + CRC16]
[checksum][0x15]
```

Discovery broadcasts `WIFIKIT-214028-READ` on UDP port 48899 and matches the
configured serial against the replies. The resolved IP is cached in flash, and
re-discovered only after several consecutive read failures — so a single dropped
packet does not throw away a working address.

Registers are read in batches rather than one connection per value.

## Changes in this fork

**New sensors** — see the register table above.

**Reply parsing fixed.** The Modbus payload used to be located by scanning the
V5 frame from byte 11 for the bytes `01 03`. The V5 status byte is `0x01`, so
whenever the low byte of the logger's working-time counter happened to be
`0x03` (about one poll in 900 in a simulation over random counters - at a
30 s interval, roughly one bad reading every 7-8 hours) the timestamp bytes were decoded as register
values and published — an occasional absurd spike on the screen. The payload
is now read at its fixed offset (25) and checked against both the V5 checksum
and the Modbus CRC; a corrupt frame is a failed poll, never a wrong number.
Modbus exception replies are recognised and logged.

**Short reads fixed.** The receive loop stopped after `29 + 2·count` bytes, three
bytes short of a real reply (`32 + 2·count`). It only worked because the reply
usually arrives in one TCP segment. Frames are now sized from their own length
field, and unsolicited frames the logger pushes into the stream are skipped.

**Indexes replaced by addresses.** Values are looked up by register address,
not by position in the batch, so widening a batch cannot silently move a
sensor onto the wrong register.

**`millis()` wrap.** Timeouts used `millis() < deadline`, which misbehaves after
~49.7 days of uptime. They now compare a signed difference.

**`status_line()` in English** (was Italian), plain ASCII so LVGL fonts can draw it.

**`host:`** is validated as an IPv4 address at config time.

## Licence

MIT
