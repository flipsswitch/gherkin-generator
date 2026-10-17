import argparse
import gzip
import json
import sys
import time
from pathlib import Path

import bmesh
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import blender_gherkin as host
from gherkin import load_parameters, write_json
from interior.generator import COLORS, generate, load_settings, schedules
from interior.validation import validate


def material(category, opacity):
    if category.startswith('GHR_'):
        return host.material(category, opacity)
    mat = bpy.data.materials.new(category)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    color = COLORS[category][0]
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = 0.65
    shader.inputs['Metallic'].default_value = 0.3 if category in ('INT_FIRE', 'INT_COLD', 'INT_HOT', 'INT_RAILS') else 0
    mat.diffuse_color = (*color, 1)
    return mat


def capture(scene, output, recipe, level):
    floor = recipe['floors'][level - 1]
    z = floor['ffl']
    camera = scene.camera
    meshes = [o for o in scene.objects if o.type == 'MESH']
    original_hidden = {o.name: o.hide_render for o in meshes}
    scene.render.resolution_x, scene.render.resolution_y = 1400, 1400
    try:
        for obj in meshes:
            obj.hide_render = obj.get('level') != level or obj.get('stage') == 4
        camera.data.ortho_scale = floor['radius'] * 2.3
        camera.location = (0, -0.001, z + 80)
        host.aim(camera, (0, 0, z))
        scene.render.filepath = str(output / 'floor-plan.png')
        bpy.ops.render.render(write_still=True)
        camera.location = (48, -64, z + 58)
        host.aim(camera, (0, 0, z + 0.8))
        scene.render.filepath = str(output / 'furnished-floor.png')
        bpy.ops.render.render(write_still=True)
        for obj in meshes:
            obj.hide_render = obj.get('level') != level or obj.get('stage') == 3
        camera.location = (0, -0.001, z + 80)
        host.aim(camera, (0, 0, z))
        scene.render.filepath = str(output / 'services-plan.png')
        bpy.ops.render.render(write_still=True)
        for obj in meshes:
            obj.hide_render = any(c.name.startswith('GHR_GLAZING') for c in obj.users_collection)
        changed = []
        try:
            for obj in meshes:
                if obj.hide_render:
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
            camera.data.ortho_scale = 205
            camera.location = (230, -370, 210)
            host.aim(camera, (0, 0, 86))
            scene.render.resolution_x, scene.render.resolution_y = 1000, 1400
            scene.render.filepath = str(output / 'interior-cutaway.png')
            bpy.ops.render.render(write_still=True)
        finally:
            for obj, original, temporary in changed:
                obj.data = original
                bpy.data.meshes.remove(temporary)
    finally:
        for obj in meshes:
            obj.hide_render = original_hidden[obj.name]


def main():
    started = time.perf_counter()
    parser = argparse.ArgumentParser(description='Generate the separate conceptual interior in Blender.')
    parser.add_argument('--parameters', type=Path, default=ROOT / 'interior/parameters.json')
    parser.add_argument('--exterior-parameters', type=Path, default=ROOT / 'parameters.json')
    parser.add_argument('--output-dir', type=Path, default=Path('outputs/gherkin-interior'))
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--glb', action='store_true')
    parser.add_argument('--capture-level', type=int, default=20)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    if not bpy.app.background:
        parser.error('Run in background mode to protect open work')
    if not 1 <= args.capture_level <= 40:
        parser.error('Capture level must be between 1 and 40')
    settings, exterior = load_settings(args.parameters), load_parameters(args.exterior_parameters)
    if args.verify:
        recipe = generate(exterior, settings)
        bpy.ops.wm.open_mainfile(filepath=str(args.verify.resolve()))
        native, readback = host.validate(bpy.context.scene, recipe)
        design = validate(recipe, settings, readback)
        print(json.dumps({'native_passed': native['passed'], 'design_passed': design['passed'], 'checks': len(design['checks'])}))
        if not native['passed'] or not design['passed']:
            raise RuntimeError('Reopened interior verification failed')
        return
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    log = []
    def record(event, **values):
        log.append({'elapsed_seconds': round(time.perf_counter() - started, 6), 'event': event, **values})
        write_json(output / 'run-log.json', log)
        print(json.dumps(log[-1]), flush=True)
    try:
        record('started', blender_version=bpy.app.version_string, python_version=sys.version.split()[0])
        recipe = generate(exterior, settings)
        record('geometry_generated', counts=recipe['counts'])
        write_json(output / 'parameters.json', settings)
        write_json(output / 'exterior-parameters.json', exterior)
        schedules(output, recipe)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.preferences.filepaths.save_version = 0
        scene = bpy.context.scene
        scene.name = 'Gherkin interior concept'
        scene.unit_settings.system, scene.unit_settings.scale_length = 'METRIC', 1
        scene['accuracy'] = settings['evidence_status']
        scene['spec_id'] = settings['spec_id']
        collections, materials, mapping = {}, {}, []
        filename = output / 'gherkin-interior.blend'
        last_stage = None
        for i, item in enumerate(recipe['objects']):
            if last_stage is not None and last_stage != item['stage']:
                bpy.ops.wm.save_as_mainfile(filepath=str(filename))
                record('stage_checkpoint', stage=last_stage, objects=i)
            last_stage = item['stage']
            category = item['category']
            if category not in collections:
                collections[category] = bpy.data.collections.new(category)
                scene.collection.children.link(collections[category])
                materials[category] = material(category, item['opacity'])
            mesh = bpy.data.meshes.new(item['name'])
            mesh.from_pydata(item['vertices'], [], item['triangles'])
            mesh.update()
            if mesh.validate(verbose=False):
                raise RuntimeError('Blender repaired a generated mesh: ' + item['name'])
            obj = bpy.data.objects.new(item['name'], mesh)
            collections[category].objects.link(obj)
            mesh.materials.append(materials[category])
            obj['gherkin_id'] = item['name']
            obj['stage'], obj['level'] = item['stage'], item['level']
            obj['accuracy'] = 'assumed interior' if category.startswith('INT_') else 'original approximate exterior'
            obj['component_ids'] = json.dumps(item.get('component_ids', []))
            mapping.append({'id': item['name'], 'native_name': obj.name, 'collection': category, 'level': item['level'], 'stage': item['stage']})
        host.presentation(scene)
        for obj in scene.objects:
            if obj.type == 'LIGHT':
                obj.data.energy *= 0.08
        scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.35
        scene.cycles.samples = 24
        bpy.ops.wm.save_as_mainfile(filepath=str(filename))
        write_json(output / 'object-mapping.json', {'objects': mapping, 'components': recipe['components'], 'doors': recipe['doors'], 'rooms': recipe['rooms'], 'networks': recipe['networks']})
        record('saved', objects=len(mapping))
        bpy.ops.wm.open_mainfile(filepath=str(filename))
        scene = bpy.context.scene
        native, readback = host.validate(bpy.context.scene, recipe)
        write_json(output / 'native-validation.json', native)
        with gzip.open(output / 'native-readback.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump(readback, stream, separators=(',', ':'), allow_nan=False)
        record('reopened_native_validation', passed=native['passed'], maximum_error_m=native['maximum_vertex_error_m'])
        report = validate(recipe, settings, readback)
        write_json(output / 'design-validation.json', report)
        record('design_validation', passed=report['passed'])
        if not native['passed'] or not report['passed']:
            raise RuntimeError('Interior verification failed; inspect validation reports')
        if args.glb:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in scene.objects:
                obj.select_set(obj.type == 'MESH')
            bpy.ops.export_scene.gltf(filepath=str(output / 'gherkin-interior.glb'), export_format='GLB', use_selection=True, export_extras=True, export_cameras=False, export_lights=False)
            record('glb_exported')
        if args.render:
            capture(bpy.context.scene, output, recipe, args.capture_level)
            record('captures_saved', level=args.capture_level)
        record('complete', counts=recipe['counts'])
    except Exception as error:
        record('error', type=type(error).__name__, message=str(error))
        raise


if __name__ == '__main__':
    main()
