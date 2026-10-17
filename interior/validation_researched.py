import math
from collections import Counter, defaultdict, deque

from interior.geometry import clear_point, clear_segment, in_rect
from interior.validation import component_mesh, segment_distance_3d


class EndpointIndex:
    def __init__(self, tolerance=0.00002):
        self.tolerance, self.points, self.cells = tolerance, [], defaultdict(list)

    def resolve(self, point, create=True):
        cell = tuple(math.floor(v / self.tolerance) for v in point)
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for dz in (-1,0,1):
                    for index in self.cells[(cell[0] + dx,cell[1] + dy,cell[2] + dz)]:
                        if math.dist(point,self.points[index]) <= self.tolerance:
                            return index
        if not create:
            return None
        index = len(self.points)
        self.points.append(point)
        self.cells[cell].append(index)
        return index


def endpoints(component,objects):
    vertices,_ = component_mesh(component,objects)
    n = component.get('endpoint_ring_size',8)
    return [[sum(p[k] for p in ring) / n for k in range(3)] for ring in (vertices[:n],vertices[n:2 * n])]


def researched_checks(recipe,settings,objects):
    components = {c['id']:c for c in recipe['components']}
    endpoint_index = EndpointIndex()
    graphs, segments, wet, buckets = defaultdict(lambda:defaultdict(set)), [], [], defaultdict(list)
    protected = defaultdict(list)
    for c in recipe['components']:
        if c['role'] in ('stair_enclosure','lift_shaft'):
            protected[c['level']].append(c['footprint'])
        if c['role'] not in ('electrical_route','service_pipe'):
            continue
        a,b = endpoints(c,objects)
        record = {'id':c['id'],'a':a,'b':b,'radius':c['radius_m'],'level':c['level'],'system':c['system']}
        if c['role'] == 'electrical_route':
            graph = graphs[c['system']]
            ka,kb = endpoint_index.resolve(a),endpoint_index.resolve(b)
            graph[ka].add(kb)
            graph[kb].add(ka)
            segments.append(record)
        else:
            index = len(wet)
            wet.append(record)
            low = [math.floor((min(a[k],b[k]) - c['radius_m']) / 2) for k in range(3)]
            high = [math.floor((max(a[k],b[k]) + c['radius_m']) / 2) for k in range(3)]
            for x in range(low[0],high[0] + 1):
                for y in range(low[1],high[1] + 1):
                    for z in range(low[2],high[2] + 1):
                        buckets[(x,y,z)].append(index)
    seen_by_system, disconnected, terminals_checked = {}, [], 0
    for network in recipe['electrical_networks']:
        system = network['system']
        if system not in seen_by_system:
            root = endpoint_index.resolve(network['source_m'],False)
            seen,queue = {root},deque([root])
            while queue:
                node = queue.popleft()
                for nxt in graphs[system][node]:
                    if nxt not in seen:
                        seen.add(nxt)
                        queue.append(nxt)
            seen_by_system[system] = seen
        for identifier in network['terminals']:
            terminals_checked += 1
            c = components[identifier]
            vertices,_ = component_mesh(c,objects)
            ztop = max(p[2] for p in vertices)
            point = [sum(p[k] for p in vertices) / len(vertices) for k in (0,1)] + [ztop]
            key = endpoint_index.resolve(point,False)
            if key is None or key not in seen_by_system[system]:
                disconnected.append(identifier)
    routed_ids = {c['id'] for c in recipe['components'] if c['role'] in ('floor_power_outlet','luminaire_proxy')}
    scheduled = [identifier for circuit in recipe['electrical_circuits'] for identifier in circuit['terminals']]
    counts = Counter(scheduled)
    allocation_errors = sorted((routed_ids ^ set(counts)) | {k for k,v in counts.items() if v != 1})
    luminaire_ids = {c['id'] for c in recipe['components'] if c['role'] == 'luminaire_proxy'}
    missing_controls = sorted(identifier for identifier in luminaire_ids if identifier + '-CONTROL' not in components)
    clash_pairs, checked, obstructions, outside = [], set(), [], []
    for segment in segments:
        a,b,radius = segment['a'],segment['b'],segment['radius']
        low = [math.floor((min(a[k],b[k]) - radius) / 2) for k in range(3)]
        high = [math.floor((max(a[k],b[k]) + radius) / 2) for k in range(3)]
        candidates = set()
        for x in range(low[0],high[0] + 1):
            for y in range(low[1],high[1] + 1):
                for z in range(low[2],high[2] + 1):
                    candidates.update(buckets[(x,y,z)])
        for index in candidates:
            pair = (segment['id'],wet[index]['id'])
            if pair in checked:
                continue
            checked.add(pair)
            pipe = wet[index]
            if segment_distance_3d(a,b,pipe['a'],pipe['b']) < radius + pipe['radius'] - 0.00002:
                clash_pairs.append(pair)
        if abs(a[2] - b[2]) < 1e-5:
            floor = recipe['floors'][segment['level'] - 1]
            if not clear_segment(a[:2],b[:2],floor['profile'],radius):
                outside.append(segment['id'])
            steps = max(1,math.ceil(math.dist(a,b) / 0.1))
            for j in range(steps + 1):
                xy = [a[k] + (b[k] - a[k]) * j / steps for k in (0,1)]
                if any(in_rect(xy,rect,radius) for rect in protected[segment['level']]):
                    obstructions.append(segment['id'])
                    break
    checks = [
        {'check':'electrical_terminals_connected_to_source','pass':not disconnected,'terminals_checked':terminals_checked,'disconnected':disconnected[:30],
         'scope':'Endpoint graph from actual native conduit ring centroids to actual terminal top centres with 20 micrometre proximity matching; no electrical performance calculation'},
        {'check':'electrical_circuit_membership_unique_and_complete','pass':not allocation_errors,'circuits':len(recipe['electrical_circuits']),'errors':allocation_errors[:30]},
        {'check':'every_luminaire_has_control_interface','pass':not missing_controls,'missing':missing_controls[:30]},
        {'check':'electrical_routes_clear_of_wet_pipes','pass':not clash_pairs,'nearby_pairs_tested':len(checked),'clashes':clash_pairs[:30],'total_clashes':len(clash_pairs),
         'scope':'Nominal conduit/pipe radii only; fittings, trays, insulation and required regulatory separation not assessed'},
        {'check':'electrical_routes_avoid_lift_and_stair_enclosures','pass':not obstructions,'obstructions':sorted(set(obstructions))[:30],
         'scope':'Actual horizontal conduit centreline samples at <= 0.1 m against protected enclosure rectangles'},
        {'check':'electrical_horizontal_routes_inside_floorplate','pass':not outside,'outside':sorted(set(outside))[:30]},
    ]
    if recipe.get('variant') == 'researched':
        facade = [o for o in recipe['objects'] if o['category'].startswith('GHR_GLAZING')]
        vertices = [v for obj in facade for v in objects[obj['name']].get('vertices_m',objects[obj['name']].get('vertices'))]
        height = max(v[2] for v in vertices)
        diameter = 2 * max(math.hypot(*v[:2]) for v in vertices)
        top = next(c for c in recipe['components'] if c['role'] == 'raised_floor_panel' and c['level'] == 40)
        top_vertices,_ = component_mesh(top,objects)
        top_ffl = max(v[2] for v in top_vertices)
        gaps = []
        for floor in recipe['floors']:
            slab = next(c for c in recipe['components'] if c['role'] == 'perforated_slab' and c['level'] == floor['level'])
            panel = next(c for c in recipe['components'] if c['role'] == 'raised_floor_panel' and c['level'] == floor['level'])
            sv,_ = component_mesh(slab,objects)
            pv,_ = component_mesh(panel,objects)
            gaps.append(min(v[2] for v in pv) - max(v[2] for v in sv))
        checks.extend([
            {'check':'R01_native_envelope_anchors','pass':abs(height - 179.8) < 0.00002 and abs(diameter - 56.15) < 0.005,
             'height_m':height,'maximum_sampled_diameter_m':diameter,'scope':'Envelope mesh extents, not a full surveyed shape comparison'},
            {'check':'R01_native_highest_finished_floor','pass':abs(top_ffl - 167.1) < 0.00002,'elevation_m':top_ffl},
            {'check':'R02_native_raised_floor_void','pass':all(abs(gap - 0.15) < 0.00002 for gap in gaps),'minimum_m':min(gaps),'maximum_m':max(gaps)},
        ])
    return checks
