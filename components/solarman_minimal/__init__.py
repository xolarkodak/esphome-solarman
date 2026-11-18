import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import sensor
from esphome.const import (
    CONF_ID,
    CONF_OFFSET,
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
CONF_MODEL = "model"
CONF_MAX_BLOCK_SIZE = "max_block_size"
CONF_BATTERY_NOMINAL_VOLTAGE = "battery_nominal_voltage"
CONF_CUSTOM_SENSORS = "custom_sensors"
CONF_REGISTER = "register"
CONF_TYPE = "type"
CONF_SCALE = "scale"
CONF_SLOW = "slow"
CONF_ZERO_IS_UNKNOWN = "zero_is_unknown"

UNIT_AMPERE_HOURS = "Ah"

# ── Must match the enums in solarman_minimal.h ─────────────────────────────
SP, P3LV, P3HV = 0, 1, 2  # Model
MODELS = {
    "auto": -1,
    "single_phase_lv": SP,  # SUN-xK-SG0xLP1   (ha-solarman deye_hybrid)
    "three_phase_lv": P3LV,  # SUN-xK-SG0xLP3   (ha-solarman deye_p3)
    "three_phase_hv": P3HV,  # SUN-xK-SG0xHP3
}
TYPES = {"u16": 0, "s16": 1, "u32": 2, "s32": 3, "u32_be": 4, "s32_be": 5}
SLOW, ZERO_NAN, BOOL = 1, 2, 4  # RegFlags
ROLE_NONE, ROLE_PV_SUM, ROLE_CAPACITY_AH, ROLE_SOC = 0, 1, 2, 3  # Role


def R(reg, typ="u16", scale=1.0, offset=0.0, flags=0):
    """One register definition: address, type, value = raw * scale + offset."""
    return (reg, TYPES[typ], float(scale), float(offset), flags)


# ── Sensor shapes ──────────────────────────────────────────────────────────
def _power():
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_WATT,
        accuracy_decimals=0,
        device_class=DEVICE_CLASS_POWER,
        state_class=STATE_CLASS_MEASUREMENT,
    )


def _voltage(decimals=1):
    return lambda: sensor.sensor_schema(
        unit_of_measurement=UNIT_VOLT,
        accuracy_decimals=decimals,
        device_class=DEVICE_CLASS_VOLTAGE,
        state_class=STATE_CLASS_MEASUREMENT,
    )


def _current(decimals=1):
    return lambda: sensor.sensor_schema(
        unit_of_measurement=UNIT_AMPERE,
        accuracy_decimals=decimals,
        device_class=DEVICE_CLASS_CURRENT,
        state_class=STATE_CLASS_MEASUREMENT,
    )


def _energy():
    """Every daily/total counter on these inverters is the same shape: kWh at
    one decimal, monotonic within its period."""
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_KILOWATT_HOURS,
        accuracy_decimals=1,
        device_class=DEVICE_CLASS_ENERGY,
        state_class=STATE_CLASS_TOTAL_INCREASING,
    )


def _plain():
    return sensor.sensor_schema(accuracy_decimals=0, state_class=STATE_CLASS_MEASUREMENT)


def _stored_energy():
    return sensor.sensor_schema(
        unit_of_measurement=UNIT_KILOWATT_HOURS,
        accuracy_decimals=2,
        device_class=DEVICE_CLASS_ENERGY_STORAGE,
        state_class=STATE_CLASS_MEASUREMENT,
    )


# ── Profiles ───────────────────────────────────────────────────────────────
#
# key -> (schema factory, {model: R(...)})
#
# SP   single-phase LV hybrid. Field-confirmed on SUN-8K-SG05LP1 (the original
#      set) and SUN-6K-SG05LP1 (values match ha-solarman deye_hybrid). The
#      registers marked "doc" come from the Deye Modbus map and are not yet
#      individually confirmed.
# P3LV three-phase LV hybrid, from the Deye three-phase Modbus map and the
#      ha-solarman deye_p3 profile. NOT yet checked on live hardware.
# P3HV three-phase HV hybrid: the P3LV map with the scales that differ on the
#      high-voltage models (battery voltage, battery and PV power). NOT yet
#      checked on live hardware.
#
# A key with no entry for a model is simply not published on that model; the
# log says so once when the read plan is built.
#
# Adding a model family = one more column here, one more MODELS entry, one
# more enum value and device-type case in C++. Nothing else changes.


def _p3(d):
    """The same definition on both three-phase families. Where HV differs,
    the entry spells out P3LV and P3HV separately instead."""
    return {P3LV: d, P3HV: d}


SENSORS = {
    # ── State
    # Enum: 0 standby, 1 self-test, 2 normal, 3 alarm, 4 fault.
    "device_state": (_plain, {SP: R(0x003B), **_p3(R(0x01F4))}),
    # ── PV strings. PV3/PV4 read 0 on 2-MPPT models.
    **{
        f"pv{n}_power": (
            _power,
            {
                SP: R(0x00BA + n - 1),
                P3LV: R(0x02A0 + n - 1),
                P3HV: R(0x02A0 + n - 1, scale=10),
            },
        )
        for n in range(1, 5)
    },
    **{
        f"pv{n}_voltage": (
            _voltage(1),
            {SP: R(0x006D + 2 * (n - 1), scale=0.1), **_p3(R(0x02A4 + 2 * (n - 1), scale=0.1))},
        )
        for n in range(1, 5)
    },
    **{
        f"pv{n}_current": (
            _current(1),
            {SP: R(0x006E + 2 * (n - 1), scale=0.1), **_p3(R(0x02A5 + 2 * (n - 1), scale=0.1))},
        )
        for n in range(1, 5)
    },
    # ── Grid (the inverter's AC input)
    "grid_voltage": (_voltage(1), {SP: R(0x0096, scale=0.1), **_p3(R(0x0256, scale=0.1))}),
    "grid_voltage_l2": (_voltage(1), _p3(R(0x0257, scale=0.1))),
    "grid_voltage_l3": (_voltage(1), _p3(R(0x0258, scale=0.1))),
    "grid_frequency": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_HERTZ,
            accuracy_decimals=2,
            device_class=DEVICE_CLASS_FREQUENCY,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        {SP: R(0x004F, scale=0.01), **_p3(R(0x0261, scale=0.01))},
    ),
    # Signed; the direction convention is NOT yet confirmed on any model.
    "grid_power": (_power, {SP: R(0x00A9, "s16"), **_p3(R(0x0271, "s16"))}),
    # 1 = tied to the utility, 0 = islanded.
    "grid_connected": (_plain, {SP: R(0x00C2, flags=BOOL)}),
    # ── Load
    "load_power": (_power, {SP: R(0x00B2, "s16"), **_p3(R(0x028D, "s16"))}),
    "load_power_l1": (_power, _p3(R(0x028A, "s16"))),
    "load_power_l2": (_power, _p3(R(0x028B, "s16"))),
    "load_power_l3": (_power, _p3(R(0x028C, "s16"))),
    # ── Battery
    "battery_soc": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_PERCENT,
            accuracy_decimals=0,
            device_class=DEVICE_CLASS_BATTERY,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        {SP: R(0x00B8), **_p3(R(0x024C))},
    ),
    "battery_voltage": (
        _voltage(2),
        {SP: R(0x00B7, scale=0.01), P3LV: R(0x024B, scale=0.01), P3HV: R(0x024B, scale=0.1)},
    ),
    # Signed. Positive = DISCHARGING (confirmed on SP).
    "battery_power": (
        _power,
        {SP: R(0x00BE, "s16"), P3LV: R(0x024E, "s16"), P3HV: R(0x024E, "s16", scale=10)},
    ),
    # Same sign as battery_power.
    "battery_current": (
        _current(1),
        {SP: R(0x00BF, "s16", scale=0.01), **_p3(R(0x024F, "s16", scale=0.01))},
    ),
    # x0.1 C with a +100 C offset; raw 0 = no probe/BMS -> unknown.
    "battery_temperature": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_CELSIUS,
            accuracy_decimals=1,
            device_class=DEVICE_CLASS_TEMPERATURE,
            state_class=STATE_CLASS_MEASUREMENT,
        ),
        {
            SP: R(0x00B6, scale=0.1, offset=-100, flags=ZERO_NAN),
            **_p3(R(0x024A, scale=0.1, offset=-100, flags=ZERO_NAN)),
        },
    ),
    # The inverter's "Batt Capacity" setting, Ah. A setting, so read rarely.
    "battery_capacity": (
        lambda: sensor.sensor_schema(
            unit_of_measurement=UNIT_AMPERE_HOURS,
            accuracy_decimals=0,
            state_class=STATE_CLASS_MEASUREMENT,
            icon="mdi:battery-high",
        ),
        {SP: R(0x00CC, flags=SLOW), **_p3(R(0x0066, flags=SLOW))},
    ),
    # ── Energy counters (x0.1 kWh; totals are 32-bit, low word first)
    "daily_production": (_energy, {SP: R(0x006C, scale=0.1), **_p3(R(0x0211, scale=0.1))}),
    "total_production": (
        _energy,
        {SP: R(0x0060, "u32", scale=0.1), **_p3(R(0x0216, "u32", scale=0.1))},
    ),
    "daily_consumption": (_energy, {SP: R(0x0054, scale=0.1), **_p3(R(0x020E, scale=0.1))}),
    "total_consumption": (
        _energy,
        {SP: R(0x0055, "u32", scale=0.1), **_p3(R(0x020F, "u32", scale=0.1))},
    ),
    "daily_energy_bought": (_energy, {SP: R(0x004C, scale=0.1), **_p3(R(0x0208, scale=0.1))}),
    "daily_energy_sold": (_energy, {SP: R(0x004D, scale=0.1), **_p3(R(0x0209, scale=0.1))}),
    "daily_battery_charge": (_energy, {SP: R(0x0046, scale=0.1), **_p3(R(0x0202, scale=0.1))}),
    "daily_battery_discharge": (
        _energy,
        {SP: R(0x0047, scale=0.1), **_p3(R(0x0203, scale=0.1))},
    ),
}

# Computed in C++ from other registers: key -> (schema, setter, [(source, role)])
DERIVED = {
    # PV1 + PV2 + PV3 + PV4.
    "pv_power": (
        _power,
        "set_pv_total_power_sensor",
        [(f"pv{n}_power", ROLE_PV_SUM) for n in range(1, 5)],
    ),
    # Total capacity: Ah x battery_nominal_voltage.
    "battery_capacity_energy": (
        _stored_energy,
        "set_battery_capacity_energy_sensor",
        [("battery_capacity", ROLE_CAPACITY_AH)],
    ),
    # Energy in the battery right now: capacity x SOC.
    "battery_remaining_energy": (
        _stored_energy,
        "set_battery_remaining_energy_sensor",
        [("battery_capacity", ROLE_CAPACITY_AH), ("battery_soc", ROLE_SOC)],
    ),
}

CUSTOM_SENSOR_SCHEMA = sensor.sensor_schema().extend(
    {
        # Applies whatever model is detected: a custom register is the user's
        # own knowledge of their own inverter.
        cv.Required(CONF_REGISTER): cv.uint16_t,
        cv.Optional(CONF_TYPE, default="u16"): cv.enum(TYPES, lower=True),
        cv.Optional(CONF_SCALE, default=1.0): cv.float_,
        cv.Optional(CONF_OFFSET, default=0.0): cv.float_,
        cv.Optional(CONF_SLOW, default=False): cv.boolean,
        cv.Optional(CONF_ZERO_IS_UNKNOWN, default=False): cv.boolean,
    }
)

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
        # a deliberate choice, not a surprise.
        cv.Optional(CONF_TCP_SCAN, default=False): cv.boolean,
        # Which register map. `auto` reads the device type from register 0x0000;
        # an unknown or unreadable type falls back to single_phase_lv.
        cv.Optional(CONF_MODEL, default="auto"): cv.enum(MODELS, lower=True),
        # Largest Modbus read. 100 is what ha-solarman's deye_hybrid profile
        # reads in one request; lower it if a logger rejects long reads.
        cv.Optional(CONF_MAX_BLOCK_SIZE, default=100): cv.int_range(min=8, max=125),
        # Used only for the kWh figures. 51.2 V = a 16-cell LiFePO4 bank, which
        # is what nearly every 48 V installation runs. Set it for HV banks.
        cv.Optional(CONF_BATTERY_NOMINAL_VOLTAGE, default=51.2): cv.All(
            cv.voltage, cv.float_range(min=1.0, max=1000.0)
        ),
        # Raw value of register 0x0000 - what `model: auto` decided from.
        cv.Optional("device_type"): _plain(),
        cv.Optional(CONF_CUSTOM_SENSORS, default=[]): cv.ensure_list(CUSTOM_SENSOR_SCHEMA),
        **{cv.Optional(key): factory() for key, (factory, _) in SENSORS.items()},
        **{cv.Optional(key): factory() for key, (factory, _, _) in DERIVED.items()},
    }
).extend(cv.polling_component_schema("30s"))


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    cg.add(var.set_serial(config[CONF_SERIAL]))  # 0 = load from flash
    cg.add(var.set_tcp_scan(config[CONF_TCP_SCAN]))
    cg.add(var.set_model(MODELS[config[CONF_MODEL]]))
    cg.add(var.set_max_block_size(config[CONF_MAX_BLOCK_SIZE]))
    cg.add(var.set_battery_nominal_voltage(config[CONF_BATTERY_NOMINAL_VOLTAGE]))
    if CONF_HOST in config:
        cg.add(var.set_host(str(config[CONF_HOST])))

    index = 0

    def bind(sens, role, defs):
        nonlocal index
        cg.add(var.add_binding(sens, role))
        for model, (reg, typ, scale, offset, flags) in defs.items():
            cg.add(var.set_register(index, model, reg, typ, scale, offset, flags))
        index += 1

    for key, (_, defs) in SENSORS.items():
        if key in config:
            sens = await sensor.new_sensor(config[key])
            bind(sens, ROLE_NONE, defs)

    # Derived values get their own hidden inputs, so they work whether or not
    # the source sensors are configured, and a source that is configured is
    # never counted twice. The planner reads each register once regardless.
    for key, (_, setter, sources) in DERIVED.items():
        if key in config:
            sens = await sensor.new_sensor(config[key])
            cg.add(getattr(var, setter)(sens))
            for source, role in sources:
                bind(cg.nullptr, role, SENSORS[source][1])

    if "device_type" in config:
        sens = await sensor.new_sensor(config["device_type"])
        cg.add(var.set_device_type_sensor(sens))

    for conf in config[CONF_CUSTOM_SENSORS]:
        sens = await sensor.new_sensor(conf)
        flags = (SLOW if conf[CONF_SLOW] else 0) | (ZERO_NAN if conf[CONF_ZERO_IS_UNKNOWN] else 0)
        r = (conf[CONF_REGISTER], TYPES[conf[CONF_TYPE]], conf[CONF_SCALE], conf[CONF_OFFSET], flags)
        bind(sens, ROLE_NONE, {m: r for m in (SP, P3LV, P3HV)})
