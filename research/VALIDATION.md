# Researched variant validation

Tests performed on Windows on 17 October 2026. [validation-summary.json](validation-summary.json) records counts, measurements, source hashes and limitations. This is validation against the procedural recipe, not an as-built survey or engineering approval.

## Application results

| Preset | Application | Result |
| --- | --- | --- |
| Original exterior | Blender 5.2.1 LTS | Created, saved, reopened and rendered; 131 native checks passed |
| Researched exterior | Blender 5.2.1 LTS | Created, saved, reopened and rendered; 131 native checks passed |
| Earlier conceptual interior | Blender 5.2.1 LTS | Created, saved, reopened and rendered; 1,015 native checks and 48 layout checks passed |
| Researched interior with electrical | Blender 5.2.1 LTS | 2,433 native checks and 57 geometry/layout checks passed; repeated successfully in a fresh process |
| Researched interior with electrical | MicroStation 2026 | Created, saved, fully unloaded and reopened; 2,432 native checks and 57 layout checks passed again |
| Earlier original exterior and conceptual interior | Blender 4.5.5 LTS and MicroStation 2026 | Earlier tests passed; see the [original](../docs/VALIDATION.md) and [conceptual interior](../interior/VALIDATION.md) reports |

The researched variant was run with the Blender **5.2** executable, not the installed 4.5 backup. Blender identified itself as **5.2.1 LTS**, build `9e2066aef7ef`, with Python 3.13.13. This researched variant has not been host-tested in Blender 4.5. The geometry regression tests use ordinary Python; they are distinct from native application tests.

## Saved geometry

The researched interior contains **2,431 mesh objects**, **80,673 mapped components**, **1,580,210 vertices** and **2,722,468 triangles**. It has 40 perforated structural slabs and 40 raised-floor panels, 160 stair flights, 16 office lift cars plus two assumed upper shuttles, 305 rooms, 828 door leaves and 2,020 workstations.

Electrical includes 2,020 floor outlets, 4,042 luminaires, 4,042 control-interface proxies, 1,024 sensor symbols, 80 distribution-board proxies, 40 controller proxies, 622 circuit groups and 120 floor/system networks. The native endpoint graph connects all **10,104 tested power, lighting and control terminals**. Sensor symbols and hydronic stubs are explicitly excluded from a claim of complete network connectivity.

| Native measurement or check | Result |
| --- | --- |
| Largest coordinate difference from generated recipe | 0.000007631 m, within the 0.00002 m Blender tolerance |
| Envelope top | 179.800003 m |
| Maximum sampled envelope diameter | 56.149985 m |
| Highest finished floor | 167.100006 m |
| Raised-floor void across 40 levels | 0.149994–0.150009 m |
| Stair tread rays | 2,240 supported; minimum sampled vertical headroom 3.782965 m |
| Connected sprinkler terminals | 4,583 |
| Nearby different wet-pipe pairs tested | 10,270; zero nominal-radius intersections |
| Nearby wet/electrical pairs tested | 171,957; zero nominal-radius intersections |
| Largest mesh object | 3,946 vertices and 7,976 triangles |

Floor volumes/opening rays, positive closed solids, circuit membership, luminaire controls, protected-core routing, floor boundaries, door approaches and furniture clearance envelopes also pass. Geometry is read from the reopened native file; intended metadata alone is insufficient. A regression test moves a saved-route endpoint while leaving metadata unchanged and verifies that connectivity fails.

## Execution and captures

The final Blender script took **258.454 seconds** from entry to completion, including generation, checkpoint saves, native read-back, validation, GLB export and six renders. Application startup, imports, research, code development and the subsequent independent verification are outside that timer. This is a prepared-script replay measurement, not a reproduction of the original 15-minute development experiment.

The original and researched exterior-only scripts took 27.591 and 29.428 seconds respectively, including their three renders. Timings come from one machine and are not performance guarantees.

The earlier conceptual interior also passed in Blender 5.2.1, taking 101.191 seconds including four renders. Its shared slab triangulator now canonicalizes coordinates at one micrometre and supports rotated openings; its layout remains separate from the researched preset. Historical 4.5 counts and source hashes remain in the earlier report.

MicroStation 2026 version 26.00.02.39, with Python 3.12.12 and 10,000 UOR per metre, completed native generation, bounded checkpoint saves and geometry validation in 341.273 seconds. The user started this run through Python Editor after a hidden test instance prevented initial access to the DGN. The DGN was subsequently unloaded by opening a disposable placeholder, then reopened from disk. The verifier read all 2,431 saved native meshes again; all 2,432 native checks and all 57 layout/network checks passed. The maximum native coordinate difference is approximately 1.44 × 10⁻¹⁴ m. No private MCP was used to generate or verify this version.

The GLB container, all 2,431 expected mesh-node names and all 2,722,468 exported triangles were checked. It has no external buffer dependency. An independent import into another application has not been geometrically validated.

Six interior captures were rendered from the reopened Blender geometry. The plan views show model L17; its assumed lower bank has already terminated. The power capture exposes the underfloor routes by hiding raised panels. The temporary cutaway does not change the saved full model. Published PNGs have ancillary metadata removed with identical compressed pixel streams.

## Regression tests and resolved failures

A full local suite of 23 tests passed. After adding the native-endpoint precision regression, the final researched subset of eight tests passed; the suite now contains 24 tests. Tests cover the original exterior's unchanged mesh fingerprints, rotated openings, narrow-recess routing, researched anchors, lift assumptions, parameter bounds and actual-geometry connectivity. GitHub Actions runs all tests on Windows and Linux with Python 3.10 and 3.12. CI does not run Blender or MicroStation.

Development exposed rotated-opening seams, routes crossing narrow atrium notches and precision-sensitive endpoint matching. Shared-coordinate canonicalization, complete segment checks and distance-based endpoint indexing resolved those failures. One intermediate Blender attempt failed when source files changed during execution; the final builds used stable files. Another attempt reported four false electrical disconnections before the endpoint-index fix. These failed attempts are not reported as successful runs.

Blender reported nonfatal permission warnings for its application cache/thumbnail folders and a future API deprecation. The final processes exited successfully, and saved-file read-back and images passed. Two parameter evidence strings were clarified after the build; the numerical inputs did not change, and fresh-process native verification also passed against the final public parameters.

## Limits

The generator recorded **606 omissions or rejected candidates**. Their reasons are summarized in the JSON report; complete IDs accompany generated models in `design-status.json`. The rendered plans and inferred rooms were visually reviewed, but the tests do not constitute a complete multi-trade clash review. Fittings, insulation, tray clearances and mandatory service separations are not covered by the nominal-radius checks.

No survey, coordinated construction drawings, circuit ratings, load calculations, hydraulic design, fire strategy, exact shaft geometry or current tenant fit-out was obtained. Full HVAC distribution, drainage branches, basement, documented accommodation stairs, and the exact rooftop restaurant layout remain incomplete. Source-supported facts and every unresolved conflict are listed in [EVIDENCE.md](EVIDENCE.md).
