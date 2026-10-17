# Geometry recipe

Read parameters.json. Every parameter has an evidence classification. This document
is an original, implementable approximation assembled for this experiment. It is
not Stuart Milne's code or a transcription of Bentley's demonstration.

## 1. Coordinates and common envelope

Use metres and a local Z-up frame. Convert at the CAD boundary, not inconsistently
inside different generators. The glass envelope is the common radial reference r(z).

Let each profile knot be (z_i, r_i). Interpolate q_i = r_i**2 with a shape-preserving
piecewise cubic Hermite interpolant, then r(z) = sqrt(max(0, q(z))). Interpolating
squared radius gives a rounded approach to the apex without creating a ring of
coincident vertices at the tip. All these profile knots are our visual approximation.

A dependency-free implementation can use the following standard mathematical construction.
For each interval h_i = z_(i+1)-z_i and d_i = (q_(i+1)-q_i)/h_i.
For an interior knot, set its slope m_i to zero when either adjacent secant is zero
or they differ in sign. Otherwise use
  w1 = 2*h_i + h_(i-1)
  w2 = h_i + 2*h_(i-1)
  m_i = (w1+w2)/(w1/d_(i-1) + w2/d_i).
At the first endpoint use
  m_0 = ((2*h_0+h_1)*d_0-h_0*d_1)/(h_0+h_1).
Set this slope to zero if its sign differs from d_0; when d_0 and d_1 differ in
sign, cap its magnitude at 3*abs(d_0). Mirror this rule for the last endpoint.
For t=(z-z_i)/h_i, evaluate
  q(z) = (2*t**3-3*t**2+1)*q_i
       + (t**3-2*t**2+t)*h_i*m_i
       + (-2*t**3+3*t**2)*q_(i+1)
       + (t**3-t**2)*h_i*m_(i+1).
Reject elevations outside the specified range. Do not install a library just for
this interpolation; an existing compatible numerical library is also acceptable.

A point on a ring is
  P(z, theta, inset) = ((r(z)-inset)*cos(theta),
                       (r(z)-inset)*sin(theta), z).
Angles in the parameter file are degrees; convert before trigonometry.

Create an optional low-detail envelope on GHR_GUIDES for early silhouette checking.
Hide it in final views so it cannot conceal the detailed facade.

## 2. Floors and actual atrium recesses

Create the 40 slabs at the explicit elevations, not 40 equally spaced slabs all the
way to the apex. The ground-to-first-upper-slab gap is intentionally double height.

At elevation z, floor outer radius is R = r(z)-0.75. The notch inner radius is 0.68*R.
The six notch centers are
  phi_a(z) = 5*(z/4.2) + 60*a degrees, a=0..5.
Each notch spans 12 degrees, centered on phi_a. These are selected approximation
parameters, not surveyed atrium dimensions.

Build a closed floor outline with six radial recesses: follow the outer circle
outside the notches and the inner circle inside them, joining with radial edges.
Use a supported concave-profile extrusion to make a 0.25-metre-thick slab, or
triangulate the complete polygon and make a closed mesh with side walls. Avoid
fragile repeated boolean subtraction when an explicit boundary will do.

A naive fan from the center can produce collinear triangles or T-junctions at
radial steps. Use a valid polygon triangulation, or a native profile operation
already proven by the scratch test. Do not leave zero-area faces.

For this visual model only, leave the slab complete whenever its regular-height
module index round(z/4.2) is divisible by six. That is an adopted reconstruction
convention, not evidence of code-compliant compartmentation.

Keep one logical group per slab regardless of how many native objects it uses.
Use the prescribed rotation for non-circular features. Rotating a plain circle
alone cannot express a spiral.

## 3. Diagrid body: a shared, staggered node lattice

For k=0..20 and j=0..17, define
  z_k = 8.4*k
  theta_(k,j) = 20*j + 10*k degrees
  N_(k,j) = P(z_k, theta_(k,j), 0.35).

For each k=0..19 and j=0..17, create both edges
  N_(k,j) -> N_(k+1,j)
  N_(k,j) -> N_(k+1,(j-1) modulo 18).

This produces the two intersecting diagonal families from common nodes, with
21 node rings, 378 nodes, and 720 unique member segments. A complete rhombus
occupies two such vertical bays. These are expected counts for OUR recipe.

Use 0.15-metre-radius tube proxies, eight-sided closed mesh tubes, or supported
native sweeps. They are visual members, not engineering sections. Keep the native
representation and member-ID mapping in the output manifest. Generating mesh tubes
in a batch is acceptable; importing a downloaded Gherkin asset is not.

The principal lattice ends at z=168. The crown is a separate facade cap in this
simplification; do not claim a fully engineered crown structure.

## 4. Glazing and crown

Use 72 points per ring, j=0..71. Regular ring elevations are z=2.1*t for t=0..80.
Append the seven crown elevations in parameters.json. For EVERY ring use
  theta_(z,j) = 5*j + 5*z/4.2 degrees
  V_(z,j) = P(z, theta_(z,j), 0).

Thus the fine glazing grid and the coarse diagrid use consistent angular phase.
The structure is slightly inside the skin. These are sampling choices for our
implementation, not an as-built panel schedule.

For two consecutive nonzero-radius rings L and U, add triangles, with indices
wrapped modulo 72:
  (L_j, L_(j+1), U_j)
  (L_(j+1), U_(j+1), U_j).
Verify outward winding in the actual coordinate convention.

Create ONE apex vertex (0,0,180). Close the last ring with 72 triangles
  (last_j, last_(j+1), apex).
Never create 72 coincident apex vertices or a final strip of zero-area quads.
The full facade recipe has 6,337 vertices and 12,600 triangular faces. It is an
exterior surface, not a watertight building solid; its base rim is intentionally open.

Classify each face by its centroid. Compute its azimuth and compare it with the
six phi_a(z) spiral centers from the floor recipe, using a wrapped angular difference.
Use dark glazing when the nearest difference is within 6 degrees, otherwise clear.
This creates an approximation of the spiral glazing pattern. It is NOT an exact
reconstruction of the original panel color schedule.

Use native materials/display properties where supported. Opacity defaults are in
parameters.json; map opacity versus transparency correctly for the actual API.
Split geometry into manageable native mesh groups by vertical band and appearance.
Preserve per-face logical IDs in the manifest. Do not issue 12,600 chat/tool calls.

## 5. Organization, persistence, and views

Use the specified levels or valid host equivalents. Maintain stable IDs for each
floor, member, and facade face. Only retry or replace this run's objects.

Save the native model and generator source. Capture an overall isometric, an
orthographic elevation, and a cutaway/visibility-controlled view that shows recesses
rather than hiding all floor geometry behind glazing. Captures must come from CAD.

## 6. Read-back checks

Inspect the actual saved CAD geometry, not only the proposed arrays or success text.
Check the envelope height (excluding member radii and annotations), radii at the
specified profile knots, 40 logical slab groups at the prescribed elevations,
six recesses on appropriate sample floors, both diagonal families, and crown closure.

Check for duplicate member IDs, seam gaps, non-finite coordinates, invalid faces,
and save failure. Apply parameters.json tolerances. Logical components and native
CAD element counts are not necessarily identical; report both accurately.

Checks requiring unavailable host read-back capabilities must be NOT VERIFIED.
A successful numerical recipe is not proof that geometry exists in the CAD host.
Do not describe this model as structurally validated or as-built.
