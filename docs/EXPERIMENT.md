# From an MCP experiment to two scripts

The original experiment asked whether an existing custom MicroStation MCP could create a Gherkin-like native model from a prepared geometry contract. It was inspired by Bentley's public account of Stuart Milne's demonstration. Our custom MCP remains private. This repository contains a new Python port of the geometry and direct adapters for the applications' native scripting interfaces.

The supplied research was frozen on 19 September 2026. It distinguished building facts, public reconstruction conventions and deliberately approximate parameters before the modeling run. We did not obtain the demonstrator's original notebook, input collection, script, DGN or uncut timing record. The source register preserves these limits. No original building asset was imported.

## What the original clock measured

| Milestone | Elapsed time |
| --- | --- |
| Setup before the timed run | 10 min 2.194 s |
| Complete geometry saved during the run | 11 min 33.6 s |
| 448 native geometry checks complete | 14 min 56.8 s |
| Full delivery, including captures and remaining evidence | 29 min 57.6 s |

The user explicitly authorized continuation beyond 15 minutes. The full delivery exceeded 900 seconds. We therefore do not claim an end-to-end 15-minute reproduction of Bentley's demo. The initial experiment used MicroStation 26.00.02.39 and custom MCP version 0.6.3.

The scripts are prepared replay programs. Their execution times exclude the research, code development, debugging, application startup and review needed to create them. A fast script replay is not equivalent to the original reasoning-and-modeling benchmark.

## Conversion decisions

`gherkin.py` implements the shared equations with the Python standard library. It retains the original radius interpolation, elevations, 102-point recessed slab outlines, eight-sided member proxies, facade triangulation, batching and stable logical IDs. Both adapters construct application-native geometry directly and inspect the geometry that the application actually stores.

MicroStation uses 40 native solid primitives and 89 native mesh elements. In the tested host, the 33 recessed floors persist as ruled-sweep solids and the seven circular floors as cone primitives with equal radii. The original MCP build used SmartSolids for its floors. The underlying boundaries, thicknesses and volumes agree; internal native element types are not identical. Four named levels improve organization over the original single-level build.

Blender uses 129 editable mesh objects and native materials. Its seven circular floors are approximated with 512 sides, with maximum chord deviation below 0.514 mm for the defaults. The recessed floor outlines, framing and glass mesh topology retain the original geometry. Blender's floating-point storage introduces micrometre-scale coordinate differences. It adds a camera, lighting and actual rendered views. The models are geometrically equivalent within the documented tolerances, not byte-identical files or identical rendered appearances.

The framing consists of closed solid prism proxies; they are not hollow structural sections. Adjacent members meet on a common node lattice but remain separate closed shells within their batches. The facade is an exterior surface with an open bottom. The cutaway render opens the geometry at a plane for inspection and does not create an engineered section or a separately validated building solid.

## Scope of the release

The release includes the scripts, frozen parameters, original mathematical recipe, attributed research notes, a sanitized geometric regression fixture and generated Blender previews. It excludes the custom MCP, server code, local configuration, raw conversation/tool logs, native installation files, seed files, credentials and machine-specific launch helpers.

Native DGN and Blender files are generated locally by the scripts rather than embedded in the source repository. Those binary formats can carry application or environment metadata. The public regression fixture retains only logical object names, geometry fingerprints, coordinates and volumes from native read-back; it contains no original process, session or review identifiers.
