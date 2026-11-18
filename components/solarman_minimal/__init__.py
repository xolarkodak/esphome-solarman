import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import (
    CONF_ID,
    DEVICE_CLASS_BATTERY,
    DEVICE_CLASS_CURRENT,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_ENERGY_STORAGE,
    DEVICE_CLASS_FREQUENCY,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_VOLTAGE,
    STATE_CLASS_MEASUREMENT,
    STATE_CLASS_TOTAL_INCREASING,
    UNIT_AMPERE,
    UNIT_CELSIUS,
    UNIT_HERTZ,
    UNIT_KILOWATT_HOURS,
    UNIT_PERCENT,
    UNIT_VOLT,
    UNIT_WATT,
)

DEPENDENCIES = ["wifi"]
# This component creates sensors itself rather than being a sensor platform, so
# nothing else guarantees the sensor component gets pulled into the build. A
# config whose only sensors come from here fails to compile without this, with
# a misleading "esphome/components/sensor/sensor.h: No such file or directory".
AUTO_LOAD = ["sensor"]

solarman_minimal_ns = cg.esphome_ns.namespace("solarman_minimal")
SolarmanMinimal = solarman_minimal_ns.class_("SolarmanMinimal", cg.PollingComponent)

CONF_HOST = "host"
CONF_TCP_SCAN = "tcp_scan"
CONF_SERIAL = "serial"
CONF_BATTERY_NOMINAL_VOLTAGE = "battery_nominal_voltage"

UNIT_AMPERE_HOURS = "Ah"


# ── Sensor shapes ──────────────────────────────────────────────────────────
def _power():
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_WATT,
        accuracy_decimals=0,
        device_class=DEVICE_CLASS_POWER,
        state_class=STATE_CLASS_MEASUREMENT,
    )


def _voltage(decimals=1):
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_VOLT,
        accuracy_decimals=decimals,
        device_class=DEVICE_CLASS_VOLTAGE,
        state_class=STATE_CLASS_MEASUREMENT,
    )


def _current(decimals=1):
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_AMPERE,
        accuracy_decimals=decimals,
        device_class=DEVICE_CLASS_CURRENT,
        state_class=STATE_CLASS_MEASUREMENT,
    )


def _energy():
    """Every daily/total counter on this inverter is the same shape: kWh at one
    decimal, monotonic within its period."""
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_KILOWATT_HOURS,
        accuracy_decimals=1,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    )


def _plain():
    return sensor.sensor_schema(
        accuracy_decimals=0,
        state_class=STATE_CLASS_MEASUREMENT,
    )


# key -> (schema factory, C++ setter, extra positional args before the sensor)
#
# Kept as one table so the schema and the codegen cannot drift apart: a key
# that validates but is never wired to C++ would produce an entity that stays
# "unknown" forever, with nothing in the log to say why.
SENSORS = {
    # ── PV strings. PVn power 0x00BA+(n-1), voltage 0x006D+2(n-1),
    #    current 0x006E+2(n-1). PV3/PV4 read 0 on 2-MPPT models.
    **{
        f"pv{n}_power": (_power, "set_pv_power_sensor", [n - 1])
        for n in range(1, 5)
    },
    **{
        f"pv{n}_voltage": (_voltage, "set_pv_voltage_sensor", [n - 1])
        for n in range(1, 5)
    },
    **{
        f"pv{n}_current": (_current, "set_pv_current_sensor", [n - 1])
        for n in range(1, 5)
    },
    # Sum of PV1..PV4, computed here so a screen does not need a template.
    "pv_power": (_power, "set_pv_total_power_sensor", []),
    # ── Grid (inverter AC input)
    # 0x0096, grid-side L1-N voltage x0.1 V.
    "grid_voltage": (_voltage, "set_grid_voltage_sensor", []),
    # 0x004F, x0.01 Hz.
    "grid_frequency": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_HERTZ,
            accuracy_decimals=2,
            device_class=DEVICE_CLASS_FREQUENCY,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        "set_grid_frequency_sensor",
        [],
    ),
    # Signed, but the direction convention is NOT yet confirmed — it read
    # 0 W throughout the only upstream field test. Verify against a known
    # reference during grid import or export before trusting the sign.
    "grid_power": (_power, "set_grid_power_sensor", []),
    # 1 = tied to the utility, 0 = islanded. Numeric rather than a
    # binary_sensor so this component keeps a single entity type.
    "grid_connected": (_plain, "set_grid_connected_sensor", []),
    "load_power": (_power, "set_load_power_sensor", []),
    # ── Battery
    "battery_soc": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_PERCENT,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_BATTERY,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        "set_battery_soc_sensor",
        [],
    ),
    "battery_voltage": (lambda: _voltage(2), "set_battery_voltage_sensor", []),
    # Signed. Positive = DISCHARGING, confirmed on a Deye 8K SG05LP1:
    # with PV at 2 W, grid at 0 W and load at 2705 W the register read
    # +2813 W, so a positive value is power leaving the battery.
    "battery_power": (_power, "set_battery_power_sensor", []),
    # 0x00BF, x0.01 A, same sign as battery_power.
    "battery_current": (lambda: _current(1), "set_battery_current_sensor", []),
    # 0x00B6, x0.1 C with a +100 C offset; NaN when no probe / BMS.
    "battery_temperature": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_CELSIUS,
            accuracy_decimals=1,
            device_class=DEVICE_CLASS_TEMPERATURE,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        "set_battery_temperature_sensor",
        [],
    ),
    # 0x00CC: battery capacity as configured on the inverter (Battery Setting
    # -> Batt Capacity), in Ah.
    "battery_capacity": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_AMPERE_HOURS,
            accuracy_decimals=0,
            state_class=STATE_CLASS_MEASUREMENT,
            icon="mdi:battery-high",
        ),
        "set_battery_capacity_sensor",
        [],
    ),
    # Same capacity in kWh: Ah x battery_nominal_voltage / 1000.
    "battery_capacity_energy": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_KILOWATT_HOURS,
            accuracy_decimals=2,
            device_class=DEVICE_CLASS_ENERGY_STORAGE,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        "set_battery_capacity_energy_sensor",
        [],
    ),
    # ── Energy counters
    "daily_production": (_energy, "set_daily_production_sensor", []),
    "total_production": (_energy, "set_total_production_sensor", []),
    "daily_consumption": (_energy, "set_daily_consumption_sensor", []),
    "total_consumption": (_energy, "set_total_consumption_sensor", []),
    "daily_energy_bought": (_energy, "set_daily_energy_bought_sensor", []),
    "daily_energy_sold": (_energy, "set_daily_energy_sold_sensor", []),
    "daily_battery_charge": (_energy, "set_daily_battery_charge_sensor", []),
    "daily_battery_discharge": (_energy, "set_daily_battery_discharge_sensor", []),
    # ── State
    # Enum from register 0x003B: 0 standby, 1 self-test, 2 normal,
    # 3 alarm, 4 fault. Published raw; label it where it is displayed.
    "device_state": (_plain, "set_device_state_sensor", []),
}

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(SolarmanMinimal),
        # Serial number of the WiFi logger stick.
        # Can be omitted if set at runtime via the "Logger Serial" text entity + web_server.
        cv.Optional(CONF_SERIAL, default=0): cv.uint32_t,
        # Optional: skip UDP discovery and use a fixed IP
        cv.Optional(CONF_HOST): cv.ipv4address,
        # Allow the on-demand /24 sweep for an open port 8899 (start_scan()).
        # Off by default: it is a scan of someone else's network and should be
        # a deliberate choice, not a surprise. Five dongles across four sites
        # never answered a UDP probe while all of them served 8899, so on those
        # this is the only discovery with a chance of working.
        cv.Optional(CONF_TCP_SCAN, default=False): cv.boolean,
        # Used only for battery_capacity_energy. 51.2 V = a 16-cell LiFePO4
        # bank, which is what nearly every 48 V Deye installation runs.
        cv.Optional(CONF_BATTERY_NOMINAL_VOLTAGE, default=51.2): cv.All(
            cv.voltage, cv.float_range(min=1.0, max=1000.0)
        ),
        **{cv.Optional(key): factory() for key, (factory, _, _) in SENSORS.items()},
    }
).extend(cv.polling_component_schema("30s"))


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    cg.add(var.set_serial(config[CONF_SERIAL]))  # 0 = load from flash
    cg.add(var.set_tcp_scan(config[CONF_TCP_SCAN]))
    cg.add(var.set_battery_nominal_voltage(config[CONF_BATTERY_NOMINAL_VOLTAGE]))
    if CONF_HOST in config:
        cg.add(var.set_host(str(config[CONF_HOST])))

    for key, (_, setter, args) in SENSORS.items():
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(getattr(var, setter)(*args, sens))
