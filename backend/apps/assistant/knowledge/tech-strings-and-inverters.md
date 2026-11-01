---
title: Strings and inverters
checked: 2026-11-01
---

## Series and parallel wiring of panels
In series (plus to minus), voltages add and current stays the same. Ten 41 V panels in series make about 410 V at the current of one panel. In parallel, currents add and voltage stays the same. Two 13 A strings in parallel make 26 A at one string's voltage. Home on-grid systems normally use series strings because the inverter needs high voltage to start and run.

## How many panels in a string for the maximum voltage
Use the coldest temperature expected at the site, because panel voltage rises in the cold.
Cold Voc = Voc × (1 + coefficient ÷ 100 × (lowest temp - 25)). The Voc coefficient is negative, about -0.27 %/°C.
Example: 49.5 V panel, -0.27, lowest temperature 5°C. Cold Voc = 49.5 × (1 + 0.054) = 52.2 V.
Then max panels = inverter max DC voltage ÷ cold Voc, rounded down. With a 600 V inverter: 600 ÷ 52.2 = 11.5, so 11 panels. Check the sign of the coefficient, because a sign error reverses the correction. Use the real datasheet values.
Source: https://www.greentechrenewables.com/article/solar-inverter-string-design-calculations

## Minimum panels in a string for the MPPT voltage
Hot panels lose voltage. The string's Vmp on a hot roof must stay above the inverter's minimum MPPT voltage.
Hot Vmp = Vmp × (1 + coefficient ÷ 100 × (cell temp - 25)). Use the Vmp coefficient from the datasheet, or the Pmax coefficient as a close stand-in.
Example: 41 V panel, -0.35 %/°C, cell temperature 70°C. Hot Vmp = 41 × (1 - 0.1575) = 34.5 V. With a 120 V MPPT minimum: 120 ÷ 34.5 = 3.5, so at least 4 panels. A string that is too short starts late, stops early and loses generation.
Source: https://www.greentechrenewables.com/article/solar-inverter-string-design-calculations

## Checking the current limit on an MPPT input
Each MPPT input has its own voltage and current limits, so check per input and not per inverter. The string's short-circuit current (Isc) must not exceed the input's rated limit. The US electrical code uses Isc × 1.25 for sizing wires and overcurrent devices, as a safety margin. Two parallel strings on one input double the current, so check that against the inverter datasheet.
Source: https://www.greentechrenewables.com/article/solar-inverter-string-design-calculations

## DC capacity tolerance of 10 percent
In March 2026, MNRE advised DISCOMs to accept up to 10% tolerance in DC capacity on PM Surya Ghar net metering applications. So panel capacity may exceed the applied capacity by up to 10%, as long as the inverter's AC capacity stays within the sanctioned load and regulatory limits. Example: for a 5 kW system with 540 W panels, 9 panels is 4.86 kW and 10 panels is 5.40 kW, both acceptable with a 5 kW inverter. This is an advisory, not binding on DISCOMs, and the report does not say whether it affects the subsidy amount.
Source: https://powerpeakdigest.com/mnre-allows-10-percent-rooftop-solar-dc-tolerance/

## Inverter types: string, hybrid, off-grid and microinverter
An on-grid (string) inverter feeds solar power into the home and grid, and has no backup in a power cut. An off-grid inverter runs from batteries with no grid connection. A hybrid inverter does both: it works with the grid and keeps backup loads running from a battery. A microinverter sits under each panel, so a shaded panel does not pull the others down, but it costs more. Our packages use the inverter set in the reviewed package, so do not swap types on site.

## Where to mount the inverter
Mount it in the shade, with airflow around it, as heat reduces output and life. Keep it out of direct sun and rain, at a height where the display can be read. Keep the DC run short. The MSEDCL specification asks for IP65 or better outdoors and IP54 or better indoors. Follow the clearances in the inverter manual, because the warranty can depend on them.
Source: https://www.mahadiscom.in/ismart/media/Technical%20Spec.pdf
