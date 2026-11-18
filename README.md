# esphome-solarman

ESPHome external component that reads **Deye hybrid inverters** over the local
network, through the Solarman V5 protocol spoken by the WiFi logger stick
(TCP port 8899). No cloud, no Home Assistant required.

The logger's IP is found automatically by UDP broadcast, so the only thing a
user has to supply is the **logger serial number** — and even that can be typed
in at runtime from the web UI instead of being hardcoded in YAML.

## Supported models

The register map is chosen per model family. With `model: auto` (the default)
the component reads the device type from register `0x0000` and picks the map
itself; an unknown or unreadable type falls back to the single-phase map.

| `model:` | Deye family | Device type | Status |
|---|---|---|---|
| `single_phase_lv` | `SUN-xK-SG0xLP1` (e.g. SG05LP1) | `0x__03` | **Field-confirmed** on SUN-8K-SG05LP1 and SUN-6K-SG05LP1 |
| `three_phase_lv` | `SUN-xK-SG0xLP3` (48 V battery) | `0x__05` | From the Deye Modbus map / ha-solarman `deye_p3` — **not yet checked on hardware** |
| `three_phase_hv` | `SUN-xK-SG0xHP3` (HV battery) | `0x__06` | As `three_phase_lv` with the HV scales — **not yet checked on hardware** |

Deye string inverters and microinverters use other maps and are not covered.
If you run one of the unconfirmed families, please press **Scan Registers**
(see below), compare the log with the inverter's display and open an issue
with the result.

**Still open on every model:** the Grid Power sign convention.

## Read-only by design

This component only ever emits Modbus function code **0x03** (read holding
registers). It contains no write function code (0x05 / 0x06 / 0x0F / 0x10) and
no code path that could alter an inverter setting — it is safe to point at a
live installation. Custom sensors can only *read* a register, too.

## Requirements

- An **ESP32** (the component uses POSIX sockets; ESP8266 is not supported)
- Either `arduino` or `esp-idf` framework
- The ESP32 on the **same LAN** as the inverter's WiFi logger stick

## Installation

```yaml
external_components:
  - source: github://xolarkodak/esphome-solarman@v0.7.0
    components: [solarman_minimal]
```

This is all ESPHome Builder (the Home Assistant add-on) needs: it fetches the
component from GitHub at build time.

Pin a tag, not a branch. A branch moves under you, and the first sign is a build
that fails without you having changed anything.

## Usage

```yaml
solarman_minimal:
  id: solarman
  update_interval: 30s
  # serial: 2712345678        # optional — otherwise set at runtime, see below
  # host: 192.168.1.100       # optional — otherwise found by UDP discovery
  # model: auto               # auto | single_phase_lv | three_phase_lv | three_phase_hv
  # battery_nominal_voltage: 51.2V  # only for the kWh figures
  # max_block_size: 100       # largest Modbus read, lower it if the logger balks

  battery_soc:
    name: "Battery SOC"
  battery_power:
    name: "Battery power"            # signed: + discharging, - charging
  battery_capacity:
    name: "Battery capacity"         # Ah, the inverter's Batt Capacity setting
  battery_capacity_energy:
    name: "Battery capacity kWh"     # Ah x battery_nominal_voltage
  battery_remaining_energy:
    name: "Battery energy left"      # capacity kWh x SOC
  grid_voltage:
    name: "Grid voltage"             # AC input of the inverter (L1 on 3-phase)
  grid_power:
    name: "Grid power"               # signed; direction not yet confirmed
  load_power:
    name: "Load power"
  pv1_power:
    name: "PV1 power"
  pv2_power:
    name: "PV2 power"
  pv_power:
    name: "PV total power"           # PV1 + PV2 + PV3 + PV4
  daily_production:
    name: "Daily production"
  device_state:
    name: "Device state"             # 0 standby, 1 self-test, 2 normal, 3 alarm, 4 fault
```

All sensors are optional — declare only what you need. **Only the registers the
declared sensors need are read**, merged into as few Modbus requests as
possible; the read plan is printed to the log at startup.

### All sensors

| Key | Single-phase LV | Three-phase LV / HV | Scale | Notes |
|---|---|---|---|---|
| `device_type` | 0x0000 | 0x0000 | raw | what `model: auto` decided from |
| `device_state` | 0x003B | 0x01F4 | 1 | 0 standby … 4 fault |
| `pvN_power` (N=1..4) | 0x00BA+(N-1) | 0x02A0+(N-1) | 1 W (HV: 10 W) | PV3/PV4 read 0 on 2-MPPT models |
| `pvN_voltage` | 0x006D+2(N-1) | 0x02A4+2(N-1) | 0.1 V | |
| `pvN_current` | 0x006E+2(N-1) | 0x02A5+2(N-1) | 0.1 A | |
| `pv_power` | sum | sum | W | derived |
| `grid_voltage` | 0x0096 | 0x0256 | 0.1 V | L1-N |
| `grid_voltage_l2` / `_l3` | — | 0x0257 / 0x0258 | 0.1 V | three-phase only |
| `grid_frequency` | 0x004F | 0x0261 | 0.01 Hz | |
| `grid_power` | 0x00A9 | 0x0271 | 1 W, signed | sign unconfirmed |
| `grid_connected` | 0x00C2 | — | 0/1 | |
| `load_power` | 0x00B2 | 0x028D | 1 W | |
| `load_power_l1` / `_l2` / `_l3` | — | 0x028A..0x028C | 1 W | three-phase only |
| `battery_soc` | 0x00B8 | 0x024C | 1 % | |
| `battery_voltage` | 0x00B7 | 0x024B | 0.01 V (HV: 0.1 V) | |
| `battery_power` | 0x00BE | 0x024E | 1 W (HV: 10 W), signed | + discharging |
| `battery_current` | 0x00BF | 0x024F | 0.01 A, signed | + discharging |
| `battery_temperature` | 0x00B6 | 0x024A | 0.1 °C − 100 | unknown when 0 (no probe) |
| `battery_capacity` | 0x00CC | 0x0066 | 1 Ah | setting, refreshed every 20 polls |
| `battery_capacity_energy` | | | kWh | derived: Ah × nominal V |
| `battery_remaining_energy` | | | kWh | derived: capacity kWh × SOC |
| `daily_production` | 0x006C | 0x0211 | 0.1 kWh | |
| `total_production` | 0x0060-61 | 0x0216-17 | 0.1 kWh | 32-bit, low word first |
| `daily_consumption` | 0x0054 | 0x020E | 0.1 kWh | |
| `total_consumption` | 0x0055-56 | 0x020F-10 | 0.1 kWh | 32-bit, low word first |
| `daily_energy_bought` / `_sold` | 0x004C / 0x004D | 0x0208 / 0x0209 | 0.1 kWh | |
| `daily_battery_charge` / `_discharge` | 0x0046 / 0x0047 | 0x0202 / 0x0203 | 0.1 kWh | |

A sensor with no register on the detected model stays *unknown*, and the log
says so once.

`battery_capacity_energy` is the battery's **total** size; `battery_remaining_energy`
is what is **in it now** (total × SOC). `battery_nominal_voltage` defaults to
51.2 V (16-cell LiFePO4); set it for other banks, and always for HV batteries.

`device_state` and `grid_connected` are numeric rather than text or binary
sensors. Map the value to a word where you display it. For a screen,
`id(solarman).model_name()` returns the map in use as text.

### Custom registers

Any register the built-in tables do not cover can be read without touching the
component:

```yaml
solarman_minimal:
  custom_sensors:
    # Addresses below are single-phase examples - check yours with Scan Registers.
    - name: "Gen port power"
      register: 0x00A6
      type: s16          # u16 (default), s16, u32, s32, u32_be, s32_be
      scale: 1           # value = raw * scale + offset
      unit_of_measurement: W
      device_class: power
      state_class: measurement
    - name: "Battery shutdown SOC"
      register: 0x00D9
      unit_of_measurement: "%"
      slow: true         # a setting: refresh every 20 polls only
```

`u32`/`s32` use two registers, low word first (Deye's order); the `_be`
variants take the high word first. `zero_is_unknown: true` publishes *unknown*
instead of 0. Custom registers are merged into the same reads as the built-in
ones, so a register next to the existing blocks costs nothing extra.

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

`scan_registers()` reads every range any built-in profile uses, for both the
single-phase and the three-phase families, and logs every **non-zero**
register:

```yaml
button:
  - platform: template
    name: "Scan Registers"
    on_press:
      - lambda: id(solarman).scan_registers();
```

Set `logger: level: DEBUG`, press the button, and read the log. Each value is
printed unsigned, signed and ×0.1 so the scaling is obvious. Compare with the
inverter's display; a register that is wrong for your model can be overridden
with a custom sensor, and a whole model family is one column in the profile
table in `components/solarman_minimal/__init__.py`.

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

The logger itself does not interpret anything: it forwards the Modbus frame to
the inverter over RS485. What each register *means* is decided by Deye per
model family, which is why the component carries one map per family.

Discovery broadcasts `WIFIKIT-214028-READ` and `HF-A11ASSISTHREAD` on UDP port
48899 and matches the configured serial against the replies. The resolved IP is
cached in flash, and re-discovered only after several consecutive read failures.

Each poll reads its blocks **one per main-loop pass**, not all at once, so a
slow logger holds up the screen for one read at a time.

## Changes in this fork

### v0.7.0

- **Several Deye families.** Register maps are data (profile tables in
  `__init__.py`), not code. `model: auto` picks the map from register 0x0000.
- **Read plan built from the configured sensors.** Fewer sensors, fewer
  registers read. On a single-phase inverter with every sensor declared the
  plan is the same two reads v0.6.0 made.
- **`custom_sensors`** for any register, with type, scale, offset.
- **`battery_remaining_energy`**: capacity × SOC.
- **Three-phase sensors**: `grid_voltage_l2/_l3`, `load_power_l1/_l2/_l3`.
- **Settings read rarely.** Battery capacity is refreshed every 20 polls
  unless it rides along in a block that is read anyway.
- **`device_type`** sensor and `model_name()` for the screen.

### v0.6.0

- New sensors: grid voltage and frequency, battery capacity (Ah, kWh), battery
  current and temperature, PV3/PV4, per-string current, total PV power.
- **Reply parsing fixed.** The Modbus payload used to be located by scanning the
  V5 frame from byte 11 for the bytes `01 03`. The V5 status byte is `0x01`, so
  whenever the low byte of the logger's working-time counter happened to be
  `0x03` the timestamp bytes were decoded as register values — about one poll in
  900 in a simulation over random counters, roughly one bad reading every 7-8
  hours at a 30 s interval. The payload is now read at its fixed offset (25)
  and checked against both the V5 checksum and the Modbus CRC.
- **Short reads fixed.** The receive loop stopped after `29 + 2·count` bytes,
  three short of a real reply (`32 + 2·count`). Frames are now sized from their
  own length field, and unsolicited frames are skipped.
- **`millis()` wrap** after ~49.7 days of uptime fixed.
- `status_line()` in English ASCII (was Italian), `host:` validated as IPv4.

## Licence

MIT
