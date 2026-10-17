import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from gherkin import cross, dot, generate, geometry_digest, load_parameters, mesh_for_object, sub, write_json


def material(name, opacity):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    colors = {'GHR_FLOORS': (0.42, 0.49, 0.53), 'GHR_DIAGRID': (0.66, 0.71, 0.73),
              'GHR_GLAZING_CLEAR': (0.19, 0.43, 0.53), 'GHR_GLAZING_DARK': (0.025, 0.08, 0.12)}
    color = colors[name]
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Metallic'].default_value = 0.35 if name == 'GHR_DIAGRID' else 0.08
    shader.inputs['Roughness'].default_value = 0.32 if opacity == 1 else 0.19
    shader.inputs['Alpha'].default_value = opacity
    mat.diffuse_color = (*color, opacity)
    if hasattr(mat, 'surface_render_method'):
        mat.surface_render_method = 'DITHERED'
    return mat


def read_mesh(obj):
    obj.data.calc_loop_triangles()
    return ([[float(v) for v in obj.matrix_world @ vertex.co] for vertex in obj.data.vertices],
            [list(face.vertices) for face in obj.data.loop_triangles])


def validate(scene, recipe):
    checks = []
    expected_names = {item['name'] for item in recipe['objects']}
    actual_names = {obj.name for obj in scene.objects if obj.type == 'MESH'}
    checks.append({'check': 'mesh_object_names', 'pass': actual_names == expected_names, 'actual': len(actual_names)})
    checks.append({'check': 'metre_units', 'pass': scene.unit_settings.system == 'METRIC' and scene.unit_settings.scale_length == 1})
    readback, maximum_error = [], 0.0
    for expected in recipe['objects']:
        obj = scene.objects.get(expected['name'])
        if obj is None or obj.type != 'MESH':
            checks.append({'check': expected['name'], 'pass': False, 'reason': 'missing mesh'})
            continue
        vertices, triangles = read_mesh(obj)
        target_vertices, target_triangles = mesh_for_object(expected)
        same_topology = triangles == target_triangles
        error = max((math.dist(a, b) for a, b in zip(vertices, target_vertices)), default=math.inf)
        maximum_error = max(maximum_error, error)
        finite = all(math.isfinite(value) for xyz in vertices for value in xyz)
        opacity = obj.data.materials[0].node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value
        valid = (same_topology and len(vertices) == len(target_vertices) and finite and error <= 0.00002
                 and abs(opacity - expected['opacity']) < 1e-6 and obj.get('gherkin_id') == expected['name']
                 and any(c.name == expected['category'] for c in obj.users_collection))
        volume = sum(dot(vertices[a], cross(vertices[b], vertices[c])) / 6 for a, b, c in triangles)
        if not expected['category'].startswith('GHR_GLAZING'):
            valid = valid and volume > 0
        checks.append({'check': expected['name'], 'pass': valid, 'maximum_vertex_error_m': error,
                       'vertices': len(vertices), 'triangles': len(triangles), 'opacity': opacity})
        readback.append({'id': obj.name, 'vertices_m': vertices, 'triangles': triangles,
                         'geometry_digest': geometry_digest(vertices, triangles), 'signed_volume_m3': volume,
                         'opacity': opacity})
    return {'passed': all(c['pass'] for c in checks), 'checks': checks, 'maximum_vertex_error_m': maximum_error,
            'source': 'Blender native mesh data after reopening the saved blend file'}, readback


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def presentation(scene):
    collection = bpy.data.collections.new('PRESENTATION')
    scene.collection.children.link(collection)
    camera = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = 220
    camera.data.clip_end = 2000
    camera.location = (240, -350, 215)
    aim(camera, (0, 0, 88))
    collection.objects.link(camera)
    scene.camera = camera
    for name, position, energy, size in [('Key', (100, -130, 230), 3500000, 130),
                                         ('Fill', (-100, -50, 110), 1700000, 100),
                                         ('Rim', (20, 130, 180), 3000000, 100)]:
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, 'AREA'))
        light.location = position
        light.data.energy = energy
        light.data.shape = 'DISK'
        light.data.size = size
        aim(light, (0, 0, 90))
        collection.objects.link(light)
    world = bpy.data.worlds.new('Studio')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.55, 0.62, 0.68, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.55
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.cycles.transparent_max_bounces = 64
    scene.render.resolution_x = 1000
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = False
    scene.render.use_stamp = False
    scene.view_settings.view_transform = 'AgX'
    return camera


def render_views(scene, output):
    camera = scene.camera
    scene.render.filepath = str(output / 'isometric.png')
    bpy.ops.render.render(write_still=True)
    camera.location = (0, -400, 90)
    aim(camera, (0, 0, 90))
    scene.render.filepath = str(output / 'elevation.png')
    bpy.ops.render.render(write_still=True)
    camera.location = (220, -350, 200)
    aim(camera, (0, 0, 88))
    changed = []
    try:
        for obj in list(scene.objects):
            if obj.type != 'MESH':
                continue
            original = obj.data
            obj.data = original.copy()
            changed.append((obj, original, obj.data))
            mesh = bmesh.new()
            mesh.from_mesh(obj.data)
            bmesh.ops.bisect_plane(mesh, geom=list(mesh.verts) + list(mesh.edges) + list(mesh.faces),
                                  dist=1e-6, plane_co=(0, 0, 0), plane_no=(0, 1, 0), clear_inner=True)
            mesh.to_mesh(obj.data)
            mesh.free()
        scene.render.filepath = str(output / 'cutaway.png')
        bpy.ops.render.render(write_still=True)
    finally:
        for obj, original, temporary in changed:
            obj.data = original
            bpy.data.meshes.remove(temporary)
        camera.location = (240, -350, 215)
        aim(camera, (0, 0, 88))


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description='Build and verify a native Blender Gherkin without an MCP server.')
    parser.add_argument('--parameters', type=Path, default=ROOT / 'parameters.json')
    parser.add_argument('--output-dir', type=Path, default=Path('gherkin-blender'))
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--glb', action='store_true')
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if not bpy.app.background:
        parser.error('Run with blender --background --python blender_gherkin.py -- ... to protect open work')
    parameters = load_parameters(args.parameters)
    recipe = generate(parameters)
    if args.verify:
        bpy.ops.wm.open_mainfile(filepath=str(args.verify.resolve()))
        report, _ = validate(bpy.context.scene, recipe)
        print(json.dumps({k: v for k, v in report.items() if k != 'checks'}))
        if not report['passed']:
            raise RuntimeError('Saved model verification failed')
        return
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    log = []

    def record(event, **values):
        log.append({'elapsed_seconds': round(time.perf_counter() - started, 6), 'event': event, **values})
        write_json(output / 'run-log.json', log)

    try:
        record('started', blender_version=bpy.app.version_string, python_version=sys.version.split()[0])
        bpy.ops.wm.read_factory_settings(use_empty=True)
        scene = bpy.context.scene
        scene.name = 'Gherkin'
        scene.unit_settings.system = 'METRIC'
        scene.unit_settings.scale_length = 1
        scene['recipe'] = parameters['spec_id']
        scene['accuracy'] = recipe['representation']
        collections, materials = {}, {}
        write_json(output / 'parameters.json', parameters)
        for index, item in enumerate(recipe['objects']):
            category = item['category']
            if category not in collections:
                collections[category] = bpy.data.collections.new(category)
                scene.collection.children.link(collections[category])
                materials[category] = material(category, item['opacity'])
            vertices, triangles = mesh_for_object(item)
            mesh = bpy.data.meshes.new(item['name'])
            mesh.from_pydata(vertices, [], triangles)
            mesh.update()
            if mesh.validate(verbose=False):
                raise RuntimeError('Blender had to repair a generated mesh: ' + item['name'])
            obj = bpy.data.objects.new(item['name'], mesh)
            obj['gherkin_id'] = item['name']
            obj['representation'] = item['kind']
            collections[category].objects.link(obj)
            mesh.materials.append(materials[category])
            if (index + 1) in (40, 85):
                record('stage_complete', objects=index + 1)
        presentation(scene)
        model_path = output / 'gherkin.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(model_path))
        record('saved', objects=len(recipe['objects']))
        bpy.ops.wm.open_mainfile(filepath=str(model_path))
        scene = bpy.context.scene
        report, readback = validate(scene, recipe)
        report['blender_version'] = bpy.app.version_string
        report['circular_floor_segments'] = 512
        report['maximum_circular_floor_sagitta_m'] = max(o['radius'] for o in recipe['objects'] if o['kind'] == 'cylinder') * (1 - math.cos(math.pi / 512))
        write_json(output / 'validation.json', report)
        write_json(output / 'native-readback.json', readback)
        write_json(output / 'object-mapping.json', {'counts': recipe['counts'],
                   'objects': [{'id': o['name'], 'native_name': o['name'], 'collection': o['category'],
                                'logical_vertex_ids': o.get('logical_vertex_ids'), 'logical_face_ids': o.get('logical_face_ids')} for o in recipe['objects']],
                   'nodes': recipe['nodes'], 'members': recipe['members'], 'floors': recipe['floors']})
        record('reopened_and_validated', passed=report['passed'], maximum_vertex_error_m=report['maximum_vertex_error_m'])
        if not report['passed']:
            raise RuntimeError('Native geometry failed verification; inspect validation.json')
        if args.glb:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in scene.objects:
                obj.select_set(obj.type == 'MESH')
            bpy.ops.export_scene.gltf(filepath=str(output / 'gherkin.glb'), export_format='GLB', use_selection=True,
                                      export_cameras=False, export_lights=False, export_extras=True)
            record('exported_glb')
        if args.render:
            render_views(scene, output)
            record('rendered', images=['isometric.png', 'elevation.png', 'cutaway.png'])
        record('complete', counts=recipe['counts'])
        print(json.dumps({'passed': True, 'counts': recipe['counts'], 'elapsed_seconds': time.perf_counter() - started}))
    except Exception as error:
        record('error', type=type(error).__name__, message=str(error))
        raise


if __name__ == '__main__':
    main()
