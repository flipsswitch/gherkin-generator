# Interior validation record

Recorded on 17 October 2026 using the supplied default parameters. These results establish properties of the generated conceptual model, not its correspondence to the real Gherkin. The [evidence register](EVIDENCE.md) explains that distinction. Machine-readable results are in [validation-summary.json](validation-summary.json).

## Native host runs

| Check | Blender | MicroStation |
| --- | --- | --- |
| Tested host | 4.5.5 LTS, Python 3.11.11 | 2026, version 26.00.02.39, Python 3.12.12 |
| Native mesh objects | 1,013 | 1,013 |
| Vertices / triangles | 680,330 / 1,167,760 | 680,330 / 1,167,760 |
| Native geometry checks | 1,015 passed | 1,014 passed |
| Additional design checks | 48 passed | 48 passed |
| Saved model reloaded independently | Fresh background process; passed | DGN unloaded by opening an empty file, then reopened; passed |
| Coordinate comparison | Maximum error 0.000007616 m | Every mesh below 0.000001 m tolerance |
| Unit scale | One Blender unit per metre | Read from the tested DGN: 10,000 UOR per metre |
| Final build script elapsed time | 143.444 s, including four renders | 138.264 s, including verification and save checkpoints |

Times start inside the entry point and exclude application startup, imports, UI preparation, independent verification, development and earlier failed attempts. They are local measurements, not a 15-minute reproduction claim or a performance guarantee. Native files, full mesh read-back and full logs are generated locally and are not included in the public repository.

Both adapters compare actual native coordinates, triangle indices, object identity and category/style information with the recipe. MicroStation reads persistent element handles. Blender reopens the saved file before reading its mesh data. The additional design checks consume that read-back; they do not merely inspect the intended vertex arrays. Declared furniture and door clearance envelopes remain parameter-based checks associated with the verified geometry.

A separate run of the optional `--glb` branch completed in 100.480 s, including generation and native checks. The exported GLB was parsed independently: all 1,013 expected mesh nodes and 1,167,760 triangles are present, and it has no external buffer references. This is a container/topology check, not a separate geometric round-trip through a third application.

## Scope of passing checks

- All 40 slab meshes have the expected volume and clear shaft-opening centres. Non-glazing solids are closed, consistently oriented and have positive volume. The original glazing remains an open shell at its base.
- The largest native mesh has 3,584 vertices and 6,272 triangles, below the configured bounds.
- All 1,920 sampled stair treads have supporting mesh geometry. The minimum measured vertical headroom in the Blender model is 3.794786 m against the specified slab, stair, landing, core-wall and column surfaces. This does not test every point in a stair enclosure or establish regulatory compliance.
- All 4,260 generated sprinkler terminals connect to the modeled fire riser. The graph is recovered from native pipe geometry. Hydraulic performance and connection to an external water supply are unverified.
- The pipe check tests 7,966 nearby pairs from different systems and finds no intersection between their nominal swept radii. Same-system joints, fittings, insulation and interactions with all other building systems are outside that check.
- Declared workstation/cafe clearance rectangles do not overlap each other. Door approach rectangles do not intersect the other tested enclosures. Continuous accessible routes, exit capacity and door-swing operation have not been certified or comprehensively tested.

The generator records 169 rejected candidates: 48 rooms fail footprint/envelope clearance and 121 service candidates have no connected route within the current concept. These omissions are visible in `design-status.json`; they are not silently claimed as completed coverage. Sprinkler spacing and coverage are not fire-protection design calculations.

## Generated content

The default concept contains 23,914 interior components, including 374 rooms, 680 door leaves, 1,634 desks and matching chairs, 150 meeting tables, 600 meeting chairs, six lift cars, 160 stair flights, two plant rooms, 12,160 pipe segments and 4,260 sprinkler heads. These are generated quantities, not researched quantities for the building.

The two stairs connect the original slab schedule through the omitted entrance slab. The concept's outer lifts end at L37, its middle lifts at L39, and its stairs reach L40. Step-free access to L40 is unresolved. Heating equipment, tanks, pumps and air handlers are simplified geometric proxies. Drain branches, ducts, electrical distribution, fire stopping, pressure zoning and a complete structural framing system are not designed.

## Regression tests and corrections

All 16 standard-library tests passed using Python 3.12.14: eight original geometry tests and eight interior tests. Interior tests cover the complete scoped design checks, unchanged exterior mesh fingerprints, a concave slab with multiple true holes, component mapping/evidence, pipe-distance edge cases, failure on missing native geometry, an obstructed door approach and invalid/unbounded settings. The original 89 facade/diagrid mesh fingerprints and root parameter file are unchanged.

Development checks exposed obstructed washroom door approaches and water takeoffs crossing other risers; their layouts and routes were corrected. A first MicroStation attempt passed geometry verification but failed during view fitting because of a stale module binding. The final adapter imports the view API directly and completed a new build, save and reopen verification. Initial renders were overexposed; the final images use lower lighting energy. These corrections occurred before the recorded successful release runs.

## Previews and release hygiene

The four preview PNGs are real Blender renders of generated geometry. The floor, furnished and services views use L20; the cutaway temporarily clips the building. The saved native model retains the complete geometry. PNG text/EXIF metadata was removed without changing the image pixel stream.

Publication review checks the selected source tree for credential patterns, personal email addresses, machine paths, private environment identifiers, unexpected binaries and image metadata. The public package contains the standalone adapters, original procedural geometry, declared assumptions, tests and curated previews. It contains no private MCP implementation, local application seed, native model, raw execution log or native read-back. Pattern scanning is a release hygiene check, not a guarantee that every possible secret format can be detected.
