"""Constants for the NuaSense integration."""

DOMAIN = "nuasense"

CONF_BASE_URL = "base_url"
CONF_STATION_ID = "station_id"
CONF_PLANT = "plant"
CONF_SPRINKLER_RATE = "sprinkler_mm_per_h"
CONF_ADVANCED = "advanced"

DEFAULT_BASE_URL = "https://api.nuasense.com"
# What the garden mostly is; decides the watering sensor's crop coefficient.
PLANTS = ["lawn", "vegetables", "beds"]
DEFAULT_PLANT = "lawn"
# A typical pop-up sprinkler; drip lines run 2-4 mm/h. 0 = no minutes sensor.
DEFAULT_SPRINKLER_RATE = 10.0
# The hourly computation changes once an hour; the first look once the forecast
# model has run. Fifteen minutes keeps "tonight" fresh without hammering the API.
SCAN_INTERVAL_MINUTES = 15

ATTRIBUTION = "Data and agronomy by NuaSense; forecast via met.no"
