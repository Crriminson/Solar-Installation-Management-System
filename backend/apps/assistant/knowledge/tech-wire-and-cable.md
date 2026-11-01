---
title: Wire and cable
checked: 2026-11-01
---

## How to measure a cable run on site
Measure the path the cable will actually take, never the straight line. Use a tape or measuring wheel along the route: from the panels, along the roof, around the parapet, down the wall, through any wall entry, to the inverter, and on to the ACDB and meter point. Use a laser distance meter for heights. Add the vertical drops and every bend. Measure each section once (DC from array to inverter, AC from inverter to the meter point) and write down the one-way length. A DC run needs a positive and a negative cable, so 15 m one way uses 30 m of cable.

## How to tell what size a cable is
Read the sheath first. It prints the type and size, for example H1Z2Z2-K 1x4 mm² or 1x6 mm². If there is no print, or you doubt it, cut the sheath back and measure with a vernier caliper. For a solid conductor, area = 3.14 × diameter × diameter ÷ 4. A 2.26 mm solid wire is about 4 mm². Solar cable is stranded, so count the strands, measure one strand, and multiply: 56 strands of 0.30 mm is 56 × 0.0707 = about 4 mm². Measure the bare metal, not the insulation. Cheap cable is often undersized, so test a sample if the brand is unknown.

## Converting AWG to square millimetres
AWG is the American wire gauge, and a smaller number means a thicker wire. 14 AWG is about 2.08 mm². 12 AWG is about 3.31 mm². 10 AWG is about 5.26 mm². 8 AWG is about 8.37 mm². 6 AWG is about 13.3 mm². Datasheets from foreign makers may use AWG, so convert before comparing with our metric cable.

## How to calculate voltage drop on a DC cable
Voltage drop (V) = 2 × one-way length (m) × current (A) × cable resistance (ohm per km) ÷ 1000. The 2 is there because current goes out and back. Use the string's Imp as current. Then percent drop = voltage drop ÷ string Vmp × 100.
Resistance in ohm per km: 2.5 mm² 8.21, 4 mm² 5.09, 6 mm² 3.39, 10 mm² 1.95.
Example: 4 mm² cable, 20 m one way, 13.5 A, 350 V string. Drop = 2 × 20 × 13.5 × 5.09 ÷ 1000 = 2.75 V. Percent = 2.75 ÷ 350 × 100 = 0.8%, which passes the 2% limit.

## Resistance of copper solar cable by size
Use these approximate values for tinned copper flexible cable, in ohm per km at 20°C. 2.5 mm²: 8.21. 4 mm²: 5.09. 6 mm²: 3.39. 10 mm²: 1.95. 16 mm²: 1.24. Plain copper is slightly lower. Resistance rises as the cable heats up, so leave margin on a hot roof. Use the cable maker's datasheet for an exact figure.
Source: https://help.easy-pv.co.uk/books/faqs/page/how-is-dc-cable-sizing-and-voltage-drop-calculated

## Voltage drop limit for solar cables
The MSEDCL rooftop technical specification limits voltage drop to less than 2% on the DC side and a maximum of 2% on the AC side. Other guides use different targets, from 1% to 3%, so 2% is the working figure to use here. That MSEDCL document is a 2021 tender specification, so check the current requirement of the DISCOM you are working with.
Source: https://www.mahadiscom.in/ismart/media/Technical%20Spec.pdf

## Should I use 4 mm² or 6 mm² DC cable
4 mm² copper is the common choice for a single string on a home system. Step up to 6 mm² for a long run, for strings in parallel, for high-current modules, or whenever the voltage drop on 4 mm² goes over the 2% limit. To find the longest run allowed: max length (m) = allowed drop in volts × 1000 ÷ (2 × current × resistance). Example: 2% of 350 V is 7 V, at 13.5 A on 4 mm²: 7 × 1000 ÷ (2 × 13.5 × 5.09) = about 50 m. On 6 mm² it is about 76 m. Always check the package's specified cable first.
Source: https://reonic.com/en-gb/blog/4mm-or-6mm-solar-cable

## How to size the AC cable from the inverter
Current = inverter watts ÷ 230 for single phase. A 5 kW inverter gives 5000 ÷ 230 = 21.7 A. Use the same drop formula with 230 V. Example: 6 mm², 20 m one way: 2 × 20 × 21.7 × 3.39 ÷ 1000 = 2.94 V, and 2.94 ÷ 230 × 100 = 1.3%, which passes the 2% limit. For three phase, the MSEDCL specification requires the neutral to be the same size as the phase wires.
Source: https://www.mahadiscom.in/ismart/media/Technical%20Spec.pdf

## Rules for DC cable on a rooftop job
From the MSEDCL rooftop specification: use multi-strand annealed copper on the DC side, and never use multi-core cable for DC. Cable should be flexible, UV protected and rated for -10°C to +80°C at 660/1000 V, and suited to the 25-year life of the panels. Route cable in RPVC pipe or GI cable tray with covers. Tag cables with ferrules so they can be identified. Clamp cables and conduit at intervals not exceeding 50 cm. Do not leave cable lying on the roof or hanging from connectors.
Source: https://www.mahadiscom.in/ismart/media/Technical%20Spec.pdf

## Cable colours and polarity
Use red for DC positive and black for DC negative where the cable is coloured. If it is all one colour, mark each end with a red or black sleeve. In India AC wiring normally uses red, yellow and blue for phases, black for neutral and green for earth. Do not rely on colour alone: check polarity with a multimeter before connecting a string to the inverter.

## How to test a cable after installing it
Check continuity with a multimeter. Check DC polarity and open-circuit voltage of each string before connecting it: it should be about module Voc times the number of modules. Insulation testing with a megger finds damaged insulation, and needs the string disconnected from the inverter first, because the test voltage can damage electronics. Record the results on the installation form.
