# NuaSense for Home Assistant

What your weather station means for your house and garden, as Home Assistant sensors: tonight's low and whether to bring the pots in, how much the garden needs watering today after the rain that fell and the rain that is coming, and whether your station's reading is plausible.

Works with any station NuaSense knows: an Ecowitt, Froggit, Ambient or Wunderground-mode console uploading directly, or anything Home Assistant already sees, forwarded in Wunderground format. The first three stations on a NuaSense account connect free.

## Install

**HACS (custom repository, until the integration is in the default store):** HACS → Integrations → ⋮ → Custom repositories → add `https://github.com/nuasense/homeassistant-nuasense` as *Integration* → Download → restart Home Assistant.

**By hand:** copy `custom_components/nuasense` into your `config/custom_components/` and restart.

Then Settings → Devices & services → Add integration → **NuaSense**.

## Set up

1. In the NuaSense console make an API key under **API Keys** with the `ingest:write` scope (it is also what reads your own stations).
2. Paste it into the integration and pick your station.
3. Tell it what the garden mostly is — **lawn**, **vegetables** or **flower beds and shrubs** — and your sprinkler's rate in mm per hour (a pop-up sprinkler is about 10, a drip line 2–4; 0 if you only want millimetres).

## Sensors

| Sensor | What it is |
|---|---|
| Tonight's low | °C, with the hour and a grass-level estimate as attributes |
| Frost tonight | `none`, `watch` (grass level may freeze: pots in, cover the tender ones) or `frost` |
| Watering today | mm your garden needs today: what it loses to evaporation, minus the rain of the last 24 hours and the rain forecast for the next 24; `0` means skip. Attributes: ET0, where it came from (your station once it has a day of data, the forecast before), both rain figures |
| Watering time today | minutes at your sprinkler's rate — ready for an automation that opens a valve |
| Rain next 24 h | mm forecast for your position |
| Plausibility | `plausible` or `implausible`: your latest reading against the forecast model for that hour. It flags only differences no weather explains (more than 5 °C), like a wrong unit or a sensor indoors, and names no cause |
| Last upload | when the station last sent, and from what |

Watering is a daily balance, for an automation that runs once a day: water when the sensor is above 0, for the minutes it says.

### Advanced

Switch on **Advanced: agronomy values** for farms, vineyards and nurseries: next spray window, ET0 per hour, consecutive leaf-wetness hours, spray quality, VPD, delta T and the hourly means.

Polled every 15 minutes.

## Sending readings from Home Assistant

The integration reads. To send a station Home Assistant already has, add it in the NuaSense console under **External stations → Add a station** (pick *Home Assistant / weewx / Meteobridge / Node-RED*) and forward its values in Wunderground format to the path shown — for example with a `rest_command` on a time pattern, or with [node-red-contrib-nuasense](https://github.com/nuasense/node-red-contrib-nuasense).

## Your data

When you connect a station, NuaSense stores its readings and computes your forecast and watering from them. The readings are used aggregated and anonymised to improve forecasts and models for everyone; they are never passed on individually without your opt-in. You can disconnect the station in the console at any time and have all its data deleted.

MIT licence. Issues: https://github.com/nuasense/homeassistant-nuasense/issues
