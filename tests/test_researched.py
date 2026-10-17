import copy
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gherkin
from interior.generator import generate, load_settings, validate_settings
from interior.geometry import area, box, clear_point, clear_segment, combine, mesh_health, perforated_slab, tube
from interior.validation import validate
from interior.validation_researched import EndpointIndex, researched_checks


class ResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = load_settings(gherkin.ROOT / 'interior/parameters-researched.json')
        cls.parameters = gherkin.load_parameters(gherkin.ROOT / 'research/parameters-exterior.json')
        cls.model = generate(cls.parameters, cls.settings)
        cls.report = validate(cls.model, cls.settings)

    def test_complete_researched_checks(self):
        self.assertTrue(self.report['passed'], [c for c in self.report['checks'] if not c['pass']])
        self.assertGreater(self.model['counts']['floor_power_outlet'], 500)
        self.assertEqual(self.model['counts']['floor_power_outlet'], self.model['counts']['workstation'])
        self.assertEqual(self.model['counts']['luminaire_proxy'], self.model['counts']['dali_interface_proxy'])

    def test_engineering_anchors_and_original_preset(self):
        p = self.parameters
        radius = gherkin.radius_function(p['profile_knots_z_radius_m'])
        self.assertAlmostEqual(p['height_m'], 179.8)
        self.assertAlmostEqual(radius(70.55) * 2, 56.15)
        self.assertAlmostEqual(radius(157.8) * 2, 30)
        self.assertAlmostEqual(self.model['floors'][-1]['ffl'], 167.1)
        self.assertAlmostEqual(p['slab_thickness_m'], 0.16)
        self.assertEqual(gherkin.load_parameters()['height_m'], 180)
        self.assertEqual(gherkin.load_parameters()['regular_height_module_m'], 4.2)

    def test_lift_topology_and_declared_uncertainty(self):
        lifts = self.model['lift_schedule']
        self.assertEqual(sum(l['bank'] != 'upper-concept' for l in lifts), 16)
        self.assertEqual(sum(l['bank'] == 'upper-concept' for l in lifts), 2)
        self.assertTrue(all('inferred' in l['evidence'] or 'assumed' in l['evidence'] for l in lifts))
        self.assertIn('unresolved', self.settings['lifts']['evidence'])
        self.assertEqual(self.model['counts']['raised_floor_panel'], 40)

    def test_rotated_openings_are_watertight(self):
        poly = [[-15,-15],[15,-15],[15,15],[2,15],[2,13],[-2,13],[-2,15],[-15,15]]
        holes = [[-5,0,2.3,2.4,math.pi / 3],[5,0,2.3,2.4,math.pi * 4 / 3],[0,6,2.9,5.17,-math.pi / 6]]
        vertices,faces = perforated_slab(poly,holes,100,0.16)
        health = mesh_health(vertices,faces)
        self.assertTrue(health['closed_oriented'])
        self.assertEqual(health['degenerate_triangles'], 0)
        self.assertAlmostEqual(health['signed_volume_m3'],(area(poly) - sum(r[2] * r[3] for r in holes)) * 0.16,delta=0.0001)

    def test_parameter_safety_bounds(self):
        for key,value in [('luminaire_grid_m',0.001),('outlets_per_circuit',0),('control_route_height_m',4.0)]:
            changed = copy.deepcopy(self.settings)
            changed['electrical'][key] = value
            with self.subTest(parameter=key), self.assertRaises(ValueError):
                validate_settings(changed)


class ElectricalReadbackTests(unittest.TestCase):
    def test_native_precision_does_not_split_a_graph_node_at_a_rounding_boundary(self):
        index = EndpointIndex()
        first = index.resolve([1.000049,2,100])
        self.assertEqual(index.resolve([1.000051,2,100],False),first)
        self.assertIsNone(index.resolve([1.001,2,100],False))

    def test_narrow_atrium_crossing_is_rejected_between_samples(self):
        poly = [[-2,-2],[2,-2],[2,2],[0.13,2],[0.13,-0.05],[0.10,-0.05],[0.10,2],[-2,2]]
        self.assertTrue(all(clear_point(p,poly,0.06) for p in ([-1,0],[0,0],[1,0])))
        self.assertFalse(clear_segment([-1,0],[1,0],poly,0.012))

    def test_disconnected_actual_mesh_fails_even_with_unchanged_metadata(self):
        route = tube([0,0,0],[2,0,0],0.012)
        outlet = box([2,0,0.2,0.16,0],-0.04,0.04)
        vertices,faces = combine([route,outlet])
        obj = {'name':'TEST','vertices':vertices,'triangles':faces}
        components = [
            {'id':'R','role':'electrical_route','level':1,'system':'POWER','object':'TEST','vertex_offset':0,'vertex_count':16,
             'face_offset':0,'face_count':len(route[1]),'endpoint_ring_size':8,'radius_m':0.012},
            {'id':'O','role':'floor_power_outlet','level':1,'system':'POWER','object':'TEST','vertex_offset':16,'vertex_count':8,
             'face_offset':len(route[1]),'face_count':len(outlet[1]),'connection_m':[2,0,0]},
        ]
        recipe = {'components':components,'electrical_networks':[{'system':'POWER','source_m':[0,0,0],'terminals':['O']}],
                  'electrical_circuits':[{'terminals':['O']}],'floors':[{'profile':[[-3,-3],[3,-3],[3,3],[-3,3]]}]}
        checks = researched_checks(recipe,{}, {'TEST':obj})
        self.assertTrue(all(c['pass'] for c in checks))
        altered = copy.deepcopy(obj)
        for p in altered['vertices'][8:16]:
            p[0] -= 0.4
        checks = researched_checks(recipe,{}, {'TEST':altered})
        self.assertFalse(next(c['pass'] for c in checks if c['check'] == 'electrical_terminals_connected_to_source'))


if __name__ == '__main__':
    unittest.main()
