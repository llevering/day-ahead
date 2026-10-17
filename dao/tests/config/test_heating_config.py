"""
Tests for the heating configuration: the configurable degree-days base temperature
(stookgrens), which falls back to 16 °C when it is not configured, the COP
temperature curve, and the options of the heat pump start/stop model.
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from dao.prog.config.models.devices.heating import (
    HeatingConfig,
    HeatingDisabled,
    HeatingEnabled,
    cop_temperature_factor,
)

STAGES = [{"max_power": 1000, "cop": 4.0}]


def parse_heating(data: dict):
    return TypeAdapter(HeatingConfig).validate_python(data)


def heating_with(base_temperature) -> dict:
    return {
        "heater present": True,
        "stages": STAGES,
        "degree_days_base_temperature": base_temperature,
    }


class TestDegreeDaysBaseTemperature:
    def test_defaults_to_16_when_not_configured(self):
        result = parse_heating({"heater present": True, "stages": STAGES})
        assert isinstance(result, HeatingEnabled)
        assert result.degree_days_base_temperature == 16.0

    def test_configured_value_is_used(self):
        assert parse_heating(heating_with(18.0)).degree_days_base_temperature == 18.0
        assert parse_heating(heating_with(15.5)).degree_days_base_temperature == 15.5

    def test_has_no_alias(self):
        # A new option uses its plain field name as key in options.json; aliases are
        # only kept for older options that need a backwards-compatible key.
        field = HeatingEnabled.model_fields["degree_days_base_temperature"]
        assert field.alias is None

    def test_other_adjustment_modes_get_the_same_default(self):
        result = parse_heating({"heater present": True, "adjustment": "on/off"})
        assert result.degree_days_base_temperature == 16.0

    def test_survives_serialisation(self):
        result = parse_heating(heating_with(17.0))
        assert result.model_dump()["degree_days_base_temperature"] == 17.0

    def test_below_range_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with(-1.0))

    def test_above_range_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with(31.0))

    def test_non_numeric_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with("warm"))

    def test_disabled_heating_needs_no_base_temperature(self):
        result = parse_heating({"heater present": False})
        assert isinstance(result, HeatingDisabled)


CURVE = [
    {"temperature": -4.0, "factor": 0.66},
    {"temperature": 7.0, "factor": 1.0},
    {"temperature": 14.0, "factor": 1.22},
]


def heating_with_curve(curve) -> dict:
    return {"heater present": True, "stages": STAGES, "cop_temperature_curve": curve}


class TestCopTemperatureCurve:
    def test_defaults_to_no_curve(self):
        result = parse_heating({"heater present": True, "stages": STAGES})
        assert result.cop_temperature_curve == []
        assert cop_temperature_factor(result.cop_temperature_curve, -10.0) == 1.0

    def test_factor_at_a_point(self):
        curve = parse_heating(heating_with_curve(CURVE)).cop_temperature_curve
        assert cop_temperature_factor(curve, 7.0) == pytest.approx(1.0)
        assert cop_temperature_factor(curve, -4.0) == pytest.approx(0.66)

    def test_factor_is_interpolated_between_points(self):
        curve = parse_heating(heating_with_curve(CURVE)).cop_temperature_curve
        assert cop_temperature_factor(curve, 10.5) == pytest.approx(1.11)
        assert cop_temperature_factor(curve, 1.5) == pytest.approx(0.83)

    def test_factor_is_clamped_outside_the_curve(self):
        curve = parse_heating(heating_with_curve(CURVE)).cop_temperature_curve
        assert cop_temperature_factor(curve, -15.0) == pytest.approx(0.66)
        assert cop_temperature_factor(curve, 25.0) == pytest.approx(1.22)

    def test_single_point_gives_a_constant_factor(self):
        curve = parse_heating(
            heating_with_curve([{"temperature": 7.0, "factor": 0.9}])
        ).cop_temperature_curve
        assert cop_temperature_factor(curve, -10.0) == pytest.approx(0.9)
        assert cop_temperature_factor(curve, 20.0) == pytest.approx(0.9)

    def test_unsorted_curve_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with_curve(list(reversed(CURVE))))

    def test_duplicate_temperature_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with_curve([CURVE[0], CURVE[0]]))

    def test_non_positive_factor_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(heating_with_curve([{"temperature": 7.0, "factor": 0.0}]))

    def test_survives_serialisation(self):
        dumped = parse_heating(heating_with_curve(CURVE)).model_dump()
        assert dumped["cop_temperature_curve"] == CURVE

    def test_has_no_alias(self):
        field = HeatingEnabled.model_fields["cop_temperature_curve"]
        assert field.alias is None


class TestStartStopOptions:
    def test_defaults_keep_starts_free_and_no_off_time(self):
        result = parse_heating({"heater present": True, "stages": STAGES})
        assert result.min_off_length == 0.0
        assert result.start_cost == 0.0
        assert result.entity_hp_running is None
        assert result.entity_hp_running_since is None

    def test_configured_values_are_used(self):
        result = parse_heating(
            {
                "heater present": True,
                "stages": STAGES,
                "min_off_length": 0.75,
                "start_cost": 0.1,
                "entity_hp_running": "binary_sensor.heatpump_compressor_running",
                "entity_hp_running_since": "sensor.heatpump_compressor_state_since",
            }
        )
        assert result.min_off_length == 0.75
        assert result.start_cost == 0.1
        assert result.entity_hp_running == "binary_sensor.heatpump_compressor_running"
        assert (
            result.entity_hp_running_since == "sensor.heatpump_compressor_state_since"
        )

    @pytest.mark.parametrize("field", ["min_off_length", "start_cost"])
    def test_negative_is_rejected(self, field):
        with pytest.raises(ValidationError):
            parse_heating({"heater present": True, "stages": STAGES, field: -0.5})

    def test_invalid_running_entity_is_rejected(self):
        with pytest.raises(ValidationError):
            parse_heating(
                {"heater present": True, "stages": STAGES, "entity_hp_running": "x"}
            )

    @pytest.mark.parametrize(
        "field",
        [
            "min_off_length",
            "start_cost",
            "entity_hp_running",
            "entity_hp_running_since",
        ],
    )
    def test_has_no_alias(self, field):
        assert HeatingEnabled.model_fields[field].alias is None
