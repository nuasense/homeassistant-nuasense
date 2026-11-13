# NuaSense for Home Assistant

Works with the weather station you already have in Home Assistant: Ecowitt, Netatmo, Ambient, Tempest, WeatherLink and others. What your weather station means for your house and garden, as Home Assistant sensors: tonight's low and whether to bring the pots in, how much the garden needs watering today after the rain that fell and the rain that is coming, and whether your station's reading is plausible.

Consoles that upload to NuaSense directly (Ecowitt, Froggit, Ambient, Wunderground mode) work too. The first three stations on a NuaSense account connect free.

## Install

**HACS (custom repository, until the integration is in the default store):** HACS → Integrations → ⋮ → Custom repositories → add `https://github.com/nuasense/homeassistant-nuasense` as *Integration* → Download → restart Home Assistant.

**By hand:** copy `custom_components/nuasense` into your `config/custom_components/` and restart.

Then Settings → Devices & services → Add integration → **NuaSense**.

## Set up

1. In the NuaSense console make an API key under **API Keys** with the `ingest:write` scope (it is also what reads your own stations).
2. Paste it into the integration and pick your station: one already on your NuaSense account, or a weather station Home Assistant already shows.
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
| Data quality | `A` to `D`, graded once a day: every value is checked as it arrives, and the station is compared with the weather model, the nearest official station and stations nearby. Attributes: what is wrong and what to fix, one line per sensor. `not_graded` until there is a day of data |
| Last upload | when the station last sent, and from what |

Watering is a daily balance, for an automation that runs once a day: water when the sensor is above 0, for the minutes it says.

### Advanced

Switch on **Advanced: agronomy values** for farms, vineyards and nurseries: next spray window, ET0 per hour, consecutive leaf-wetness hours, spray quality, VPD, delta T and the hourly means.

Polled every 15 minutes.

### Disease and pest risk

Open the integration's **Configure** and pick the crops you grow (potato, tomato, onion, cabbage, kale, pepper, carrot and more). Each crop gets a sensor: `high`, `medium`, `low` or `not_judged`, the highest risk your station's own weather gives it, computed hourly with NuaSense's crop models (late blight, early blight, mildews, rusts and others). The attributes list every threat with its level, how complete the data was and what to check on the plants.

Threats your station cannot judge come back as `not_judged` with the reason, never as `low`: soil-borne diseases need a soil probe, and insect clocks need a planting date. It is weather risk, not a diagnosis: a high level means conditions favour the disease, so look at the crop.

## Sending a station Home Assistant already has

Already have an Ecowitt, Netatmo, Ambient, Tempest, WeatherLink or any other weather station in Home Assistant? Choose **A weather station Home Assistant already shows** in the setup dialog. The integration finds the station's outdoor temperature, humidity, pressure, wind, rain and solar sensors (you can change each one), registers the station on your NuaSense account with the position set in Home Assistant, and sends its readings to NuaSense every five minutes over HTTPS. No console, no forwarding rule. The station counts as one of the free stations on the account.

Rain is sent only from a running total (rain today, or a total), never from a rate.

## Your data

When you connect a station, NuaSense stores its readings and computes your forecast and watering from them. The readings are used aggregated and anonymised to improve forecasts and models for everyone; they are never passed on individually without your opt-in. You can disconnect the station in the console at any time and have all its data deleted.

MIT licence. Issues: https://github.com/nuasense/homeassistant-nuasense/issues
