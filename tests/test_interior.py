import copy
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gherkin
from interior.generator import generate, load_settings, validate_settings
from interior.geometry import area, mesh_health, perforated_slab
from interior.validation import layout_checks, segment_distance_3d, validate


class InteriorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_settings()
        cls.model = generate(settings=cls.settings)
        cls.report = validate(cls.model, cls.settings)

    def test_complete_design_checks(self):
        self.assertTrue(self.report['passed'], [c for c in self.report['checks'] if not c['pass']])
        self.assertEqual(self.model['counts']['perforated_slab'], 40)
        self.assertEqual(self.model['counts']['stair_flight'], 160)
        self.assertEqual(self.model['counts']['lift_car'], 6)
        self.assertEqual(self.model['counts']['washbasin'], 74)
        self.assertEqual(sum(r['use'] == 'plant' for r in self.model['rooms']), 2)

    def test_original_exterior_is_preserved(self):
        reference = json.loads(Path(__file__).with_name('reference.json').read_text())
        shell = [o for o in self.model['objects'] if o['category'].startswith('GHR_')]
        self.assertEqual(len(shell), 89)
        for obj in shell:
            self.assertEqual(gherkin.geometry_digest(obj['vertices'], obj['triangles']), reference['meshes'][obj['name']]['digest'])

    def test_concave_slab_with_multiple_real_openings(self):
        profile = [[-6, -5], [6, -5], [6, 5], [2, 5], [2, 3], [-2, 3], [-2, 5], [-6, 5]]
        holes = [[-3, 0, 1.5, 2, 0], [3, 0, 1.5, 2, 0]]
        vertices, faces = perforated_slab(profile, holes, 12, 0.25)
        health = mesh_health(vertices, faces)
        self.assertTrue(health['closed_oriented'])
        self.assertEqual(health['degenerate_triangles'], 0)
        self.assertAlmostEqual(health['signed_volume_m3'], (area(profile) - 6) * 0.25)
        with self.assertRaises(ValueError):
            perforated_slab(profile, holes + [holes[0]], 12, 0.25)

    def test_stable_component_mapping_and_evidence(self):
        components = self.model['components']
        self.assertEqual(len({c['id'] for c in components}), len(components))
        objects = {o['name']: o for o in self.model['objects']}
        for comp in components:
            obj = objects[comp['object']]
            self.assertIn(comp['id'], obj['component_ids'])
            self.assertLessEqual(comp['vertex_offset'] + comp['vertex_count'], len(obj['vertices']))
            self.assertLessEqual(comp['face_offset'] + comp['face_count'], len(obj['triangles']))
            self.assertEqual(comp['evidence'], 'assumed')

    def test_pipe_distance_detects_crossings_and_clearance(self):
        self.assertAlmostEqual(segment_distance_3d([-1, 0, 0], [1, 0, 0], [0, -1, 0], [0, 1, 0]), 0)
        self.assertAlmostEqual(segment_distance_3d([-1, 0, 0], [1, 0, 0], [-1, 0, 0.12], [1, 0, 0.12]), 0.12)
        self.assertAlmostEqual(segment_distance_3d([0, 0, 0], [0, 0, 4], [-1, 0, 2], [1, 0, 2]), 0)

    def test_missing_native_geometry_cannot_pass(self):
        result = validate(self.model, self.settings, self.model['objects'][1:])
        self.assertFalse(result['passed'])

    def test_door_obstruction_is_detected(self):
        changed = dict(self.model)
        changed['doors'] = copy.deepcopy(self.model['doors'])
        changed['doors'][0]['approach_rect'] = [1.65, 0, 1, 1, 0]
        self.assertTrue(any(not c['pass'] for c in layout_checks(changed)))

    def test_unsafe_or_unbounded_parameters_are_rejected(self):
        for group, name, value in [('stairs', 'going_m', math.nan), ('stairs', 'risers_per_flight', 100000),
                                   ('fitout', 'grid_m', [0, 2]), ('services', 'routing_grid_m', 0.001),
                                   ('mesh_limits', 'components_per_object', 100000), ('services', 'head_grid_multiple', 0)]:
            settings = copy.deepcopy(self.settings)
            settings[group][name] = value
            with self.subTest(parameter=name), self.assertRaises(ValueError):
                validate_settings(settings)


if __name__ == '__main__':
    unittest.main()
