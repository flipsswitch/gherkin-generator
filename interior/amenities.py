import math

from interior.architectural_geometry import ring, split_polygon
from interior.geometry import box, combine, local_xy, prism, tube


class AmenityMixin:
    def configure_upper(self):
        p = self.architecture['upper_amenity']
        radius = p['mezzanine_radius_m']
        cx, cy = p['mezzanine_centre_m']
        points = [[cx + radius * math.cos(math.tau * j / 128), cy + radius * math.sin(math.tau * j / 128), 0] for j in range(128)]
        clipped, _ = split_polygon(points, lambda v: v[0] - p['mezzanine_flat_x_m'])
        obj = self.base['objects'][39]
        obj.update(kind='extrude', profile=[v[:2] for v in clipped], radius=radius, skip_atrium_guards=True)

    def floor_openings(self, level, openings):
        if level != 40:
            return super().floor_openings(level, openings)
        return self.architecture['upper_amenity']['service_penetrations_m_radians']

    def floor_opening_polygons(self, level):
        if level != 40:
            return []
        p = self.architecture['upper_amenity']
        x, y = p['stair_centre_m']
        radius = p['stair_opening_radius_m']
        return [[[x + radius * math.cos(math.tau * j / 96), y + radius * math.sin(math.tau * j / 96)] for j in range(96)]]

    def enclosure(self, identifier, rect, floor, height, wall, door_width, category, stage, role, door=True):
        if floor['level'] == 40 and role in ('stair_enclosure', 'service_enclosure', 'lift_shaft'):
            return
        if floor['level'] == 39 and role in ('stair_enclosure', 'lift_shaft'):
            height = min(height, 2.75)
        return super().enclosure(identifier, rect, floor, height, wall, door_width, category, stage, role, door)

    def stairs(self):
        all_floors = self.floors
        try:
            self.floors = all_floors[:39]
            super().stairs()
        finally:
            self.floors = all_floors
        p = self.architecture['upper_amenity']
        x, y = p['stair_centre_m']
        lower, upper = self.floors[38]['ffl'], self.floors[39]['ffl']
        count = p['stair_risers']
        rise = (upper - lower) / count
        inner, outer = p['stair_radii_m']
        for j in range(count):
            a = math.pi + math.tau * j / count
            b = math.pi + math.tau * (j + 1) / count
            poly = [[x + r * math.cos(t), y + r * math.sin(t)] for r, t in ((inner, a), (outer, a), (outer, b), (inner, b))]
            top = lower + (j + 1) * rise
            identifier = f'ARC-IRIS-STAIR-{j:02d}'
            self.add(identifier, 'INT_STAIRS', 1, 39, prism(poly, top - rise - 0.12, rise + 0.12),
                     'curved_amenity_stair_tread', source_ids=['R12'], evidence='Circular stair topology observed; radii, rise and going inferred',
                     riser_m=rise, angle_radians=b - a)
            mid = (a + b) / 2
            self.walks.append({'component': identifier, 'level': 39, 'xyz': [x + (inner + outer) / 2 * math.cos(mid), y + (inner + outer) / 2 * math.sin(mid), top]})
            for k, radius in enumerate((inner + 0.06, outer - 0.06)):
                pa = [x + radius * math.cos(a), y + radius * math.sin(a), top + 1.0]
                pb = [x + radius * math.cos(b), y + radius * math.sin(b), top + rise + 1.0]
                self.add(identifier + f'-RAIL-{k}', 'INT_RAILS', 1, 39,
                         combine([tube(pa, pb, 0.025), tube([pa[0], pa[1], top], pa, 0.016)]), 'amenity_stair_handrail')
        self.add('ARC-IRIS-TOP-LANDING', 'INT_STAIRS', 1, 40, box([x - 3.2, y + 0.45, 1.2, 1.2, 0], upper - 0.16, 0.16),
                 'amenity_stair_landing', source_ids=['R12'])
        self.add('ARC-IRIS-LIFT-GLASS', 'INT_INTERIOR_GLASS', 2, 39, ring(x, y, lower, 0.98, 0.955, upper - lower + 2.3, 48),
                 'panoramic_platform_lift_proxy', source_ids=['R12', 'R13'], evidence='Bar lift existence observed; central position and all dimensions inferred, no equipment certification')
        self.add('ARC-IRIS-LIFT-PLATFORM', 'INT_HARDWARE', 2, 39, tube([x, y, lower + 0.06], [x, y, lower + 0.18], 0.91, 48), 'amenity_lift_platform')
        self.add('ARC-IRIS-LIFT-HEADER', 'INT_HARDWARE', 2, 40, ring(x, y, upper + 2.25, 1.01, 0.90, 0.12, 48), 'amenity_lift_header')

    def finish_upper_structure(self):
        p = self.architecture['upper_amenity']
        x, y = p['stair_centre_m']
        floor = self.floors[39]
        floor['obstacles'] = [[x, y, p['stair_opening_radius_m'] * 2 + 0.2, p['stair_opening_radius_m'] * 2 + 0.2, 0]] + list(floor['openings'])
        self.floors[38]['obstacles'].append([x, y, 5.6, 5.6, 0])
        for item in self.floors[38:40]:
            item.setdefault('routing_keepouts', []).append([x, y, 5.6, 5.6, 0])
        floor['amenity_use'] = 'R12 Iris viewing mezzanine; footprint and setting-out inferred'
        z = floor['ffl']
        for j, (a, b) in enumerate(zip(floor['profile'], floor['profile'][1:] + floor['profile'][:1])):
            self.add(f'ARC-IRIS-PERIMETER-{j:03d}', 'INT_RAILS', 2, 40,
                     combine([tube([*a, z + 1.1], [*b, z + 1.1], 0.025), tube([*a, z], [*a, z + 1.1], 0.016)]),
                     'mezzanine_guardrail', source_ids=['R12'], evidence='Mezzanine edge inferred; guarding height and fixings not an engineered design')
        for j in range(48):
            a, b = math.tau * j / 48, math.tau * (j + 1) / 48
            if abs((a + b) / 2 - math.pi) < math.radians(24):
                continue
            r = p['stair_opening_radius_m']
            pa, pb = [x + r * math.cos(a), y + r * math.sin(a)], [x + r * math.cos(b), y + r * math.sin(b)]
            self.add(f'ARC-IRIS-VOID-GUARD-{j:02d}', 'INT_RAILS', 2, 40,
                     combine([tube([*pa, z + 1.1], [*pb, z + 1.1], 0.025), tube([*pa, z], [*pa, z + 1.1], 0.016)]), 'mezzanine_stairwell_guard')

    def plan_rooms(self):
        super().plan_rooms()
        floor = self.floors[37]
        p = self.architecture['upper_amenity']['private_dining']
        for j in range(5):
            angle = math.radians(p['start_angle_degrees'] + j * p['angle_step_degrees'])
            rect = [p['radius_m'] * math.cos(angle), p['radius_m'] * math.sin(angle), *p['room_size_m'], angle - math.pi / 2]
            self.room(f'ARC-L38-PRIVATE-DINING-{j + 1}', 'private_dining', rect, floor)

    def fitout(self):
        super().fitout()
        floor = self.floors[37]
        for room in floor['rooms']:
            if room['use'] != 'private_dining':
                continue
            rect, z = room['rect'], floor['ffl']
            self.add(room['id'] + '-TABLE', 'INT_WORKTOPS', 3, 38,
                     combine([box([*local_xy(rect, 0, 0.25), 2.6, 1.0, rect[4]], z + 0.72, 0.06),
                              box([*local_xy(rect, 0, 0.25), 0.2, 0.5, rect[4]], z, 0.72)]), 'private_dining_table', source_ids=['R12'])
            for j, (x, y) in enumerate([(x, y) for y in (-0.6, 1.1) for x in (-0.9, -0.3, 0.3, 0.9)]):
                xy = local_xy(rect, x, y)
                self.add(room['id'] + f'-CHAIR-{j}', 'INT_SEATING', 3, 38,
                         combine([box([*xy, 0.46, 0.44, rect[4]], z + 0.43, 0.07),
                                  box([*local_xy(rect, x, y + (0.22 if y > 0 else -0.22)), 0.46, 0.055, rect[4]], z + 0.5, 0.43),
                                  tube([*xy, z], [*xy, z + 0.43], 0.04)]), 'private_dining_chair')
