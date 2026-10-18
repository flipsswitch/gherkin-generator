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
from interior.generator import COLORS, default_exterior, default_settings, generate, load_settings, schedules
from interior.validation import validate
from privacy import create_output_directory, error_summary


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
    shader.inputs['Alpha'].default_value = opacity
    mat.diffuse_color = (*color, opacity)
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
            obj.hide_render = obj.get('level') != level or obj.get('stage', 0) >= 4
        camera.data.ortho_scale = floor['radius'] * 2.3
        camera.location = (0, -0.001, z + 80)
        host.aim(camera, (0, 0, z))
        host.render_png(scene, output / 'floor-plan.png')
        camera.location = (48, -64, z + 58)
        host.aim(camera, (0, 0, z + 0.8))
        host.render_png(scene, output / 'furnished-floor.png')
        for obj in meshes:
            obj.hide_render = obj.get('level') != level or obj.get('stage') == 3
        camera.location = (0, -0.001, z + 80)
        host.aim(camera, (0, 0, z))
        host.render_png(scene, output / 'services-plan.png')
        if recipe.get('variant') == 'researched':
            for label, categories in [('electrical-power-plan', {'INT_POWER', 'INT_BOARDS'}),
                                      ('electrical-lighting-plan', {'INT_LIGHTS', 'INT_CONTROLS', 'INT_BOARDS'})]:
                for obj in meshes:
                    category = next((c.name for c in obj.users_collection), '')
                    obj.hide_render = obj.get('level') != level or category == 'INT_RAISED' or obj.get('stage') in (3, 4) or (obj.get('stage') == 5 and category not in categories)
                host.render_png(scene, output / (label + '.png'))
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
            host.render_png(scene, output / 'interior-cutaway.png')
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
    parser.add_argument('--variant', choices=['original', 'researched', 'architectural'], default='original')
    parser.add_argument('--parameters', type=Path)
    parser.add_argument('--exterior-parameters', type=Path)
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
    settings = load_settings(args.parameters or default_settings(args.variant))
    exterior = load_parameters(args.exterior_parameters or default_exterior(settings))
    if args.verify:
        recipe = generate(exterior, settings)
        bpy.ops.wm.open_mainfile(filepath=str(args.verify.resolve()))
        native, readback = host.validate(bpy.context.scene, recipe)
        design = validate(recipe, settings, readback)
        write_json(args.verify.parent / 'independent-native-validation.json', native)
        write_json(args.verify.parent / 'independent-design-validation.json', design)
        print(json.dumps({'native_passed': native['passed'], 'design_passed': design['passed'], 'checks': len(design['checks'])}))
        if not native['passed'] or not design['passed']:
            raise RuntimeError('Reopened interior verification failed')
        return
    output = args.output_dir.resolve()
    create_output_directory(output)
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
            obj['accuracy'] = settings['evidence_status'] if category.startswith('INT_') else exterior['description']
            obj['component_ids'] = json.dumps(item.get('component_ids', []))
            mapping.append({'id': item['name'], 'native_name': obj.name, 'collection': category, 'level': item['level'], 'stage': item['stage']})
        host.presentation(scene)
        for obj in scene.objects:
            if obj.type == 'LIGHT':
                obj.data.energy *= 0.08
        scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.35
        scene.cycles.samples = 24
        if recipe.get('detail_preset') == 'architectural':
            from interior.presentation_architectural import configure
            configure(scene)
        bpy.ops.wm.save_as_mainfile(filepath=str(filename))
        write_json(output / 'object-mapping.json', {'objects': mapping, **{key: recipe[key] for key in ('components', 'doors', 'rooms', 'networks', 'electrical_circuits', 'electrical_networks', 'lift_schedule') if key in recipe}})
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
            if recipe.get('detail_preset') == 'architectural':
                from interior.presentation_architectural import capture as architectural_capture
                architectural_capture(bpy.context.scene, output, recipe, args.capture_level)
            else:
                capture(bpy.context.scene, output, recipe, args.capture_level)
            record('captures_saved', level=args.capture_level)
        record('complete', counts=recipe['counts'])
    except Exception as error:
        record('error', **error_summary(error))
        raise


if __name__ == '__main__':
    main()
