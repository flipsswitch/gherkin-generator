import math

from gherkin import cross, dot, sub
from interior.generator import COLORS
from interior.geometry import box, clear_point, combine, corners, local_xy, overlaps, tube
from interior.architectural_geometry import ellipsoid, hollow_member, rectangular_member, ring, subtract_portal, triangle_fan, triangular_member, vertical_panel
from interior.researched import ResearchBuilder
from interior.amenities import AmenityMixin


COLORS.update({
    'INT_DIAGRID': ((0.55, 0.58, 0.59), 8),
    'INT_CROWN': ((0.19, 0.22, 0.24), 7),
    'INT_MULLIONS': ((0.31, 0.36, 0.39), 8),
    'INT_ENTRANCE': ((0.88, 0.88, 0.85), 0),
    'INT_LOBBY': ((0.75, 0.77, 0.75), 8),
    'INT_INTERIOR_GLASS': ((0.59, 0.74, 0.77), 7),
    'INT_HARDWARE': ((0.15, 0.17, 0.18), 7),
    'INT_WORKTOPS': ((0.80, 0.77, 0.69), 0),
    'INT_SCREENS': ((0.022, 0.035, 0.045), 7),
    'INT_PLANTERS': ((0.70, 0.68, 0.62), 8),
    'INT_FOLIAGE': ((0.19, 0.32, 0.10), 2),
    'INT_LANDSCAPE': ((0.70, 0.70, 0.67), 8),
    'INT_TRUNKS': ((0.22, 0.14, 0.08), 6),
})


def validate_architectural_settings(settings):
    p = settings['architecture']
    if settings.get('variant') != 'researched':
        raise ValueError('Architectural detail requires the researched core and services')
    if p['crown']['section_m'] != [0.11, 0.15] or p['crown']['lens_diameter_m'] != 2.4:
        raise ValueError('This preset preserves the documented crown section and lens diameter')
    if p['crown']['nodes_per_ring'] != 36 or p['crown']['ring_z_m'] != sorted(set(p['crown']['ring_z_m'])):
        raise ValueError('Unsupported crown sampling')
    if not 0 <= p['crown']['profile_factor'] <= 1 or not 22 <= p['upper_amenity']['stair_risers'] <= 36:
        raise ValueError('Unsupported crown or amenity stair sampling')
    if not 0 < p['diagrid']['wall_base_m'] < 0.254 or not 0 < p['diagrid']['wall_top_m'] < 0.1365:
        raise ValueError('Invalid hollow diagrid wall thickness')
    e = p['entrance']
    if len(e['door_centres_x_m']) != 4 or e['door_diameter_m'] < 1.8 or e['door_diameter_m'] > 3.0:
        raise ValueError('Entrance requires four bounded revolving-door proxies')
    if e['screen_y_m'] >= -18 or e['screen_y_m'] <= -23 or e['lobby_panel_height_m'] != 7:
        raise ValueError('Unsupported entrance setting-out')
    if any(b - a <= e['door_diameter_m'] + 0.4 for a, b in zip(e['door_centres_x_m'], e['door_centres_x_m'][1:])):
        raise ValueError('Revolving-door clearances overlap')
    if not 0.01 <= p['mullion_radius_m'] <= 0.05:
        raise ValueError('Mullion sampling must remain bounded')


class ArchitecturalBuilder(AmenityMixin, ResearchBuilder):
    def __init__(self, exterior, settings):
        super().__init__(exterior, settings)
        self.architecture = settings['architecture']
        self.glass_room = False
        self.portal = self.architecture['entrance']['portal_xz_m']
        self.surface_batches = {}
        self.mullion_edges = set()
        self.configure_upper()

    def surface(self, prefix, category, polygons, opacity, source_ids):
        batches = self.surface_batches.setdefault((prefix, category), [])
        for poly in polygons:
            vertices, faces = triangle_fan(poly)
            if not faces:
                continue
            if not batches or len(batches[-1]['vertices']) + len(vertices) > 8000:
                obj = {'name': f'{prefix}-{category.rsplit("_", 1)[-1]}-{len(batches):03d}', 'category': category,
                       'kind': 'mesh', 'color': 1 if category.endswith('DARK') else 7, 'opacity': opacity,
                       'stage': 1, 'level': 0, 'vertices': [], 'triangles': [], 'source_ids': source_ids,
                       'evidence': 'Inferred surface tessellation; triangle count is not the installed panel count'}
                batches.append(obj)
                self.objects.append(obj)
            obj = batches[-1]
            offset = len(obj['vertices'])
            obj['vertices'].extend(vertices)
            obj['triangles'].extend([[i + offset for i in face] for face in faces])

    def shell_and_core(self):
        super().shell_and_core()
        self.finish_upper_structure()
        self.objects = [o for o in self.objects if not o['category'].startswith('GHR_') or o['name'].startswith('ARC-')]
        self.diagrid()
        self.facade()
        self.entrance()
        self.landscape()

    def diagrid(self):
        p = self.architecture['diagrid']
        def section(z):
            t = max(0, min(1, (z - 8.3) / (149.5 - 8.3)))
            return 0.254 + (0.1365 - 0.254) * t, p['wall_base_m'] + (p['wall_top_m'] - p['wall_base_m']) * t
        for member in self.base['members']:
            a, b = member['start'], member['end']
            ra, wa = section(a[2])
            rb, wb = section(b[2])
            identifier = member['id'].replace('GHR-', 'ARC-')
            self.add(identifier, 'INT_DIAGRID', 1, 0, hollow_member(a, b, ra, rb, wa, wb, 24),
                     'hollow_diagrid_member', source_ids=['R01'], evidence='Documented end-zone diameters and walls; tapered interpolation and 24-sided discretization inferred',
                     start_m=a, end_m=b, outer_radii_m=[ra, rb], wall_m=[wa, wb], ring_vertices=24)
            if max(a[2], b[2]) <= 16.62 and a[1] < -19 and b[1] < -19:
                self.add(identifier + '-CLADDING', 'INT_ENTRANCE', 2, 1,
                         rectangular_member(a, b, 0.68, 0.38), 'entrance_chevron_cladding', source_ids=['U03'],
                         evidence='White entrance chevron appearance observed in supplied photo; cladding dimensions inferred')

    def facade(self):
        data = self.base['facade']
        top = self.exterior['diagrid_body_top_m']
        for face in data['faces']:
            poly = [data['vertices'][i] for i in face['vertices']]
            if max(p[2] for p in poly) > top + 1e-5:
                continue
            pieces = subtract_portal(poly, self.portal, -18.5)
            category = 'GHR_GLAZING_' + face['appearance'].upper()
            self.surface('ARC-FACADE', category, pieces, self.exterior['glazing_' + face['appearance'] + '_opacity'], ['R10'])
            for piece in pieces:
                for a, b in zip(piece, piece[1:] + piece[:1]):
                    if math.dist(a, b) < 0.02:
                        continue
                    key = tuple(sorted(tuple(round(v, 5) for v in p) for p in (a, b)))
                    if key in self.mullion_edges:
                        continue
                    self.mullion_edges.add(key)
                    self.add(f'ARC-MULLION-{len(self.mullion_edges):05d}', 'INT_MULLIONS', 1, 0,
                             tube(a, b, self.architecture['mullion_radius_m'], 6), 'facade_mullion', source_ids=['U01', 'U03'],
                             evidence='Visible fine facade framing; section and panel subdivision inferred')

    def dome(self):
        p = self.architecture['crown']
        height = self.exterior['height_m']
        base = self.exterior['diagrid_body_top_m']
        lens_radius = p['lens_diameter_m'] / 2
        factor = p['profile_factor']
        target = (lens_radius / 15) ** 2
        t = 1 - target if factor == 0 else (factor - 1 + math.sqrt((1 - factor) ** 2 + 4 * factor * (1 - target))) / (2 * factor)
        lens_z = base + 22 * t
        zs = p['ring_z_m'] + [lens_z]
        previous = None
        count = p['nodes_per_ring']
        for k, z in enumerate(zs):
            t = (z - base) / 22
            radius = 15 * math.sqrt(max(0, (1 - t) * (1 + factor * t)))
            angle = (k % 2) * math.pi / count
            points = [[radius * math.cos(math.tau * j / count + angle), radius * math.sin(math.tau * j / count + angle), z] for j in range(count)]
            if previous:
                side = -1 if k % 2 else 1
                for j in range(count):
                    for edge in (0, side):
                        a, b = previous[j], points[(j + edge) % count]
                        self.add(f'ARC-CROWN-{k:02d}-{j:02d}-{edge:+d}', 'INT_CROWN', 1, 0,
                                 triangular_member(a, b, *p['section_m']), 'crown_triangular_member', source_ids=['R01'],
                                 evidence='110 x 150 mm gross triangular section sourced; wall thickness, joints and setting-out unavailable',
                                 start_m=a, end_m=b, section_m=p['section_m'])
                    q = (j + 1) % count
                    polygons = [[previous[j], previous[q], points[j]], [previous[q], points[q], points[j]]]
                    for polygon in polygons:
                        normal = cross(sub(polygon[1], polygon[0]), sub(polygon[2], polygon[0]))
                        if dot(normal, [sum(v[0] for v in polygon), sum(v[1] for v in polygon), 0]) < 0:
                            polygon.reverse()
                    self.surface('ARC-CROWN-GLASS', 'GHR_GLAZING_CLEAR', polygons, self.exterior['glazing_clear_opacity'], ['R01', 'U02'])
            for j, (a, b) in enumerate(zip(points, points[1:] + points[:1])):
                self.add(f'ARC-CROWN-RING-{k:02d}-{j:02d}', 'INT_CROWN', 1, 0, rectangular_member(a, b, 0.06, 0.09),
                         'crown_ring_proxy', source_ids=['U02'], evidence='Horizontal framing observed; section and elevations inferred')
            previous = points
        edge = [[lens_radius * math.cos(math.tau * j / 72), lens_radius * math.sin(math.tau * j / 72), lens_z] for j in range(72)]
        self.surface('ARC-APEX-LENS', 'GHR_GLAZING_CLEAR', [[a, b, [0, 0, height]] for a, b in zip(edge, edge[1:] + edge[:1])],
                     self.exterior['glazing_clear_opacity'], ['R06'])
        self.add('ARC-APEX-SURROUND', 'INT_LOBBY', 1, 0, ring(0, 0, lens_z - 0.38, 2.25, lens_radius, 0.18, 72),
                 'apex_annular_surround', source_ids=['U02'], evidence='Metallic annulus observed in dome photo; outer diameter and depth inferred')

    def entrance(self):
        p = self.architecture['entrance']
        floor = self.floors[0]
        z, y = floor['ffl'], p['screen_y_m']
        radius, h = p['door_diameter_m'] / 2, p['door_height_m']
        centres = p['door_centres_x_m']
        edges = [-11.0] + [v for x in centres for v in (x - radius, x + radius)] + [11.0]
        for j in range(0, len(edges), 2):
            a, b = edges[j:j + 2]
            self.add(f'ARC-ENTRY-SCREEN-{j:02d}', 'INT_INTERIOR_GLASS', 2, 1, box([(a + b) / 2, y, b - a, 0.035, 0], z, h),
                     'entrance_glazed_screen', source_ids=['U03'])
        self.add('ARC-ENTRY-TRANSOM', 'INT_INTERIOR_GLASS', 2, 1, box([0, y, 22, 0.035, 0], z + h, 7.0 - h), 'entrance_glazed_transom', source_ids=['U03'])
        self.add('ARC-ENTRY-UPPER-GLASS', 'INT_INTERIOR_GLASS', 2, 1,
                 vertical_panel([[-9.4, z + 7.0], [9.4, z + 7.0], [4.7, 16.610526], [-4.7, 16.610526]], y, 0.035),
                 'recessed_upper_entrance_glazing', source_ids=['U03'], evidence='Photo-informed recessed screen; dimensions and subdivision inferred')
        for j in range(12):
            self.add(f'ARC-ENTRY-FRAME-{j:02d}', 'INT_HARDWARE', 2, 1, box([-11 + j * 2, y, 0.05, 0.09, 0], z + h, 7.0 - h), 'entrance_screen_frame')
        for j, x in enumerate(centres):
            name = f'ARC-ENTRY-REVOLVING-{j + 1}'
            self.add(name + '-CROWN', 'INT_HARDWARE', 2, 1, ring(x, y, z + h, radius + 0.06, radius - 0.06, 0.12),
                     'revolving_door_header', source_ids=['R11'], evidence='Four Crystal Tourniket doors sourced; all dimensions, positions and three-leaf arrangement inferred',
                     door_index=j + 1, centre_m=[x, y, z], diameter_m=p['door_diameter_m'])
            for side in (-1, 1):
                for k in range(18):
                    a = side * math.pi / 2 + math.radians(-55 + k * 110 / 18)
                    b = side * math.pi / 2 + math.radians(-55 + (k + 1) * 110 / 18)
                    pa = [x + radius * math.sin(a), y + radius * math.cos(a), z]
                    pb = [x + radius * math.sin(b), y + radius * math.cos(b), z]
                    self.add(name + f'-DRUM-{side:+d}-{k:02d}', 'INT_INTERIOR_GLASS', 2, 1,
                             rectangular_member([pa[0], pa[1], z + h / 2], [pb[0], pb[1], z + h / 2], 0.02, h),
                             'revolving_door_drum', parent=name)
            self.add(name + '-SPINDLE', 'INT_HARDWARE', 2, 1, tube([x, y, z], [x, y, z + h], 0.035, 12), 'revolving_door_spindle', parent=name)
            for k in range(3):
                angle = math.tau * k / 3
                self.add(name + f'-LEAF-{k}', 'INT_INTERIOR_GLASS', 2, 1,
                         box([x + math.cos(angle) * radius / 2, y + math.sin(angle) * radius / 2, radius - 0.04, 0.025, angle], z + 0.035, h - 0.07),
                         'revolving_door_leaf', parent=name, operation='closed illustrative rotor; dynamic clearance and compliance unverified')
            self.doors.append({'id': name, 'level': 1, 'parent': name, 'opening_width_m': p['door_diameter_m'], 'opening_height_m': h,
                               'threshold_m': [x, y - radius, z], 'approach_rect': [x, y - radius - 0.8, 2.0, 1.4, 0],
                               'assumed_swing': 'Three-leaf rotor; kinematics not simulated'})
        self.add('ARC-ENTRY-CANOPY', 'INT_HARDWARE', 2, 1, box([0, -22.1, 17.4, 5.2, 0], 8.20, 0.16), 'entrance_canopy', source_ids=['U03'])
        for side in (-1, 1):
            for j in range(14):
                self.add(f'ARC-LOBBY-PANEL-{side:+d}-{j:02d}', 'INT_LOBBY', 2, 1,
                         box([side * 10.6, -18.8 + j * 0.32, 0.08, 0.305, 0], z, p['lobby_panel_height_m']),
                         'lobby_aluminium_panel', source_ids=['R10'], evidence='7 m height sourced; panel rhythm and placement inferred')
        desk = [0, -15.8, 4.2, 1.1, 0]
        self.add('ARC-RECEPTION-BASE', 'INT_LOBBY', 3, 1, box(desk, z, 1.02), 'reception_desk_proxy')
        self.add('ARC-RECEPTION-TOP', 'INT_WORKTOPS', 3, 1, box([0, -15.8, 4.4, 1.2, 0], z + 1.02, 0.06), 'reception_worktop')

    def landscape(self):
        z = self.floors[0]['ffl']
        self.add('ARC-PLAZA', 'INT_LANDSCAPE', 1, 0, box([0, 0, 78, 72, 0], z - 0.3, 0.3),
                 'plaza_proxy', source_ids=['R10'], evidence='Landscaped plaza documented; extent and setting-out illustrative, not a site survey')
        for j, (x, y) in enumerate([(-29, -22), (-31, -11), (-32, 1), (-28, 19), (29, -22), (31, -10), (32, 3), (28, 19)]):
            name = f'ARC-PLAZA-TREE-{j:02d}'
            self.add(name + '-PLANTER', 'INT_PLANTERS', 3, 0, box([x, y, 4.8, 1.7, 0], z, 0.45), 'plaza_stone_seat', source_ids=['R10'])
            self.add(name + '-TRUNK', 'INT_TRUNKS', 3, 0, tube([x, y, z + 0.45], [x, y, z + 4.8], 0.13, 10), 'plaza_tree_trunk')
            for k in range(5):
                a = k * math.tau / 5
                self.add(name + f'-CROWN-{k}', 'INT_FOLIAGE', 3, 0,
                         ellipsoid([x + 0.7 * math.cos(a), y + 0.7 * math.sin(a), z + 4.8 + 0.25 * (k % 2)], [1.2, 1.1, 1.9]), 'plaza_tree_foliage')
        for j in range(-14, 15):
            self.add(f'ARC-PAVING-{j:+03d}', 'INT_MULLIONS', 3, 0,
                     box([j * 2.5, -30.5, 0.012, 9.0, 0], z + 0.001, 0.002), 'paving_joint_proxy')

    def room(self, identifier, kind, rect, floor):
        self.glass_room = kind in ('meeting', 'private_office')
        try:
            accepted = super().room(identifier, kind, rect, floor)
            if accepted and self.glass_room:
                self.rooms[-1]['area_m2'] = (rect[2] - 0.07) * (rect[3] - 0.07)
            return accepted
        finally:
            self.glass_room = False

    def enclosure(self, identifier, rect, floor, height, wall, door_width, category, stage, role, door=True):
        if not self.glass_room:
            return super().enclosure(identifier, rect, floor, height, wall, door_width, category, stage, role, door)
        super().enclosure(identifier, rect, floor, height, 0.035, door_width, 'INT_INTERIOR_GLASS', stage, role, door)
        z = floor['ffl']
        pts = corners(rect)
        frame = [tube([*a, z], [*a, z + height], 0.025, 6) for a in pts]
        frame.extend(tube([*a, z + height], [*b, z + height], 0.025, 6) for a, b in zip(pts, pts[1:] + pts[:1]))
        self.add(identifier + '-GLASS-FRAME', 'INT_HARDWARE', stage, floor['level'], combine(frame), 'partition_glazing_frame', parent=identifier)

    def desk(self, identifier, rect, floor):
        w, d, h = self.settings['fitout']['desk_m']
        z = floor['ffl']
        def b(x, y, width, depth, bottom, height):
            return box([*local_xy(rect, x, y), width, depth, rect[4]], z + bottom, height)
        self.add(identifier, 'INT_WORKTOPS', 3, floor['level'], b(0, 0.35, w, d, h - 0.035, 0.035), 'workstation', clearance_rect=rect)
        self.add(identifier + '-LEGS', 'INT_HARDWARE', 3, floor['level'],
                 combine([b(x, y, 0.045, 0.045, 0, h - 0.035) for x in (-w / 2 + 0.1, w / 2 - 0.1) for y in (0.35 - d / 2 + 0.08, 0.35 + d / 2 - 0.08)]),
                 'workstation_frame', parent=identifier)
        self.add(identifier + '-SCREEN', 'INT_SCREENS', 3, floor['level'],
                 combine([b(0, 0.57, 0.53, 0.035, h + 0.13, 0.32), b(0, 0.56, 0.05, 0.05, h + 0.015, 0.12),
                          b(0, 0.52, 0.18, 0.18, h, 0.015), b(0, 0.25, 0.42, 0.14, h + 0.001, 0.018), b(0.34, 0.25, 0.06, 0.1, h, 0.024)]),
                 'monitor_keyboard_mouse', parent=identifier)
        self.add(identifier + '-CHAIR', 'INT_SEATING', 3, floor['level'],
                 combine([b(0, -0.4, 0.49, 0.46, 0.43, 0.075), b(0, -0.64, 0.46, 0.06, 0.51, 0.4),
                          b(-0.27, -0.42, 0.045, 0.28, 0.64, 0.035), b(0.27, -0.42, 0.045, 0.28, 0.64, 0.035)]),
                 'workstation_chair', parent=identifier)
        cx, cy = local_xy(rect, 0, -0.4)
        legs = [tube([cx, cy, z + 0.07], [cx, cy, z + 0.43], 0.035, 8)]
        for k in range(5):
            a = rect[4] + k * math.tau / 5
            end = [cx + 0.29 * math.cos(a), cy + 0.29 * math.sin(a), z + 0.045]
            legs.extend([tube([cx, cy, z + 0.09], end, 0.018, 6), box([*end[:2], 0.055, 0.055, a], z, 0.045)])
        self.add(identifier + '-CHAIR-BASE', 'INT_HARDWARE', 3, floor['level'], combine(legs), 'chair_caster_base', parent=identifier)
        floor['furniture'].append({'id': identifier, 'rect': rect, 'type': 'workstation'})

    def amenity(self, floor):
        if floor['level'] != 1:
            super().amenity(floor)

    def fitout(self):
        super().fitout()
        for floor in self.floors:
            if not 3 <= floor['level'] <= 35:
                continue
            for j in range(6):
                angle = math.radians(floor['phase'] + j * 60)
                radius = floor['radius'] - 2.0
                rect = [radius * math.cos(angle), radius * math.sin(angle), 1.3, 0.6, angle + math.pi / 2]
                if not self.fits(rect, floor, 1.5, 0.3) or any(overlaps(rect, r, 0.3) for r in floor['obstacles']) or any(overlaps(rect, f['rect'], 0.25) for f in floor['furniture']):
                    continue
                if any(overlaps(rect, d['approach_rect'], 0.2) for d in self.doors if d['level'] == floor['level']):
                    continue
                identifier = f'ARC-L{floor["level"]:02d}-PLANTER-{j}'
                self.add(identifier, 'INT_PLANTERS', 3, floor['level'], box(rect, floor['ffl'], 0.48), 'office_planter')
                for k in (-1, 0, 1):
                    xy = local_xy(rect, k * 0.4, 0)
                    self.add(identifier + f'-LEAVES-{k:+d}', 'INT_FOLIAGE', 3, floor['level'],
                             ellipsoid([*xy, floor['ffl'] + 1.0], [0.3, 0.3, 0.58], 8, 4), 'office_foliage')
                floor['furniture'].append({'id': identifier, 'rect': rect, 'type': 'planter'})
        floor = self.floors[39]
        z = floor['ffl']
        rect = [-3.5, 2.4, 4.5, 0.9, 0]
        if self.fits(rect, floor, 1.15, 0.2) and not any(overlaps(rect, r, 0.25) for r in floor['obstacles']) and not any(overlaps(rect, f['rect'], 0.25) for f in floor['furniture']):
            self.add('ARC-L40-BAR', 'INT_HARDWARE', 3, 40, box(rect, z, 1.08), 'crown_bar_proxy', source_ids=['R10', 'U02'])
            self.add('ARC-L40-BAR-TOP', 'INT_WORKTOPS', 3, 40, box([-3.5, 2.4, 4.7, 1.05, 0], z + 1.08, 0.06), 'crown_bar_counter')
            floor['furniture'].append({'id': 'ARC-L40-BAR', 'rect': rect, 'type': 'bar'})
        else:
            self.omissions.append({'id': 'ARC-L40-BAR', 'reason': 'Inferred bar rejected by envelope, core or furniture clearance'})

    def finish(self):
        result = super().finish()
        for obj in result['objects']:
            if obj['category'] == 'INT_INTERIOR_GLASS':
                obj['opacity'] = 0.24
        result['detail_preset'] = 'architectural'
        result['architecture'] = self.architecture
        result['entrance_routes'] = [{'door': j + 1, 'start_m': [x, -28, self.floors[0]['ffl'] + 1.3],
                                     'end_m': [x, self.architecture['entrance']['screen_y_m'] - self.architecture['entrance']['door_diameter_m'] / 2 - 0.1, self.floors[0]['ffl'] + 1.3]}
                                    for j, x in enumerate(self.architecture['entrance']['door_centres_x_m'])]
        return result
