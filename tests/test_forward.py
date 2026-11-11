"""The pure half of forwarding: picking a station's sensors and building the upload.

    python3 -m unittest discover -s tests
"""

import importlib.util
import sys
import pathlib
import unittest

SPEC = importlib.util.spec_from_file_location(
    "forward", pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "nuasense" / "forward.py"
)
forward = importlib.util.module_from_spec(SPEC)
sys.modules["forward"] = forward  # dataclasses look the module up while the class is built
SPEC.loader.exec_module(forward)
C = forward.Candidate

# Entity names as the Ecowitt and Netatmo integrations create them.
ECOWITT = [
    C("sensor.gw2000a_outdoor_temperature", "temperature", "°C", "GW2000A Outdoor Temperature"),
    C("sensor.gw2000a_indoor_temperature", "temperature", "°C", "GW2000A Indoor Temperature"),
    C("sensor.gw2000a_dewpoint", "temperature", "°C", "GW2000A Dewpoint"),
    C("sensor.gw2000a_feels_like_temperature", "temperature", "°C", "GW2000A Feels Like Temperature"),
    C("sensor.gw2000a_outdoor_humidity", "humidity", "%", "GW2000A Outdoor Humidity"),
    C("sensor.gw2000a_indoor_humidity", "humidity", "%", "GW2000A Indoor Humidity"),
    C("sensor.gw2000a_absolute_pressure", "atmospheric_pressure", "hPa", "GW2000A Absolute Pressure"),
    C("sensor.gw2000a_relative_pressure", "atmospheric_pressure", "hPa", "GW2000A Relative Pressure"),
    C("sensor.gw2000a_wind_speed", "wind_speed", "km/h", "GW2000A Wind Speed"),
    C("sensor.gw2000a_wind_gust", "wind_speed", "km/h", "GW2000A Wind Gust"),
    C("sensor.gw2000a_max_daily_gust", "wind_speed", "km/h", "GW2000A Max Daily Gust"),
    C("sensor.gw2000a_wind_direction", None, "°", "GW2000A Wind Direction"),
    C("sensor.gw2000a_rain_rate", "precipitation_intensity", "mm/h", "GW2000A Rain Rate"),
    C("sensor.gw2000a_daily_rain", "precipitation", "mm", "GW2000A Daily Rain"),
    C("sensor.gw2000a_total_rain", "precipitation", "mm", "GW2000A Total Rain"),
    C("sensor.gw2000a_solar_radiation", "irradiance", "W/m²", "GW2000A Solar Radiation"),
    C("sensor.gw2000a_soil_moisture_1", "moisture", "%", "GW2000A Soil Moisture 1"),
]
NETATMO = [
    C("sensor.garden_temperature", "temperature", "°C", "Garden Temperature"),
    C("sensor.garden_humidity", "humidity", "%", "Garden Humidity"),
    C("sensor.living_room_temperature", "temperature", "°C", "Living room Temperature"),
    C("sensor.living_room_pressure", "atmospheric_pressure", "mbar", "Living room Pressure"),
    C("sensor.rain_gauge_precipitation_today", "precipitation", "mm", "Rain gauge Precipitation today"),
    C("sensor.rain_gauge_precipitation_last_hour", "precipitation", "mm", "Rain gauge Precipitation last hour"),
    C("sensor.anemometer_wind_speed", "wind_speed", "km/h", "Anemometer Wind speed"),
    C("sensor.anemometer_gust_strength", "wind_speed", "km/h", "Anemometer Gust strength"),
    C("sensor.anemometer_wind_direction", None, "°", "Anemometer Wind direction"),
]


class Pick(unittest.TestCase):
    def test_ecowitt_outdoor_absolute_daily(self):
        m = forward.pick(ECOWITT)
        self.assertEqual(m["temperature"], "sensor.gw2000a_outdoor_temperature")
        self.assertEqual(m["humidity"], "sensor.gw2000a_outdoor_humidity")
        self.assertEqual(m["pressure"], "sensor.gw2000a_absolute_pressure")
        self.assertEqual(m["wind_speed"], "sensor.gw2000a_wind_speed")
        self.assertEqual(m["wind_gust"], "sensor.gw2000a_wind_gust")
        self.assertEqual(m["wind_direction"], "sensor.gw2000a_wind_direction")
        self.assertEqual(m["rain"], "sensor.gw2000a_daily_rain")
        self.assertEqual(m["solar"], "sensor.gw2000a_solar_radiation")

    def test_netatmo_rate_is_not_a_total(self):
        m = forward.pick(NETATMO)
        self.assertEqual(m["temperature"], "sensor.garden_temperature")
        self.assertEqual(m["rain"], "sensor.rain_gauge_precipitation_today")
        self.assertEqual(m["wind_gust"], "sensor.anemometer_gust_strength")
        self.assertNotIn("solar", m)

    def test_rain_keys(self):
        self.assertEqual(forward.rain_key(C("sensor.x_daily_rain", "precipitation", "mm", "Daily Rain")), "dailyrainin")
        self.assertEqual(forward.rain_key(C("sensor.x_total_rain", "precipitation", "mm", "Total Rain")), "totalrainin")
        self.assertIsNone(forward.rain_key(C("sensor.x_rain_rate", "precipitation", "mm", "Rain Rate")))
        self.assertIsNone(forward.rain_key(C("sensor.x_last_hour", "precipitation", "mm", "Precipitation last hour")))

    def test_pressure_param(self):
        self.assertEqual(forward.pressure_param_for(ECOWITT[6]), "baromabsin")
        self.assertEqual(forward.pressure_param_for(NETATMO[3]), "baromin")


class Query(unittest.TestCase):
    def test_metric_becomes_imperial(self):
        m = forward.pick(ECOWITT)
        states = {
            "sensor.gw2000a_outdoor_temperature": ("20.0", "°C"),
            "sensor.gw2000a_outdoor_humidity": ("63", "%"),
            "sensor.gw2000a_absolute_pressure": ("1013.25", "hPa"),
            "sensor.gw2000a_wind_speed": ("10", "km/h"),
            "sensor.gw2000a_wind_gust": ("18", "km/h"),
            "sensor.gw2000a_wind_direction": ("270", "°"),
            "sensor.gw2000a_daily_rain": ("25.4", "mm"),
            "sensor.gw2000a_solar_radiation": ("500", "W/m²"),
        }
        q = forward.to_query(states, m, "dailyrainin", "baromabsin")
        self.assertEqual(q["tempf"], "68.00")
        self.assertEqual(q["humidity"], "63.0")
        self.assertEqual(q["baromabsin"], "29.921")
        self.assertEqual(q["windspeedmph"], "6.21")
        self.assertEqual(q["windgustmph"], "11.18")
        self.assertEqual(q["winddir"], "270")
        self.assertEqual(q["dailyrainin"], "1.000")
        self.assertEqual(q["solarradiation"], "500.0")

    def test_unavailable_and_unknown_units_are_left_out(self):
        m = {"temperature": "sensor.t", "humidity": "sensor.h", "pressure": "sensor.p", "wind_speed": "sensor.w"}
        states = {"sensor.t": ("unavailable", "°C"), "sensor.h": ("140", "%"), "sensor.p": ("1000", "furlongs"), "sensor.w": ("3", "m/s")}
        q = forward.to_query(states, m, None, "baromin")
        self.assertEqual(q, {"windspeedmph": "6.71"})

    def test_fahrenheit_and_inhg_pass_through(self):
        q = forward.to_query({"sensor.t": ("68", "°F"), "sensor.p": ("29.92", "inHg")}, {"temperature": "sensor.t", "pressure": "sensor.p"}, None, "baromin")
        self.assertEqual(q, {"tempf": "68.00", "baromin": "29.920"})


if __name__ == "__main__":
    unittest.main()
