# NuaSense for Home Assistant

What your weather station means for your crop, as Home Assistant sensors: tonight's low and whether it is a frost night, the next calm dry window for spraying, whether the station's latest reading is plausible against the model, and the hourly agronomy — ET0, leaf wetness, spray quality, VPD, delta T.

Works with any station NuaSense knows: an Ecowitt, Froggit, Ambient or Wunderground-mode console uploading directly, or anything Home Assistant already sees, forwarded in Wunderground format (see *Sending readings* below). The first three stations on a NuaSense account connect free.

## Install

**HACS (custom repository, until the integration is in the default store):** HACS → Integrations → ⋮ → Custom repositories → add `https://github.com/nuasense/homeassistant-nuasense` as *Integration* → Download → restart Home Assistant.

**By hand:** copy `custom_components/nuasense` into your `config/custom_components/` and restart.

Then Settings → Devices & services → Add integration → **NuaSense**.

## Set up

1. In the NuaSense console make an API key under **API Keys** with the `ingest:write` scope. (Despite the name it is also what reads your own stations.)
2. Paste it into the integration. It lists the stations on your account; pick one. One entry per station.

## Sensors

| Sensor | What it is |
|---|---|
| Tonight's low | °C, with the hour it is expected and the grass-level estimate as attributes |
| Frost tonight | `none`, `watch` (grass level may freeze) or `frost` |
| Next spray window | `07:00–14:00` or `none`; date, wind and the reason as attributes |
| Station check | `plausible`, `check` or `off`: the latest reading against the model for that hour |
| ET0 last hour | mm |
| Leaf wetness, consecutive hours | h, with the reason |
| Spray quality | label, with index, limiting factor and inversion risk |
| Vapour pressure deficit | kPa |
| Delta T | °C |
| Temperature / humidity / pressure, hourly mean | from the station |
| Last upload | when the station last sent, and from which device |

Polled every 15 minutes. The hourly values exist from the first full hour after a station starts sending; the first look needs the station to have a position.

## Sending readings from Home Assistant

The integration reads. To send a station Home Assistant already has, add it in the NuaSense console under **External stations → Add a station** (pick *Home Assistant / weewx / Meteobridge / Node-RED*) and forward its values in Wunderground format to the path shown — for example with a `rest_command` on a time pattern, or with [node-red-contrib-nuasense](https://github.com/nuasense/node-red-contrib-nuasense). A native upload entity for this integration is planned.

## Your data

When you connect a station, NuaSense stores its readings and computes your forecast, spray windows and risks from them. The readings are used aggregated and anonymised to improve forecasts and models for everyone; they are never passed on individually without your opt-in. You can disconnect the station in the console at any time and have all its data deleted.

MIT licence. Issues: https://github.com/nuasense/homeassistant-nuasense/issues
