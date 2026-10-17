import copy
import json
import math
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gherkin


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parameters = gherkin.load_parameters()
        cls.model = gherkin.generate(cls.parameters)
        cls.reference = json.loads((Path(__file__).with_name('reference.json')).read_text())

    def test_original_native_mesh_fingerprints(self):
        for obj in self.model['objects']:
            if obj['kind'] != 'mesh':
                continue
            with self.subTest(object=obj['name']):
                reference = self.reference['meshes'][obj['name']]
                self.assertEqual(gherkin.geometry_digest(obj['vertices'], obj['triangles']), reference['digest'])
                self.assertEqual(len(obj['vertices']), reference['vertices'])
                self.assertEqual(len(obj['triangles']), reference['triangles'])
                self.assertLessEqual(len(obj['vertices']), 512)
                self.assertLessEqual(len(obj['triangles']), 1024)

    def test_original_native_floors(self):
        for obj in self.model['objects'][:40]:
            with self.subTest(object=obj['name']):
                reference = self.reference['floors'][obj['name']]
                self.assertAlmostEqual(obj['elevation'], reference['elevation'], places=8)
                self.assertAlmostEqual(obj['thickness'], reference['thickness'], places=8)
                if obj['kind'] == 'cylinder':
                    volume = math.pi * obj['radius'] ** 2 * obj['thickness']
                else:
                    profile = obj['profile']
                    volume = obj['thickness'] * sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(profile, profile[1:] + profile[:1])) / 2
                    self.assertEqual(len(profile), len(reference['profile_m']))
                    self.assertLess(max(min(math.dist(p, v) for v in reference['profile_m']) for p in profile), 1e-7)
                self.assertAlmostEqual(volume, reference['volume'], delta=1e-6)

    def assert_closed_positive_mesh(self, vertices, triangles):
        directed = Counter()
        for a, b, c in triangles:
            self.assertEqual(len({a, b, c}), 3)
            self.assertGreater(gherkin.length(gherkin.cross(gherkin.sub(vertices[b], vertices[a]), gherkin.sub(vertices[c], vertices[a]))), 1e-10)
            directed.update([(a, b), (b, c), (c, a)])
        self.assertTrue(all(count == 1 and directed[(b, a)] == 1 for (a, b), count in directed.items()))
        volume = sum(gherkin.dot(vertices[a], gherkin.cross(vertices[b], vertices[c])) / 6 for a, b, c in triangles)
        self.assertGreater(volume, 0)
        return volume

    def test_closed_floor_meshes_and_volumes(self):
        for obj in self.model['objects'][:40]:
            with self.subTest(object=obj['name']):
                vertices, triangles = gherkin.mesh_for_object(obj)
                volume = self.assert_closed_positive_mesh(vertices, triangles)
                expected = self.reference['floors'][obj['name']]['volume']
                tolerance = expected * 0.000026 if obj['kind'] == 'cylinder' else 1e-6
                self.assertAlmostEqual(volume, expected, delta=tolerance)

    def test_both_member_families_are_closed_and_connected(self):
        nodes = {node['id']: node['xyz'] for node in self.model['nodes']}
        self.assertEqual(len(nodes), 378)
        self.assertEqual(Counter(m['family'] for m in self.model['members']), {'A': 360, 'B': 360})
        self.assertEqual(len({m['id'] for m in self.model['members']}), 720)
        self.assertEqual(len({tuple(sorted((m['start_node'], m['end_node']))) for m in self.model['members']}), 720)
        objects = {obj['name']: obj for obj in self.model['objects']}
        for member in self.model['members']:
            self.assertEqual(member['start'], nodes[member['start_node']])
            self.assertEqual(member['end'], nodes[member['end_node']])
            obj = objects[member['object']]
            offset = member['vertex_offset']
            vertices = obj['vertices'][offset:offset + member['vertex_count']]
            triangles = [[i - offset for i in face] for face in obj['triangles'][member['face_offset']:member['face_offset'] + member['face_count']]]
            volume = self.assert_closed_positive_mesh(vertices, triangles)
            expected = 4 * math.sin(math.pi / 4) * self.parameters['diagrid_member_radius_m'] ** 2 * math.dist(member['start'], member['end'])
            self.assertAlmostEqual(volume, expected, delta=1e-7)

    def test_facade_seam_crown_and_open_base(self):
        facade = self.model['facade']
        vertices, faces = facade['vertices'], facade['faces']
        self.assertEqual(len(vertices), 6337)
        self.assertEqual(len(faces), 12600)
        self.assertEqual(sum(v == [0, 0, 180] for v in vertices), 1)
        self.assertEqual(len({f['id'] for f in faces}), len(faces))
        self.assertEqual(len({tuple(sorted(f['vertices'])) for f in faces}), len(faces))
        directed = Counter()
        for face in faces:
            a, b, c = face['vertices']
            directed.update([(a, b), (b, c), (c, a)])
            normal = gherkin.cross(gherkin.sub(vertices[b], vertices[a]), gherkin.sub(vertices[c], vertices[a]))
            center = gherkin.scale(gherkin.add(gherkin.add(vertices[a], vertices[b]), vertices[c]), 1 / 3)
            self.assertGreater(gherkin.dot(normal, [center[0], center[1], 0]), 0)
        boundary = [(a, b) for a, b in directed if (b, a) not in directed]
        self.assertEqual(len(boundary), 72)
        self.assertTrue(all(vertices[a][2] == vertices[b][2] == 0 for a, b in boundary))
        self.assertTrue(all(count == 1 for count in directed.values()))
        mapped_faces = [face_id for obj in self.model['objects'] for face_id in obj.get('logical_face_ids', [])]
        self.assertEqual(sorted(mapped_faces), sorted(face['id'] for face in faces))

    def test_envelope_and_six_recesses(self):
        radius = gherkin.radius_function(self.parameters['profile_knots_z_radius_m'])
        for z, r in self.parameters['profile_knots_z_radius_m']:
            self.assertAlmostEqual(radius(z), r)
        for left, right in zip(self.parameters['profile_knots_z_radius_m'], self.parameters['profile_knots_z_radius_m'][1:]):
            for step in range(101):
                r = radius(left[0] + (right[0] - left[0]) * step / 100)
                self.assertGreaterEqual(r + 1e-8, min(left[1], right[1]))
                self.assertLessEqual(r - 1e-8, max(left[1], right[1]))
        self.assertEqual(sum(obj['kind'] == 'extrude' for obj in self.model['objects']), 33)
        for obj in self.model['objects'][:40]:
            if obj['kind'] != 'extrude':
                continue
            self.assertEqual(len(obj['profile']), 102)
            inner = [math.hypot(*xy) < obj['radius'] * 0.8 for xy in obj['profile']]
            self.assertEqual(sum(a != b for a, b in zip(inner, inner[1:] + inner[:1])), 12)

    def test_counts_and_finite_coordinates(self):
        self.assertEqual(self.model['counts'], self.reference['counts'])
        self.assertEqual(len({o['name'] for o in self.model['objects']}), 129)
        for obj in self.model['objects']:
            vertices, _ = gherkin.mesh_for_object(obj)
            self.assertTrue(all(math.isfinite(v) for xyz in vertices for v in xyz))

    def test_invalid_inputs_fail_before_cad(self):
        cases = [('height_m', math.nan), ('units', 'feet'), ('slab_thickness_m', -1),
                 ('glazing_samples_per_ring', 1000000), ('atrium_angular_width_deg', 60),
                 ('glazing_clear_opacity', 1.1), ('diagrid_ring_step_m', 8.3)]
        for key, value in cases:
            parameters = copy.deepcopy(self.parameters)
            parameters[key] = value
            with self.subTest(parameter=key), self.assertRaises(ValueError):
                gherkin.generate(parameters)


if __name__ == '__main__':
    unittest.main()
