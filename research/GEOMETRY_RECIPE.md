# Recipe for the researched variant

The two presets are `parameters-exterior.json` and `../interior/parameters-researched.json`. Geometry is deterministic, in metres, with Z up and a common origin at the centre of the ground slab. X/Y orientation is a modelling convention, with no surveyed northing/easting or georeference. The original demo preset is separate. Evidence IDs refer to [EVIDENCE.md](EVIDENCE.md).

## Envelope and levels

The shared generator interpolates **squared radius** at the supplied height/radius knots using shape-preserving cubic Hermite interpolation, then takes the nonnegative square root. This prevents a spline from inventing negative radii or overshooting the supplied maximum. The new anchors include a 179.8 m top, a 56.15 m maximum diameter and a 30 m diameter at the dome base. The dome base is derived as 179.8 − 22 = 157.8 m. Most connecting knots remain assumptions.

For level `i`, the exterior parameter supplies the slab underside `z[i]`. The finished floor is `z[i] + 0.16 + 0.18`: a continuous 160 mm slab proxy, an assumed 30 mm raised-floor panel and a source-supported 150 mm void. The highest supplied slab underside, 166.76 m, therefore gives a 167.10 m finished floor. Typical intervals are 4.15 m; the exceptional ground and top intervals are fitted assumptions. Model numbering is not a verified mapping to the building's floor labels.

Each floor starts with the envelope radius at its slab level, less the 0.40 m facade inset. Six recesses follow the original notch construction. The floor phase is `5° × z / 4.15`. Recesses have an assumed 12° opening and inner radius `max(0.68 × floor_radius, 13.7 m)`. Explicit `full_floor_levels` suppress the recesses at selected levels. That closure schedule is illustrative.

The diagrid retains 18 nodes per ring and alternating connections to the next ring. Nineteen uniformly resampled two-storey bands reach the dome base. The lower and upper member radii use R01's 508 mm and 273 mm diameters; their intermediate linear interpolation is assumed. Tubes are capped polygonal solids, with no steel wall thickness, welds or connections. The facade is sampled into triangles with a closed apex. Panel counts and material opacity remain visual choices.

## Shafts, floors and circulation

The core uses three radial sectors at 0°, 120° and 240°. Six, five and five office shafts give the sourced total of 16 office lifts. Shaft sizes, the bank split, all coordinates and every stop list are inferred. Shaft voids persist through travel levels even where a bank does not serve that floor. Two additional upper shuttle proxies are explicitly assumed; they do not resolve the historical 16-versus-18 lift-count conflict.

Two rotated stair enclosures occupy the same side of the core, and the WC block occupies the opposite side, following the relative arrangement visible in public plans. Stair flights are generated between successive finished-floor elevations, with the tall lobby interval split into two bays. Doors interrupt enclosure walls. Closed leaves are treated as operable in the approach-clearance test. Stair dimensions and occupancy capacity have not been designed to a fire strategy.

Slabs and raised panels contain the rotated shaft/stair/service openings. Horizontal scanline strips use the even/odd rule across the outer polygon and all hole boundaries. Extruding the retained strips produces a closed mesh with real voids. Shared coordinates are canonicalized to a one-micrometre grid to prevent round-off seams. Volume and vertical opening rays are checked after native creation.

## Structure, rooms and furniture

Radial beam proxies use the documented 10° spacing. The assumed core bearing radius is 13.5 m. Each beam is assembled from three closed rectangular members representing a web and two flanges. A ring of core-column candidates, perimeter hoops and a sampled dome lattice adds structural context. Unsupported candidate placements are omitted and recorded; there is no load path or structural-design verification.

Room candidates follow six floor sectors: meeting rooms on alternate fingers, private offices on the others, plus WC and service rooms. An envelope/obstacle filter rejects candidates that do not fit. Office furniture uses a deterministic grid with clearance envelopes, core exclusion, radial aisles, facade setbacks and room/door exclusions. Upper floors can use space vacated by lower lift banks; that reuse is an assumption. The furniture does not reproduce a tenant's current layout.

## Wet services

A 0.5 m routing grid and a breadth-first tree connect reachable destinations to service roots. Admissible grid nodes and edges remain inside the floor profile and avoid protected stair/lift enclosures. Full segment-to-boundary tests reject paths that cross a narrow atrium recess between samples. Selected paths are merged into contiguous segments before geometry is emitted.

Sprinkler mains use a nominal level 3.05 m above finished floor; drops end at 2.70 m. Domestic cold and hot water use separate heights. The drain riser is a schematic placeholder. These dimensions and all pipe radii are assumptions. Sprinkler coverage, flows, pressure zoning, valves, insulation, drainage branches and penetrations are not designed. Four-pipe fan coils carry explicitly unconnected ports for two supply/return pairs; there is no complete hydronic or duct network.

## Electrical and lighting controls

The two source locations reflect evidence of dual supplies, but their allocation is invented: source A serves power, source B lighting. A separate control network represents the documented DALI/LON/BMS system concept. Each level has board/controller proxies. Power routes sit in the raised-floor void; lighting and control routes occupy distinct overhead layers. Vertical wet-pipe drops become routing keepouts.

Each generated workstation requests a floor outlet. Luminaires occupy a filtered grid and room/lobby positions. A source-to-terminal route uses the same deterministic grid tree, followed by a final connection and drop to the component's top centre. Every luminaire also requests a control interface. Groups of at most eight outlets or twelve lights become schedule entries; illustrative control groups use at most 64 addresses. These are modelling choices, not electrical design rules. All voltage, current, conductor and protection fields remain unset.

The network is a geometric connectivity model. It does not show a separate cable for every circuit or every conductor. Boards are equipment symbols, containment is a base-strip proxy, and multisensors are symbols without complete branch wiring. Circuit schedules describe membership; they do not establish isolation, capacity, resilience or compliance.

## Object identity and verification

Semantic component IDs encode role, level and index. Components of compatible category/stage/level are packed into bounded native mesh objects. The mapping records vertex and face slices for each component. MicroStation additionally records native element IDs; Blender uses stable object names. Stage transitions and bounded batches save checkpoints.

Validation reads the saved native vertices and triangles, checks them against the recipe, then evaluates layout constraints using the verified mapping. Electrical endpoints come from actual tube end-ring centroids; terminal positions come from actual terminal meshes. An endpoint index uses 20 micrometre proximity matching, avoiding false disconnections caused by decimal rounding bins. Graph traversal traces terminals to the source. Nominal swept-radius tests compare wet and electrical lines. These limited geometry checks do not establish engineering readiness.
