# Public evidence for the researched variant

Reviewed 17 October 2026. This register supplements the original `SOURCES.md`; it does not rewrite the provenance of the original demo. The original parameter files remain available unchanged.

The researched model combines documented building facts, observations from public plans, and explicit design assumptions. It is not an as-built reconstruction. A source describing a system does not establish the coordinates, dimensions, capacities or routing of our generated components.

| ID | Primary source | Supported information | Model use and limit |
| --- | --- | --- | --- |
| R01 | Dominic Munro, Arup, [Swiss Re's Building, London](https://www.archidiap.com/beta/assets/uploads/2016/03/doc_14.pdf), *Nyheter om Stålbyggnad* 3/2004, pp. 36–43; author article hosted by an architectural archive | p.38: six fingers, 1.5 m planning grid, 5° floor progression, steel core. pp.39/41: radial framing at 10°; 160 mm composite slab. p.42: 30 m diameter, 22 m high dome. p.43: 179.8 m top; 167.1 m highest occupied floor; 56.15 m maximum diameter at level 17; 4.15 m office module; diagrid diameters 508 mm at ground–L2 and 273 mm at L36–38. | Numeric anchors and structural types adopted. Connecting envelope, slab datum, exceptional floors, member interpolation, core dimensions and dome lattice remain inferred. Ribbed decking is represented by a continuous slab. |
| R02 | [A.K.A. The Gherkin — The Building](https://akathegherkin.com/the-building/), first-party leasing material | 16 high-speed, 21-person passenger lifts; 150 mm raised-floor void; 2.75 m clear height; four-pipe fan coils. | Office lift count and service types adopted. A further assumed 30 mm panel gives 180 mm raised construction. Lift sizes, locations, travel and fan-coil port geometry are inferred. |
| R03 | First-party [floors 3 and 8](https://thegherkin.work/downloads/The_Gherkin_Floorplans.pdf), [level 10 open-plan option](https://akathegherkin.com/wp-content/uploads/2021/03/30StMaryAxe_Floor10_OpenPlan.pdf), [level 14 open-plan option](https://akathegherkin.com/wp-content/uploads/2021/03/30StMaryAxe_Floor14_OpenPlan.pdf) | Plan observations: approximately circular core; three radial bank/lobby sectors; separated stairs on one side; WC accommodation on the opposite side. Plans show different mixes of private offices, meeting rooms and open desks. | Relative topology informed the model. Drawings are indicative/not to scale; fit-outs may change. Coordinates were not surveyed or recovered from CAD. The procedural fit-out does not reproduce a particular tenant. |
| R04 | [First-party December 2025 brochure](https://thegherkin.com/availability/wp-content/uploads/2025/12/The-Gherking-brochure-December-2025.pdf), pp.4, 7, 10 | Dual power supply; independent fresh air per floor; 2.75 m clear height. Lift transfer floors labelled 21/22; accommodation stairs illustrated at 19–25. Typical plans and suggested fit-outs. | Two schematic electrical sources and transfer-level evidence. Circuit allocation and bank stop lists are assumptions. Accommodation stairs are recorded but omitted because their exact geometry is unavailable. |
| R05 | [Delmatic — 30 St Mary Axe](https://delmatic.com/project/30-st-mary-axe/), installed lighting-control supplier | DALI lighting control; LON/BMS integration; occupancy/daylight multisensors; extension of base-build controls into tenant fit-outs. | Luminaires, controller/interface and sensor proxies added. Addresses, group sizes, cable paths and sensor positions are illustrative, not a recovered commissioning configuration. |
| R06 | [Building the Gherkin — Facts and Figures](https://www.buildingthegherkin.com/pdf/factsandfigures.pdf), historical project press material | Rounded 180 m height and 18 passenger lifts. | Historical cross-check. The scope difference from R02's 16 lifts is unresolved. Two extra upper shuttle proxies are an explicit modelling choice, not proof that this explains the difference. |
| R07 | [Tyréns Hilson Moran — 30 St Mary Axe](https://www.tyrenshm.com/projects/30-st-mary-axe/), project services engineer | Shell/core and original Swiss Re fit-out engineering; mixed-mode ventilation and integrated openable facade. | Context for system types. No publicly accessible coordinated services drawings or capacities were established from this page. |
| R08 | [Denton — Level 30 refurbishment](https://www.denton.co.uk/projects/an-upgrade-for-new-potential-clients-at-the-gherkin-30-st-mary-axe), fit-out contractor | Mechanical/electrical refurbishment, air-handling work and WC alterations. | Evidence that interiors and services change over time. A single present-day interior cannot be inferred by combining all dated sources. |
| R09 | [Speirs Major — 30 St Mary's Axe](https://www.speirsandmajor.com/projects/410/30-st-mary-s-axe), project lighting designer | Entrance, core and atrium lighting approach. | Qualitative reference only; our rectangular office luminaires are layout proxies, not the installed product schedule. |

## Architectural v3 evidence

Further dimensions in the existing primary documents are used in v3: R01 p.42 specifies fabricated triangular dome sections of **110 × 150 mm**; p.43 gives **40 mm** wall thickness for the **508 mm** lower diagrid CHS and **12.5 mm** for the **273 mm** upper CHS. R06 specifies a **2.4 m diameter** apex glass lens. Gross dimensions are represented; interpolation, polygonal approximation and unknown connection details remain explicit.

| ID | Primary source | Supported information | Model use and limit |
| --- | --- | --- | --- |
| R10 | [Foster + Partners' project description, hosted by ArchDaily](https://www.archdaily.com/928285/30-st-mary-axe-tower-foster-plus-partners), explicitly attributed to the architects | 7 m aluminium lobby panels; landscaped plaza with trees and low stone seating walls; upper dining/bar uses; triangular and diamond facade panels and ventilated glazing cavity. | V3 adopts the panel height and qualitative architecture. Site dimensions, tenant layouts and facade subdivisions remain inferred. No glass fabrication schedule is reconstructed. |
| R11 | [Boon Edam's supplier contribution, hosted by Archello](https://archello.com/es/project/30-st-mary-axe), Swiss Re section | Four Crystal Tourniket all-glass revolving doors supplied and installed. | Four revolving-door proxies. The source does not establish installed diameter, leaf count or coordinates. Search-index text was available; direct page retrieval was restricted. |
| R12 | [Searcys at The Gherkin, 2022 summer brochure](https://searcys.co.uk/wp-content/uploads/2022/05/Searcys_at_The_Gherkin_Summer_Brochure.pdf), operator's plans, PDF pages 5 and 7 (printed 8–9 and 12–13) | Iris is shown as an open, approximately D-shaped mezzanine with a circular stair; Helix has a lift lobby; five private dining rooms occupy level 38. | V3 replaces the repeated core on the highest floor with that qualitative topology and adds five dining-room proxies. Mezzanine scale, all coordinates, stair geometry, room rectangles, furniture and correspondence with model indices are inferred. These marketing diagrams are not coordinated construction drawings. |
| R13 | [Sociability, Searcys at The Gherkin](https://desktop.sociability.app/venuedetails/searcys-at-the-gherkin-30-st-mary-axe-london), first-hand access observations dated October 2024 | Upstairs bar reached by curved stairs or a small lift. | Supports the existence of a bar-access lift. Its assumed central position, size and travel are not established by a surveyed asset schedule. No compliance conclusion is adopted. |

The four user-supplied images are observations, not measured drawings: **U01** is the exterior aerial, **U02** the dome interior/apex surround, **U03** the entrance chevrons/recessed glazing, and **U04** the architectural cutaway. They guide appearance and presentation only. The images, local filenames and metadata are not distributed. U04 does not establish an actual tenant fit-out or coordinates of hidden systems.

V3 ends its two inferred transfer shuttles at model L39 and adds a separate small bar-access lift proxy. This is an arrangement for the procedural model, not a reconciliation of the historical 16/18 passenger-lift totals. Main-stair termination, bar access, service penetrations and fire separation require verified drawings before engineering use.

## Conflicts and unresolved information

- **Lift totals:** 16 in R02 versus 18 in R06. No verified asset schedule reconciles them. The model contains 16 office shaft/car proxies plus two assumed upper shuttles. The 6/5/5 bank split and every travel limit remain assumptions.
- **Floor numbering:** public sources use differing storey conventions. `L01`–`L40` are model indices, with L01 at ground. Mapping to published floor labels is approximate. The exceptional lobby and upper intervals are fitted, not measured.
- **Envelope:** rounded 180 m in the original preset remains unchanged. The researched preset uses R01's 179.8 m anchor and a 157.8 m dome base derived from its 22 m rise. Most profile knots and all glazing panel counts remain computational choices.
- **Public plans:** several show proposed fit-outs, and the existing layouts are subject to change. We use their core topology without claiming their desks, doors or partitions are a current survey.
- **Engineering gaps:** no coordinated electrical single-line diagrams, cable schedules, hydraulic schematics, sprinkler layouts, load schedules, fire strategy or construction model were obtained. Search results for other nearby towers and unattributed student reconstructions were excluded as technical evidence.

## Parameter and component provenance

`parameters-exterior.json` carries the new envelope anchors. `../interior/parameters-researched.json` separates source-supported dimensions from assumed locations and dimensions. Generated components include `evidence` and `source_ids`; empty source IDs mean there is no component-specific building evidence.

The stair poses, 13.5 m core bearing radius, 6/5/5 lift arrangement, WC dimensions and repeated room layouts are our own approximations based on visible topology. The top levels reuse space after lower lift banks terminate; that reuse and the retained circulation radius are assumptions. Structural proxy sizes are not engineered. Electrical circuits have no assigned voltage, amperage, conductor size or protective device.

The source documents and their drawings retain their respective rights. They are linked, not included or relicensed. The Unlicense applies to this repository's original code, parameter choices and prose, not to third-party source material.

## Reference fingerprints

These identify the public documents inspected, without distributing their drawings or contact details.

| Document | SHA-256 |
| --- | --- |
| R01, 8 pages | `a250816a63a8d3ecb0d18f6fc7150bde69b9b989bb265c94e4a39d5d08615a7b` |
| R03, floors 3/8, 1 page | `dd6877169898e9521c17fe9884701b89eb6718d088a048016446147d49fee52e` |
| R03, level 10, 1 page | `c8eac2b67e428cc4bf0416012b6c7abe8cf469fa4f9ff64476fb481da13eb6fd` |
| R03, level 14, 1 page | `cb9a874d061c4604e80c2edc0b21b137856cc06d700a1ab8a04d4eebd3b9be7e` |
| R04, 25 pages | `3288dfe5a308736c4307ae1b00f4e6393eb12136127846220d106dc141652d74` |
| R12, 15 pages | `69b04c304ea65447b1ca8f074bc673b3adc7a392da4fd2c2f640dcf134375f4e` |
