import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gherkin
from interior.architectural import ArchitecturalBuilder
from interior.architectural_geometry import ellipsoid, hollow_member, rectangular_member, ring, subtract_portal, triangle_fan, triangular_member
from interior.generator import default_exterior, default_settings, load_settings, validate_settings
from interior.geometry import area, in_rect, mesh_health, perforated_slab
from interior.researched import ResearchBuilder
from interior.validation import layout_checks
from interior.validation_architectural import architectural_checks, segment_triangle


class ArchitecturalPrimitiveTests(unittest.TestCase):
    def test_electrical_routing_preserves_amenity_keepouts(self):
        builder = ResearchBuilder.__new__(ResearchBuilder)
        builder.settings = {'variant': 'researched', 'services': {'routing_grid_m': 0.5}}
        builder.exterior = {'floor_radial_inset_m': 0.1}
        builder.stair_rects, builder.lifts, builder.shaft_rects = [], [], []
        builder.pipe_route_obstacles, builder.omissions = [], []
        builder.electrical_routing = True
        builder.radius = lambda z: 20
        keepout = [0, 0, 3, 3, 0]
        floor = {'level': 40, 'ffl': 167.1, 'profile': [[-8, -8], [8, -8], [8, 8], [-8, 8]], 'routing_keepouts': [keepout]}
        for height in (3.0, 2.9):
            segments, ends, _, _ = builder.route_tree(floor, [-4, 0], [{'id': 'light', 'xy': [4, 0]}], height)
            self.assertEqual(len(ends), 1)
            self.assertEqual(floor['routing_keepouts'], [keepout])
            for a, b in segments:
                count = max(1, math.ceil(math.dist(a, b) / 0.1))
                self.assertFalse(any(in_rect([a[k] + (b[k] - a[k]) * j / count for k in (0, 1)], keepout) for j in range(count + 1)))

    def test_oblique_closed_positive_members(self):
        a, b = [2, -7, 169], [-5, 8, 178]
        for mesh in (triangular_member(a, b, 0.11, 0.15), rectangular_member(a, b, 0.68, 0.38),
                     hollow_member(a, b, 0.254, 0.1365, 0.04, 0.0125), ring(2, 3, 179, 2.25, 1.2, 0.18),
                     ellipsoid([0, 0, 5], [1.2, 1.1, 1.9])):
            health = mesh_health(*mesh)
            self.assertTrue(health['closed_oriented'])
            self.assertEqual(health['degenerate_triangles'], 0)
            self.assertGreater(health['signed_volume_m3'], 0)

    def test_hollow_section_material_volume(self):
        mesh = hollow_member([0, 0, 0], [0, 0, 8], 0.254, 0.254, 0.04, 0.04)
        polygon_area = 24 * math.sin(math.tau / 24) / 2 * (0.254 ** 2 - 0.214 ** 2)
        self.assertAlmostEqual(mesh_health(*mesh)['signed_volume_m3'], polygon_area * 8, delta=0.00001)

    def test_portal_removes_front_glass_but_keeps_rear(self):
        portal = [[-2, 0], [2, 0], [2, 5], [-2, 5]]
        for y in (-5, 5):
            triangle = [[-4, y, 1], [4, y, 1], [0, y, 8]]
            pieces = subtract_portal(triangle, portal, -3)
            triangles = []
            for poly in pieces:
                vertices, faces = triangle_fan(poly)
                triangles.extend([vertices[i] for i in face] for face in faces)
            hit = any(segment_triangle([0, -10, 2], [0, 10, 2], face) for face in triangles)
            self.assertEqual(hit, y == 5)

    def test_bad_section_and_door_settings_rejected(self):
        p = load_settings(default_settings('architectural'))
        bad = copy.deepcopy(p)
        bad['architecture']['crown']['section_m'] = [0.5, 0.5]
        with self.assertRaises(ValueError):
            validate_settings(bad)
        bad = copy.deepcopy(p)
        bad['architecture']['entrance']['door_centres_x_m'] = [-1, 0, 1, 2]
        with self.assertRaises(ValueError):
            validate_settings(bad)

    def test_circular_opening_removes_real_slab_volume(self):
        opening = [[3 * math.cos(math.tau * j / 64), 3 * math.sin(math.tau * j / 64)] for j in range(64)]
        mesh = perforated_slab([[-10, -10], [10, -10], [10, 10], [-10, 10]], [], 167, 0.16, [opening])
        health = mesh_health(*mesh)
        self.assertTrue(health['closed_oriented'])
        self.assertEqual(health['degenerate_triangles'], 0)
        self.assertAlmostEqual(health['signed_volume_m3'], (400 - area(opening)) * 0.16, delta=0.00001)


class ArchitecturalReadbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_settings(default_settings('architectural'))
        builder = ArchitecturalBuilder(gherkin.load_parameters(default_exterior(cls.settings)), cls.settings)
        builder.shell_and_core()
        builder.plan_rooms()
        builder.fitout()
        cls.model = builder.finish()
        cls.objects = {o['name']: o for o in cls.model['objects']}

    def test_section_lens_door_and_approach_checks(self):
        checks = architectural_checks(self.model, self.settings, self.objects)
        self.assertTrue(all(c['pass'] for c in checks), checks)
        self.assertEqual(self.model['counts']['crown_triangular_member'], 432)
        self.assertNotIn('dome_lattice_proxy', self.model['counts'])

    def test_private_dining_door_approaches_clear_shuttles(self):
        checks = layout_checks(self.model)
        self.assertTrue(all(c['pass'] for c in checks), checks)

    def test_native_lens_damage_is_detected(self):
        objects = dict(self.objects)
        name = next(n for n in objects if n.startswith('ARC-APEX-LENS'))
        objects[name] = copy.deepcopy(objects[name])
        for vertex in objects[name]['vertices']:
            vertex[0] *= 1.3
        checks = architectural_checks(self.model, self.settings, objects)
        self.assertFalse(next(c['pass'] for c in checks if c['check'] == 'R06_native_apex_lens_diameter_and_height'))

    def test_native_glass_blocking_entry_is_detected(self):
        objects = dict(self.objects)
        name = next(n for n in objects if n.startswith('ARC-FACADE'))
        objects[name] = copy.deepcopy(objects[name])
        n = len(objects[name]['vertices'])
        objects[name]['vertices'].extend([[-12, -25, 0], [12, -25, 0], [12, -25, 4], [-12, -25, 4]])
        objects[name]['triangles'].extend([[n, n + 1, n + 2], [n, n + 2, n + 3]])
        checks = architectural_checks(self.model, self.settings, objects)
        self.assertFalse(next(c['pass'] for c in checks if c['check'] == 'entrance_approaches_have_real_facade_openings'))


if __name__ == '__main__':
    unittest.main()
