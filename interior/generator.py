import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import gherkin
from interior.geometry import area, box, clear_point, clear_segment, combine, corners, in_rect, inside, local_xy, mesh_health, overlaps, perforated_slab, segment_distance, stair_flight, transform, tube


COLORS = {
    'INT_SLABS': ((0.48, 0.52, 0.56), 8),
    'INT_CORE': ((0.70, 0.73, 0.76), 8),
    'INT_STAIRS': ((0.67, 0.70, 0.73), 8),
    'INT_RAILS': ((0.18, 0.23, 0.26), 7),
    'INT_LIFTS': ((0.29, 0.38, 0.43), 7),
    'INT_SUPPORTS': ((0.22, 0.29, 0.32), 8),
    'INT_PARTITIONS': ((0.86, 0.82, 0.73), 8),
    'INT_DOORS': ((0.37, 0.22, 0.12), 6),
    'INT_DESKS': ((0.67, 0.46, 0.25), 6),
    'INT_SEATING': ((0.10, 0.27, 0.31), 5),
    'INT_FIXTURES': ((0.91, 0.93, 0.94), 0),
    'INT_PLANT': ((0.20, 0.42, 0.48), 5),
    'INT_FIRE': ((0.73, 0.10, 0.055), 3),
    'INT_COLD': ((0.055, 0.28, 0.75), 1),
    'INT_HOT': ((0.88, 0.42, 0.06), 6),
    'INT_DRAIN': ((0.27, 0.20, 0.15), 6),
    'INT_LIGHTS': ((0.98, 0.93, 0.70), 4),
    'INT_POWER': ((0.92, 0.58, 0.025), 4),
    'INT_CONTROLS': ((0.46, 0.17, 0.72), 7),
    'INT_BOARDS': ((0.16, 0.24, 0.35), 1),
    'INT_RAISED': ((0.64, 0.66, 0.63), 8),
    'INT_HVAC': ((0.13, 0.58, 0.49), 2),
    'INT_FRAME': ((0.27, 0.35, 0.40), 7),
}


def load_settings(path=None):
    data = json.loads(Path(path or ROOT / 'interior/parameters.json').read_text(encoding='utf-8'))
    validate_settings(data)
    return data


def validate_settings(p):
    def finite(v):
        if isinstance(v, dict):
            return all(finite(x) for x in v.values())
        if isinstance(v, list):
            return all(finite(x) for x in v)
        return not isinstance(v, (int, float)) or math.isfinite(v)
    if not finite(p) or p['units'] != 'metres':
        raise ValueError('Interior settings require finite numbers in metres')
    for group in ('stairs', 'lifts', 'service_shafts', 'rooms', 'fitout', 'services', 'mesh_limits', 'validation'):
        for name, value in p[group].items():
            if isinstance(value, (int, float)) and value <= 0:
                raise ValueError(group + '.' + name + ' must be positive')
    if not 4 <= p['stairs']['risers_per_flight'] <= 16 or not isinstance(p['stairs']['risers_per_flight'], int):
        raise ValueError('Stair riser count is outside the supported range')
    if p['stairs']['door_width_m'] >= p['stairs']['flight_width_m'] * 2:
        raise ValueError('Stair door does not fit its enclosure')
    if not 0.4 <= p['services']['routing_grid_m'] <= 1 or not 4 <= p['services']['head_grid_multiple'] <= 12:
        raise ValueError('Service sampling must remain bounded')
    if not isinstance(p['services']['head_grid_multiple'], int) or not 6 <= p['services']['pipe_radial_sides'] <= 16:
        raise ValueError('Invalid service mesh sampling')
    if not 16 <= p['mesh_limits']['components_per_object'] <= 128:
        raise ValueError('Component batches must be bounded')
    if not 8192 <= p['mesh_limits']['vertices_per_object'] <= 32768 or not 16384 <= p['mesh_limits']['triangles_per_object'] <= 65536:
        raise ValueError('Mesh limits are outside the supported range')
    for key in ('office_levels', 'amenity_levels'):
        if len(p[key]) != 2 or not 1 <= p[key][0] <= p[key][1] <= 40:
            raise ValueError('Invalid level range')
    if any(not isinstance(n, int) or not 1 <= n <= 40 for n in p['plant_levels']):
        raise ValueError('Invalid plant level')
    if any(v <= 0 for key in ('shaft_size_m',) for v in p['lifts'][key]):
        raise ValueError('Shaft dimensions must be positive')
    if p['rooms']['door_height_m'] >= p['rooms']['partition_height_m']:
        raise ValueError('Door head must be below the partition top')
    if p['fitout']['desk_m'][0] >= p['fitout']['workstation_clearance_m'][0] or p['fitout']['desk_m'][1] >= p['fitout']['workstation_clearance_m'][1]:
        raise ValueError('Workstation clearance must contain the desk')
    for group, key, size in [('lifts', 'shaft_size_m', 2), ('service_shafts', 'size_m', 2), ('rooms', 'service_size_m', 2),
                             ('rooms', 'meeting_size_m', 2), ('fitout', 'desk_m', 3), ('fitout', 'grid_m', 2), ('fitout', 'workstation_clearance_m', 2)]:
        value = p[group][key]
        if len(value) != size or any(not isinstance(v, (int, float)) or not 0 < v <= 20 for v in value):
            raise ValueError('Invalid dimension vector: ' + group + '.' + key)
    if p.get('variant') != 'researched' and (p['service_shafts']['centres_x_m'] != [-4.0, 4.0] or p['services']['routing_grid_m'] != 0.5):
        raise ValueError('Interior v1 reserves service roots at x = -4 and +4 on a 0.5 m routing grid')
    if p.get('variant') == 'researched':
        from interior.researched import validate_researched_settings
        validate_researched_settings(p)


class Builder:
    def __init__(self, exterior, settings):
        self.base = gherkin.generate(exterior)
        self.exterior, self.settings = exterior, settings
        self.radius = gherkin.radius_function(exterior['profile_knots_z_radius_m'])
        self.objects, self.components, self.rooms, self.doors = [], [], [], []
        self.floors, self.walks, self.networks, self.omissions = [], [], [], []
        self.groups = {}
        self.ids = set()
        self.lifts = []
        for y in settings['lifts']['centres_y_m']:
            for x in settings['lifts']['centres_x_m']:
                cy = y - math.copysign(0.2, y) if abs(x) < 1e-8 else y
                self.lifts.append({'id': f'LIFT-{len(self.lifts) + 1:02d}', 'rect': [x, cy, *settings['lifts']['shaft_size_m'], 0],
                                   'last_level': settings['lifts']['middle_last_level'] if abs(x) < 1e-8 else settings['lifts']['outer_last_level']})

    def add(self, identifier, category, stage, level, mesh, role, **metadata):
        if identifier in self.ids:
            raise ValueError('Duplicate stable ID: ' + identifier)
        self.ids.add(identifier)
        vertices, faces = mesh
        if not vertices or not faces:
            raise ValueError('Empty component: ' + identifier)
        limits = self.settings['mesh_limits']
        if len(vertices) > limits['vertices_per_object'] or len(faces) > limits['triangles_per_object']:
            raise ValueError('Component exceeds a bounded native mesh: ' + identifier)
        key = (stage, level, category)
        batches = self.groups.setdefault(key, [])
        if not batches or len(batches[-1]['component_ids']) >= limits['components_per_object'] or len(batches[-1]['vertices']) + len(vertices) > limits['vertices_per_object'] or len(batches[-1]['triangles']) + len(faces) > limits['triangles_per_object']:
            batches.append({'name': f'INT-S{stage}-L{level:02d}-{category[4:]}-{len(batches):03d}',
                            'category': category, 'kind': 'mesh', 'color': COLORS[category][1], 'opacity': 1.0,
                            'stage': stage, 'level': level, 'vertices': [], 'triangles': [], 'component_ids': []})
        obj = batches[-1]
        vo, fo = len(obj['vertices']), len(obj['triangles'])
        obj['vertices'].extend(vertices)
        obj['triangles'].extend([[i + vo for i in f] for f in faces])
        obj['component_ids'].append(identifier)
        self.components.append({'id': identifier, 'role': role, 'stage': stage, 'level': level,
                                'evidence': 'assumed', 'object': obj['name'], 'vertex_offset': vo, 'vertex_count': len(vertices),
                                'face_offset': fo, 'face_count': len(faces),
                                'bounds_m': [[min(p[k] for p in vertices) for k in range(3)], [max(p[k] for p in vertices) for k in range(3)]], **metadata})
        return identifier

    def fits(self, rect, floor, height=1, margin=0.15):
        pts = corners(rect, margin)
        pts += [[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] for a, b in zip(pts, pts[1:] + pts[:1])]
        radius = self.radius(floor['ffl'] + height) - self.exterior['floor_radial_inset_m']
        return all(clear_point(p, floor['profile'], margin) and math.hypot(*p) <= radius - margin for p in pts)

    def shell_and_core(self):
        s, p = self.settings['stairs'], self.exterior
        run = s['risers_per_flight'] * s['going_m']
        width = 2 * s['flight_width_m'] + s['central_gap_m']
        total = run + 2 * s['landing_length_m']
        self.stair_poses = s.get('poses_m_radians', [[cx, 0, 0] for cx in s['centres_x_m']])
        self.stair_rects = [[x, y, width + 2 * s['wall_m'], total + 2 * s['wall_m'], angle] for x, y, angle in self.stair_poses]
        self.stair_holes = [[*local_xy(rect, 0, s['landing_length_m'] / 2), width, run + s['landing_length_m'], rect[4]] for rect in self.stair_rects]
        self.shaft_rects = self.settings['service_shafts'].get('rectangles_m_radians', [[cx, 0, *self.settings['service_shafts']['size_m'], 0] for cx in self.settings['service_shafts']['centres_x_m']])
        for i, obj in enumerate(self.base['objects'][:p['floor_count']]):
            level, z = i + 1, obj['elevation']
            profile = obj['profile'] if obj['profile'] else [[obj['radius'] * math.cos(j * math.tau / 512), obj['radius'] * math.sin(j * math.tau / 512)] for j in range(512)]
            next_z = p['floor_elevations_m'][i + 1] if i + 1 < p['floor_count'] else z + 3.4
            lifts = [a for a in self.lifts if a.get('first_level', 1) <= level <= a['last_level']]
            holes = self.stair_holes + [a['rect'] for a in lifts] + self.shaft_rects
            floor = {'level': level, 'id': f'L{level:02d}', 'slab_z': z, 'ffl': z + p['slab_thickness_m'] + self.settings.get('raised_floor_m', 0), 'next_z': next_z,
                     'radius': obj['radius'], 'phase': self.base['floors'][i]['phase_degrees'], 'profile': profile,
                     'openings': holes, 'lifts': [a['id'] for a in lifts], 'obstacles': list(self.stair_rects),
                     'rooms': [], 'furniture': [], 'service_destinations': []}
            self.floors.append(floor)
            self.add(f'INT-L{level:02d}-SLAB', 'INT_SLABS', 1, level, perforated_slab(profile, holes, z, p['slab_thickness_m']), 'perforated_slab', openings=holes)
            if self.settings.get('raised_floor_m'):
                panel = self.settings['raised_panel_m']
                self.add(f'INT-L{level:02d}-RAISED', 'INT_RAISED', 1, level,
                         perforated_slab(profile, holes, floor['ffl'] - panel, panel), 'raised_floor_panel', openings=holes,
                         evidence='R02 dimension; continuous panel proxy; pedestal layout omitted')
            if obj['profile']:
                for edge, (a, b) in enumerate(zip(profile, profile[1:] + profile[:1])):
                    if min(math.hypot(*a), math.hypot(*b)) >= obj['radius'] - 0.1:
                        continue
                    parts = [tube([*a, floor['ffl'] + 1.1], [*b, floor['ffl'] + 1.1], 0.025)]
                    posts = max(1, math.ceil(math.dist(a, b) / 1.2))
                    for j in range(posts + 1):
                        xy = [a[k] + (b[k] - a[k]) * j / posts for k in (0, 1)]
                        parts.append(tube([*xy, floor['ffl']], [*xy, floor['ffl'] + 1.1], 0.018))
                    self.add(f'INT-L{level:02d}-ATRIUM-GUARD-{edge:03d}', 'INT_RAILS', 1, level, combine(parts), 'atrium_guardrail_proxy')
            height = next_z - floor['ffl']
            for k, rect in enumerate(self.stair_rects):
                self.enclosure(f'INT-L{level:02d}-STAIR-{k + 1}', rect, floor, height, s['wall_m'], s['door_width_m'], 'INT_CORE', 1, 'stair_enclosure')
            for lift in lifts:
                a = self.settings['lifts']
                rect = list(lift['rect'])
                rect[2] += 2 * a['wall_m']
                rect[3] += 2 * a['wall_m']
                if self.settings.get('variant') != 'researched':
                    rect[4] = math.pi if rect[1] < 0 else 0
                floor['obstacles'].append(rect)
                self.enclosure(f'INT-L{level:02d}-{lift["id"]}', rect, floor, height, a['wall_m'], a['door_width_m'], 'INT_CORE', 1, 'lift_shaft',
                               door=level in lift.get('served_levels', range(1, lift['last_level'] + 1)))
            for j, rect in enumerate(self.shaft_rects):
                a = self.settings['service_shafts']
                outer = [rect[0], rect[1], rect[2] + 2 * a['wall_m'], rect[3] + 2 * a['wall_m'], rect[4]]
                self.enclosure(f'INT-L{level:02d}-RISER-{j + 1}', outer, floor, a['enclosure_height_m'], a['wall_m'], 0, 'INT_CORE', 1, 'service_enclosure', door=False)
                floor['obstacles'].append(outer)
        for obj in self.base['objects'][p['floor_count']:]:
            obj['stage'], obj['level'] = 1, 0
            self.objects.append(obj)
        for j, lift in enumerate(self.lifts):
            x, y, w, d, angle = lift['rect']
            first = lift.get('first_level', 1)
            z = self.floors[first - 1]['ffl']
            last = self.floors[lift['last_level'] - 1]
            car = combine([box([x, y, w - 0.25, d - 0.25, 0], z + dz, h) for dz, h in [(0.02, 0.12), (2.25, 0.12)]] +
                          [box([x + side * (w / 2 - 0.16), y, 0.08, d - 0.25, 0], z + 0.14, 2.11) for side in (-1, 1)] +
                          [box([x, y + (1 if y > 0 else -1) * (d / 2 - 0.16), w - 0.25, 0.08, 0], z + 0.14, 2.11)])
            if self.settings.get('variant') == 'researched':
                car = combine([box([0, 0, w - 0.25, d - 0.25, 0], z + dz, h) for dz, h in [(0.02, 0.12), (2.25, 0.12)]] +
                              [box([side * (w / 2 - 0.16), 0, 0.08, d - 0.25, 0], z + 0.14, 2.11) for side in (-1, 1)] +
                              [box([0, d / 2 - 0.16, w - 0.25, 0.08, 0], z + 0.14, 2.11)])
                car = transform(car, [x, y, angle])
            self.add('INT-' + lift['id'] + '-CAR', 'INT_LIFTS', 1, first, car, 'lift_car', shaft=lift['id'], served_levels=lift.get('served_levels', [1, lift['last_level']]))
            for side in (-1, 1):
                self.add(f'INT-{lift["id"]}-RAIL-{side:+d}', 'INT_LIFTS', 1, 0,
                         box([*local_xy(lift['rect'], side * (w / 2 - 0.04), 0), 0.04, 0.04, angle], z, last['next_z'] - z - 0.2), 'lift_guide')
        for i, (x, y) in enumerate(self.settings.get('legacy_core_columns_m', [(-3.28, -3.11), (3.28, -3.11), (-3.28, 3.11), (3.28, 3.11)])):
            self.add(f'INT-CORE-COLUMN-{i + 1}', 'INT_SUPPORTS', 1, 0,
                     box([x, y, 0.25, 0.25, 0], 0.25, self.floors[-1]['ffl'] - 0.25), 'conceptual_core_column')
        self.stairs()

    def enclosure(self, identifier, rect, floor, height, wall, door_width, category, stage, role, door=True):
        cx, cy, w, d, angle = rect
        z = floor['ffl']
        hdoor = self.settings['rooms']['door_height_m']
        def part(x, y, a, b, dz=0, h=height):
            px, py = local_xy(rect, x, y)
            return box([px, py, a, b, angle], z + dz, h)
        pieces = [part(-w / 2 + wall / 2, 0, wall, d), part(w / 2 - wall / 2, 0, wall, d), part(0, d / 2 - wall / 2, w - 2 * wall, wall)]
        if door:
            side_width = (w - 2 * wall - door_width) / 2
            if side_width <= 0 or height <= hdoor:
                raise ValueError('Invalid door or enclosure dimensions')
            for side in (-1, 1):
                pieces.append(part(side * (door_width / 2 + side_width / 2), -d / 2 + wall / 2, side_width, wall))
            pieces.append(part(0, -d / 2 + wall / 2, door_width, wall, hdoor, height - hdoor))
            dx, dy = local_xy(rect, 0, -d / 2)
            self.add(identifier + '-DOOR', 'INT_DOORS', stage, floor['level'],
                     box([dx, dy, door_width - 0.03, 0.045, angle], z + 0.015, hdoor - 0.03), 'door_leaf', parent=identifier)
            clear = [*local_xy(rect, 0, -d / 2 - 0.65), door_width + 0.3, 1.3, angle]
            self.doors.append({'id': identifier + '-DOOR', 'level': floor['level'], 'parent': identifier,
                               'opening_width_m': door_width, 'opening_height_m': hdoor,
                               'threshold_m': [dx, dy, z], 'approach_rect': clear, 'assumed_swing': 'closed leaf; swing not simulated'})
        else:
            pieces.append(part(0, -d / 2 + wall / 2, w - 2 * wall, wall))
        self.add(identifier, category, stage, floor['level'], combine(pieces), role, footprint=rect)

    def stairs(self):
        p, s = self.exterior, self.settings['stairs']
        regular = p['regular_height_module_m']
        run = s['risers_per_flight'] * s['going_m']
        w, gap, landing = s['flight_width_m'], s['central_gap_m'], s['landing_length_m']
        bays = []
        for lower, upper in zip(self.floors, self.floors[1:]):
            count = max(1, math.ceil((upper['ffl'] - lower['ffl']) / (regular * 1.25)))
            delta = (upper['ffl'] - lower['ffl']) / count
            bays.extend((lower['ffl'] + i * delta, delta, lower['level']) for i in range(count))
        for k, (z, module, level) in enumerate(bays):
            rise = module / (2 * s['risers_per_flight'])
            for j, pose in enumerate(self.stair_poses):
                base = f'INT-STAIR-{j + 1}-BAY-{k:02d}'
                for flight in range(2):
                    x0 = -gap / 2 - w if flight == 0 else gap / 2
                    y0 = -run / 2 if flight == 0 else run / 2
                    direction = 1 if flight == 0 else -1
                    z0 = z + flight * module / 2
                    identifier = base + f'-FLIGHT-{flight + 1}'
                    self.add(identifier, 'INT_STAIRS', 1, level,
                             transform(stair_flight(x0, x0 + w, y0, direction, z0, s['risers_per_flight'], rise, s['going_m'], s['waist_m']), pose),
                             'stair_flight', riser_m=rise, going_m=s['going_m'], risers=s['risers_per_flight'])
                    for step in range(s['risers_per_flight']):
                        self.walks.append({'component': identifier, 'level': level,
                                           'xyz': [*local_xy([*pose[:2], 0, 0, pose[2]], x0 + w / 2, y0 + direction * (step + 0.5) * s['going_m']), z0 + (step + 1) * rise]})
                    for side in (0.06, w - 0.06):
                        a = [x0 + side, y0, z0 + rise + s['handrail_height_m']]
                        b = [x0 + side, y0 + direction * run, z0 + module / 2 + s['handrail_height_m']]
                        rail_parts = [tube(a, b, 0.025)]
                        for t in (0.05, 0.5, 0.95):
                            foot = [x0 + side, y0 + direction * run * t, z0 + math.ceil(t * s['risers_per_flight']) * rise]
                            rail_parts.append(tube(foot, [foot[0], foot[1], a[2] + (b[2] - a[2]) * t], 0.015))
                        self.add(identifier + f'-RAIL-{side:.2f}', 'INT_RAILS', 1, level, transform(combine(rail_parts), pose), 'stair_handrail')
                self.add(base + '-MID', 'INT_STAIRS', 1, level,
                         transform(box([0, run / 2 + landing / 2, 2 * w + gap, landing, 0], z + module / 2 - s['waist_m'], s['waist_m']), pose), 'stair_landing')
                if not any(abs(f['ffl'] - (z + module)) < 1e-7 for f in self.floors):
                    self.add(base + '-TRANSFER', 'INT_STAIRS', 1, level,
                             transform(box([0, -run / 2 - landing / 2, 2 * w + gap, landing, 0], z + module - s['waist_m'], s['waist_m']), pose), 'intermediate_landing')

    def room(self, identifier, kind, rect, floor):
        p = self.settings['rooms']
        if not self.fits(rect, floor, p['partition_height_m'], 0.15) or any(overlaps(rect, r, 0.1) for r in floor['obstacles']):
            self.omissions.append({'id': identifier, 'reason': 'Room rejected by footprint or envelope clearance'})
            return False
        self.enclosure(identifier, rect, floor, p['partition_height_m'], p['wall_m'], p['door_width_m'], 'INT_PARTITIONS', 2, 'room_partition')
        rec = {'id': identifier, 'level': floor['level'], 'use': kind, 'rect': rect, 'area_m2': (rect[2] - 2 * p['wall_m']) * (rect[3] - 2 * p['wall_m']), 'evidence': 'assumed'}
        self.rooms.append(rec)
        floor['rooms'].append(rec)
        floor['obstacles'].append(rect)
        return True

    def plan_rooms(self):
        p = self.settings['rooms']
        for floor in self.floors:
            level = floor['level']
            if level >= 38:
                continue
            for side, x in enumerate(p['service_centres_x_m']):
                for j, y in enumerate(p['service_centres_y_m']):
                    kind = ['electrical', 'washroom', 'it' if side == 0 else 'janitor'][j]
                    rect = [x, y, *p['service_size_m'], math.pi / 2 if x > 0 else -math.pi / 2]
                    self.room(f'INT-L{level:02d}-{kind.upper()}-{side + 1}', kind, rect, floor)
            if self.settings['office_levels'][0] <= level <= self.settings['office_levels'][1]:
                for sector in range(6):
                    angle = math.radians(floor['phase'] + 12 + 60 * sector)
                    radial = p['meeting_radius_m']
                    rect = [radial * math.cos(angle), radial * math.sin(angle), *p['meeting_size_m'], angle + math.pi / 2]
                    self.room(f'INT-L{level:02d}-MEETING-{sector + 1}', 'meeting', rect, floor)
            if level in self.settings['plant_levels']:
                rect = [0, -11.5 if level == 2 else -10.6, 10 if level == 2 else 6, 4 if level == 2 else 3.6, math.pi if level == 2 else math.pi / 2]
                self.room(f'INT-L{level:02d}-PLANT', 'plant', rect, floor)

    def desk(self, identifier, rect, floor):
        p = self.settings['fitout']
        w, d, height = p['desk_m']
        def b(x, y, width, depth, bottom, h):
            return box([*local_xy(rect, x, y), width, depth, rect[4]], floor['ffl'] + bottom, h)
        desk = combine([b(0, 0.35, w, d, height - 0.05, 0.05),
                        b(-w / 2 + 0.13, 0.35, 0.12, d - 0.12, 0, height - 0.05),
                        b(w / 2 - 0.13, 0.35, 0.12, d - 0.12, 0, height - 0.05),
                        b(0, 0.55, 0.5, 0.045, height + 0.12, 0.3), b(0, 0.5, 0.14, 0.16, height, 0.12)])
        self.add(identifier, 'INT_DESKS', 3, floor['level'], desk, 'workstation', clearance_rect=rect)
        self.add(identifier + '-CHAIR', 'INT_SEATING', 3, floor['level'],
                 combine([b(0, -0.4, 0.52, 0.5, 0.44, 0.08), b(0, -0.65, 0.52, 0.07, 0.52, 0.42),
                          b(0, -0.4, 0.08, 0.08, 0.07, 0.37), b(0, -0.4, 0.48, 0.42, 0.02, 0.05)]), 'workstation_chair', parent=identifier)
        floor['furniture'].append({'id': identifier, 'rect': rect, 'type': 'workstation'})

    def fitout(self):
        p = self.settings['fitout']
        for floor in self.floors:
            level = floor['level']
            for room in floor['rooms']:
                rect, kind = room['rect'], room['use']
                def at(x, y, w, d, bottom, height):
                    return box([*local_xy(rect, x, y), w, d, rect[4]], floor['ffl'] + bottom, height)
                if kind == 'meeting':
                    self.add(room['id'] + '-TABLE', 'INT_DESKS', 3, level,
                             combine([at(0, 0.35, 2.2, 1.0, 0.72, 0.06), at(-0.7, 0.35, 0.12, 0.6, 0, 0.72), at(0.7, 0.35, 0.12, 0.6, 0, 0.72)]), 'meeting_table')
                    for j, (x, y) in enumerate([(-0.7, -0.5), (0.7, -0.5), (-0.7, 1.15), (0.7, 1.15)]):
                        self.add(room['id'] + f'-CHAIR-{j}', 'INT_SEATING', 3, level,
                                 combine([at(x, y, 0.48, 0.48, 0.44, 0.06), at(x, y, 0.07, 0.07, 0, 0.44), at(x, y + (0.24 if y > 0 else -0.24), 0.48, 0.06, 0.5, 0.4)]), 'meeting_chair')
                elif kind == 'washroom':
                    self.add(room['id'] + '-BASIN', 'INT_FIXTURES', 3, level, combine([at(-0.8, 0.6, 0.55, 0.48, 0.76, 0.12), at(-0.8, 0.6, 0.14, 0.14, 0, 0.76)]), 'washbasin')
                    self.add(room['id'] + '-WC', 'INT_FIXTURES', 3, level, combine([at(0.6, 0.8, 0.42, 0.65, 0, 0.42), at(0.6, 1.12, 0.42, 0.18, 0.42, 0.4)]), 'wc_proxy')
                    floor['service_destinations'].append({'id': room['id'] + '-BASIN', 'xy': local_xy(rect, -0.8, 0.6), 'z': floor['ffl'] + 0.8})
                elif kind in ('electrical', 'it', 'janitor'):
                    self.add(room['id'] + '-CABINETS', 'INT_PLANT', 3, level,
                             combine([at(x, 0.7, 0.65, 0.7, 0, 1.8) for x in (-0.7, 0.3)]), kind + '_equipment_proxy')
                elif kind == 'plant':
                    count = 4 if rect[2] >= 8 else 2
                    for j in range(count):
                        x = (j - (count - 1) / 2) * 2.0
                        self.add(room['id'] + f'-EQUIPMENT-{j}', 'INT_PLANT', 3, level,
                                 combine([at(x, 0.4, 1.5, 1.4, 0, 0.12), at(x, 0.4, 1.25, 1.1, 0.12, 1.8)]),
                                 ['heating_plant_proxy', 'air_handling_proxy', 'water_tank_proxy', 'pump_set_proxy'][j])
            if not self.settings['office_levels'][0] <= level <= self.settings['office_levels'][1]:
                self.amenity(floor)
                continue
            angle = math.radians(floor['phase'])
            limit = math.ceil(floor['radius'] / min(p['grid_m']))
            door_rects = [d['approach_rect'] for d in self.doors if d['level'] == level]
            for row in range(-limit, limit + 1):
                for col in range(-limit, limit + 1):
                    xy = local_xy([0, 0, 0, 0, angle], col * p['grid_m'][0], row * p['grid_m'][1])
                    rect = [*xy, *p['workstation_clearance_m'], angle]
                    if math.hypot(*xy) < floor.get('core_clear_radius_m', p['core_clear_radius_m']) + math.hypot(*p['workstation_clearance_m']) / 2:
                        continue
                    if not self.fits(rect, floor, 1.25, p['facade_clearance_m']):
                        continue
                    if any(overlaps(rect, r, p['room_clearance_m']) for r in floor['obstacles']) or any(overlaps(rect, r, 0.2) for r in door_rects):
                        continue
                    if any(segment_distance(pt, [0, 0], [floor['radius'] * math.cos(a), floor['radius'] * math.sin(a)]) < p['radial_aisle_width_m'] / 2
                           for pt in corners(rect) + [xy] for a in [angle + math.radians(30 + 60 * k) for k in range(6)]):
                        continue
                    self.desk(f'INT-L{level:02d}-DESK-R{row:+03d}-C{col:+03d}', rect, floor)

    def amenity(self, floor):
        level = floor['level']
        if level in self.settings['plant_levels']:
            return
        minimum = 10 if level == 1 else 5.2
        for j in range(12):
            a = math.radians(floor['phase'] + 30 + j * 30)
            r = max(minimum + 2, floor['radius'] - 3.0)
            rect = [r * math.cos(a), r * math.sin(a), 2.2, 2.2, a]
            if not self.fits(rect, floor, 1.0, 0.6) or any(overlaps(rect, o, 0.8) for o in floor['obstacles']) or any(overlaps(rect, f['rect'], 0.4) for f in floor['furniture']):
                continue
            name = f'INT-L{level:02d}-CAFE-{j:02d}'
            x, y = rect[:2]
            self.add(name, 'INT_DESKS', 3, level,
                     combine([tube([x, y, floor['ffl'] + 0.7], [x, y, floor['ffl'] + 0.76], 0.55, 16), tube([x, y, floor['ffl']], [x, y, floor['ffl'] + 0.7], 0.07)]), 'cafe_table', clearance_rect=rect)
            for k in range(4):
                px, py = local_xy(rect, math.cos(k * math.pi / 2) * 0.85, math.sin(k * math.pi / 2) * 0.85)
                self.add(name + f'-SEAT-{k}', 'INT_SEATING', 3, level, combine([box([px, py, 0.4, 0.4, a], floor['ffl'] + 0.43, 0.06), tube([px, py, floor['ffl']], [px, py, floor['ffl'] + 0.43], 0.06)]), 'cafe_seat')
            floor['furniture'].append({'id': name, 'rect': rect, 'type': 'cafe'})

    def route_tree(self, floor, root, targets, height):
        step = self.settings['services']['routing_grid_m']
        origin = tuple(round(v / step) for v in root)
        r = self.radius(floor['ffl'] + height) - self.exterior['floor_radial_inset_m'] - 0.2
        barriers = self.stair_rects + [[*lift['rect'][:2], lift['rect'][2] + 0.5, lift['rect'][3] + 0.5, lift['rect'][4] if self.settings.get('variant') == 'researched' else 0] for lift in self.lifts if lift.get('first_level', 1) <= floor['level'] <= lift['last_level']]
        barriers += [[*rect[:2], rect[2] + 0.24, rect[3] + 0.24, rect[4]] for rect in self.shaft_rects if not in_rect(root, rect)]
        barriers += floor.get('routing_keepouts', [])
        barrier_buckets = defaultdict(list)
        for rect in barriers:
            points = corners(rect, 0.12)
            for x in range(math.floor(min(p[0] for p in points) / 2), math.floor(max(p[0] for p in points) / 2) + 1):
                for y in range(math.floor(min(p[1] for p in points) / 2), math.floor(max(p[1] for p in points) / 2) + 1):
                    barrier_buckets[(x, y)].append(rect)
        def blocked(xy):
            return any(in_rect(xy, rect, 0.12) for rect in barrier_buckets[(math.floor(xy[0] / 2), math.floor(xy[1] / 2))])
        if not hasattr(self, 'route_profile_cache'):
            self.route_profile_cache = {}
            self.route_edge_cache = {}
        profile_cache = self.route_profile_cache.setdefault(floor['level'], {})
        edge_cache = self.route_edge_cache.setdefault(floor['level'], {})
        def usable(xy, margin):
            key = (*xy, margin)
            if key not in profile_cache:
                profile_cache[key] = clear_point(xy, floor['profile'], margin)
            return profile_cache[key]
        valid_cache = {}
        def valid(node):
            if node not in valid_cache:
                xy = [n * step for n in node]
                valid_cache[node] = (math.hypot(*xy) < r and not blocked(xy) and usable(xy, 0.08 if self.settings.get('variant') == 'researched' else 0))
            return valid_cache[node]
        if not valid(origin):
            raise ValueError('Service root outside routable space')
        parent = {origin: None}
        queue = deque([origin])
        remaining = {tuple(round(v / step) for v in target['xy']) for target in targets}
        remaining = {node for node in remaining if valid(node)}
        while queue:
            node = queue.popleft()
            remaining.discard(node)
            if not remaining:
                break
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nxt = node[0] + dx, node[1] + dy
                if nxt not in parent and valid(nxt):
                    mid = [(node[k] + nxt[k]) * step / 2 for k in (0, 1)]
                    if blocked(mid) or not usable(mid, 0.06):
                        continue
                    if self.settings.get('variant') == 'researched':
                        edge = tuple(sorted((node, nxt)))
                        if edge not in edge_cache:
                            edge_cache[edge] = clear_segment([n * step for n in node], [n * step for n in nxt], floor['profile'], 0.03)
                        if not edge_cache[edge]:
                            continue
                    parent[nxt] = node
                    queue.append(nxt)
        ends = []
        for target in targets:
            node = tuple(round(v / step) for v in target['xy'])
            if node not in parent:
                self.omissions.append({'id': target['id'], 'reason': 'No connected service route within the current concept'})
                continue
            ends.append((target, node))
        edges = set()
        for _, node in ends:
            while parent[node] is not None:
                edges.add(tuple(sorted((node, parent[node]))))
                node = parent[node]
        adjacency = defaultdict(set)
        for a, b in edges:
            adjacency[a].add(b)
            adjacency[b].add(a)
        breaks = {origin} | {node for _, node in ends}
        for node, neighbors in adjacency.items():
            ns = list(neighbors)
            if len(ns) != 2 or ns[0][0] + ns[1][0] != 2 * node[0] or ns[0][1] + ns[1][1] != 2 * node[1]:
                breaks.add(node)
        segments, visited = [], set()
        for node in sorted(breaks):
            for nxt in sorted(adjacency[node]):
                if tuple(sorted((node, nxt))) in visited:
                    continue
                start, previous, end = node, node, nxt
                visited.add(tuple(sorted((node, nxt))))
                while end not in breaks:
                    candidate = next(n for n in adjacency[end] if n != previous)
                    visited.add(tuple(sorted((end, candidate))))
                    previous, end = end, candidate
                segments.append(([v * step for v in start], [v * step for v in end]))
        return segments, ends, origin, len(parent)

    def pipe(self, identifier, category, level, a, b, radius, **metadata):
        if math.dist(a, b) < 1e-8:
            return
        self.add(identifier, category, 4, level, tube(a, b, radius, self.settings['services']['pipe_radial_sides']), 'service_pipe', start_m=a, end_m=b, radius_m=radius, **metadata)

    def services(self):
        p = self.settings['services']
        start_z, top_z = self.floors[0]['ffl'], self.floors[-1]['ffl'] + p['pipe_height_m']
        for name, category, xy, rad in [('FIRE', 'INT_FIRE', [4, 0], p['fire_radius_m']), ('COLD', 'INT_COLD', [-4, -0.25], p['water_radius_m']),
                                      ('HOT', 'INT_HOT', [-4, 0.25], p['water_radius_m']), ('DRAIN', 'INT_DRAIN', [-4, 0.5], p['drain_radius_m'])]:
            for f in self.floors:
                low = f['ffl'] if f['level'] == 1 else f['slab_z']
                high = f['next_z'] if f['level'] < len(self.floors) else top_z
                takeoff = f['ffl'] + p['pipe_height_m'] - ({'COLD': 0.2, 'HOT': 0.08}.get(name, 0))
                cuts = [low, takeoff, high] if name != 'DRAIN' and low < takeoff < high else [low, high]
                for part, (a, b) in enumerate(zip(cuts, cuts[1:])):
                    self.pipe(f'INT-{name}-RISER-L{f["level"]:02d}-{part}', category, f['level'], [*xy, a], [*xy, b], rad, system=name)
        for floor in self.floors:
            level, height = floor['level'], p['pipe_height_m']
            spacing = p['routing_grid_m'] * p['head_grid_multiple']
            count = math.ceil(floor['radius'] / spacing)
            targets = [{'id': f'INT-L{level:02d}-HEAD-{ix:+03d}-{iy:+03d}', 'xy': [ix * spacing, iy * spacing + 0.5]}
                       for ix in range(-count, count + 1) for iy in range(-count, count + 1)
                       if math.hypot(ix * spacing, iy * spacing + 0.5) > 4.8 and clear_point([ix * spacing, iy * spacing + 0.5], floor['profile'], 0.7)
                       and not any(in_rect([ix * spacing, iy * spacing + 0.5], r, 0.25) for r in self.stair_rects + [a['rect'] for a in self.lifts if level <= a['last_level']])]
            segments, ends, origin, reachable = self.route_tree(floor, [4, 0], targets, height)
            z = floor['ffl'] + height
            connections = []
            for j, (a, b) in enumerate(segments):
                identifier = f'INT-L{level:02d}-FIRE-MAIN-{j:03d}'
                self.pipe(identifier, 'INT_FIRE', level, [*a, z], [*b, z], p['branch_radius_m'], system='FIRE')
                connections.append({'id': identifier, 'start': [*a, z], 'end': [*b, z]})
            for target, node in ends:
                xy = [n * p['routing_grid_m'] for n in node]
                bottom = floor['ffl'] + p['head_height_m']
                self.pipe(target['id'] + '-DROP', 'INT_FIRE', level, [*xy, z], [*xy, bottom], 0.012, system='FIRE')
                self.add(target['id'], 'INT_FIRE', 4, level, tube([*xy, bottom - 0.03], [*xy, bottom], 0.055, 12), 'sprinkler_head', system='FIRE')
            self.networks.append({'id': f'FIRE-L{level:02d}', 'level': level, 'root_m': [4, 0, z], 'routed_terminals': len(ends),
                                  'requested_terminals': len(targets), 'routing_nodes': reachable, 'segments': connections,
                                  'terminals': [target['id'] for target, _ in ends], 'evidence': 'assumed; no hydraulic or coverage design'})
            if floor['service_destinations']:
                water_height = height - 0.2
                segments, ends, _, _ = self.route_tree(floor, [-5, 0], floor['service_destinations'], water_height)
                for cat, off, label in [('INT_COLD', -0.25, 'COLD'), ('INT_HOT', 0.25, 'HOT')]:
                    wz = floor['ffl'] + water_height + (0.12 if label == 'HOT' else 0)
                    self.pipe(f'INT-L{level:02d}-{label}-TAKEOFF', cat, level, [-4, off, wz], [-5, off, wz], p['water_radius_m'], system=label)
                    self.pipe(f'INT-L{level:02d}-{label}-TAKEOFF-TURN', cat, level, [-5, off, wz], [-5, 0, wz], p['water_radius_m'], system=label)
                    for j, (a, b) in enumerate(segments):
                        self.pipe(f'INT-L{level:02d}-{label}-{j:03d}', cat, level, [*a, wz], [*b, wz], p['water_radius_m'], system=label)
                    for j, (target, node) in enumerate(ends):
                        xy = [n * p['routing_grid_m'] for n in node]
                        final_xy = [target['xy'][0] + (0.05 if label == 'HOT' else -0.05), target['xy'][1]]
                        self.pipe(f'INT-L{level:02d}-{label}-FINAL-{j}', cat, level, [*xy, wz], [*final_xy, wz], p['water_radius_m'], system=label)
                        self.pipe(f'INT-L{level:02d}-{label}-DROP-{j}', cat, level, [*final_xy, wz], [*final_xy, target['z']], p['water_radius_m'], system=label)

    def finish(self):
        for key in sorted(self.groups):
            self.objects.extend(self.groups[key])
        self.objects.sort(key=lambda o: (o['stage'], o['level'], o['name']))
        counts = dict(Counter(c['role'] for c in self.components))
        counts.update(native_objects=len(self.objects), components=len(self.components), levels=len(self.floors), rooms=len(self.rooms), doors=len(self.doors),
                      vertices=sum(len(o['vertices']) for o in self.objects), triangles=sum(len(o['triangles']) for o in self.objects))
        return {'units': 'metres', 'axis': 'Z-up', 'representation': self.settings['evidence_status'],
                'objects': self.objects, 'components': self.components, 'floors': self.floors, 'rooms': self.rooms,
                'doors': self.doors, 'stair_walk_points': self.walks, 'networks': self.networks,
                'omissions': self.omissions, 'counts': counts, 'exclusions': self.settings['exclusions']}


def generate(exterior=None, settings=None):
    settings = settings or load_settings()
    researched = settings.get('variant') == 'researched'
    exterior = exterior or gherkin.load_parameters(ROOT / 'research/parameters-exterior.json' if researched else None)
    validate_settings(settings)
    if exterior['floor_count'] != 40 or (not researched and exterior['regular_height_module_m'] != 4.2):
        raise ValueError('Interior v1 requires the original 40-level, 4.2 m module schedule')
    if researched:
        from interior.researched import ResearchBuilder
        builder = ResearchBuilder(exterior, settings)
    else:
        builder = Builder(exterior, settings)
    builder.shell_and_core()
    builder.plan_rooms()
    builder.fitout()
    builder.services()
    if researched:
        builder.electrical()
    return builder.finish()


def schedules(output, recipe):
    output = Path(output)
    with (output / 'rooms.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['id', 'level', 'use', 'area_m2', 'evidence'])
        writer.writeheader()
        writer.writerows({k: r[k] for k in writer.fieldnames} for r in recipe['rooms'])
    with (output / 'components.csv').open('w', newline='', encoding='utf-8') as stream:
        fields = ['id', 'role', 'stage', 'level', 'evidence', 'object', 'vertex_offset', 'vertex_count', 'face_offset', 'face_count']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: c[k] for k in fields} for c in recipe['components'])
    gherkin.write_json(output / 'design-status.json', {'representation': recipe['representation'], 'counts': recipe['counts'], 'omissions': recipe['omissions'], 'exclusions': recipe['exclusions']})
    if 'electrical_circuits' in recipe:
        with (output / 'electrical-circuits.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=['id', 'level', 'system', 'board', 'source', 'terminals', 'ratings', 'evidence'])
            writer.writeheader()
            writer.writerows({**c, 'terminals': ';'.join(c['terminals'])} for c in recipe['electrical_circuits'])
        gherkin.write_json(output / 'lift-schedule.json', recipe['lift_schedule'])


def main():
    parser = argparse.ArgumentParser(description='Generate a coordinated conceptual Gherkin interior; no as-built claim.')
    parser.add_argument('--variant', choices=['original', 'researched'], default='original')
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--exterior-parameters', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    settings = load_settings(args.parameters or ROOT / ('interior/parameters-researched.json' if args.variant == 'researched' else 'interior/parameters.json'))
    exterior = gherkin.load_parameters(args.exterior_parameters) if args.exterior_parameters else None
    recipe = generate(exterior, settings)
    gherkin.write_json(args.output_dir / 'geometry.json', recipe)
    schedules(args.output_dir, recipe)
    print(json.dumps(recipe['counts'], indent=2))


if __name__ == '__main__':
    main()
