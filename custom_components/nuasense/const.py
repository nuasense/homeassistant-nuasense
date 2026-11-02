"""Constants for the NuaSense integration."""

DOMAIN = "nuasense"

CONF_BASE_URL = "base_url"
CONF_STATION_ID = "station_id"

DEFAULT_BASE_URL = "https://api.nuasense.com"
# The hourly computation changes once an hour; the first look once the forecast
# model has run. Fifteen minutes keeps "tonight" fresh without hammering the API.
SCAN_INTERVAL_MINUTES = 15

ATTRIBUTION = "Data and agronomy by NuaSense; forecast via met.no"
