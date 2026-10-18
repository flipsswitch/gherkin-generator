import bmesh
import bpy

import blender_gherkin as host


def category(obj):
    return next((c.name for c in obj.users_collection if c.name != 'PRESENTATION'), '')


def configure(scene):
    palette = {
        'INT_SLABS': (0.68, 0.70, 0.69), 'INT_RAISED': (0.32, 0.33, 0.31),
        'INT_CORE': (0.81, 0.80, 0.76), 'INT_STAIRS': (0.77, 0.79, 0.78),
        'INT_FRAME': (0.46, 0.39, 0.31), 'INT_PARTITIONS': (0.84, 0.83, 0.78),
        'INT_SEATING': (0.035, 0.065, 0.08), 'INT_DESKS': (0.51, 0.35, 0.20),
        'INT_WORKTOPS': (0.54, 0.40, 0.25),
        'INT_DOORS': (0.48, 0.34, 0.21), 'GHR_GLAZING_CLEAR': (0.35, 0.43, 0.48),
        'GHR_GLAZING_DARK': (0.019, 0.042, 0.065),
    }
    for mat in bpy.data.materials:
        shader = mat.node_tree.nodes.get('Principled BSDF') if mat.use_nodes else None
        if shader is None:
            continue
        if mat.name in palette:
            color = palette[mat.name]
            shader.inputs['Base Color'].default_value = (*color, 1)
            mat.diffuse_color = (*color, mat.diffuse_color[3])
        if mat.name.startswith('GHR_GLAZING'):
            shader.inputs['Metallic'].default_value = 0.55
            shader.inputs['Roughness'].default_value = 0.21
        elif mat.name in ('INT_ENTRANCE', 'INT_LOBBY', 'INT_CROWN', 'INT_MULLIONS', 'INT_HARDWARE'):
            shader.inputs['Metallic'].default_value = 0.65
            shader.inputs['Roughness'].default_value = 0.31
        elif mat.name == 'INT_INTERIOR_GLASS':
            shader.inputs['Metallic'].default_value = 0.15
            shader.inputs['Roughness'].default_value = 0.12
        elif mat.name == 'INT_SCREENS':
            shader.inputs['Emission Color'].default_value = (0.04, 0.11, 0.17, 1)
            shader.inputs['Emission Strength'].default_value = 0.2
        elif mat.name == 'INT_LIGHTS':
            shader.inputs['Emission Color'].default_value = (1, 0.91, 0.73, 1)
            shader.inputs['Emission Strength'].default_value = 2
    nodes = scene.world.node_tree.nodes
    links = scene.world.node_tree.links
    nodes.clear()
    ambient = nodes.new('ShaderNodeBackground')
    ambient.inputs['Color'].default_value = (0.74, 0.81, 0.90, 1)
    ambient.inputs['Strength'].default_value = 0.3
    background = nodes.new('ShaderNodeBackground')
    background.inputs['Color'].default_value = (1, 1, 1, 1)
    background.inputs['Strength'].default_value = 6
    ray = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    output = nodes.new('ShaderNodeOutputWorld')
    links.new(ray.outputs['Is Camera Ray'], mix.inputs[0])
    links.new(ambient.outputs[0], mix.inputs[1])
    links.new(background.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], output.inputs[0])
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.data.energy = {'Key': 280000, 'Fill': 110000, 'Rim': 200000}.get(obj.name, obj.data.energy)
    scene.cycles.samples = 40
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transparent_max_bounces = 48
    preferences = bpy.context.preferences.addons['cycles'].preferences
    for backend in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
            devices = [d for d in preferences.devices if d.type != 'CPU']
            if devices:
                for device in preferences.devices:
                    device.use = device.type != 'CPU'
                scene.cycles.device = 'GPU'
                break
        except (TypeError, ValueError, RuntimeError):
            continue
    scene.render.resolution_x, scene.render.resolution_y = 1200, 1700
    scene.camera.data.ortho_scale = 205
    scene.camera.location = (80, -240, 150)
    host.aim(scene.camera, (0, 0, 87))


def cut_mesh(obj, plane_y, start_z):
    original = obj.data
    temporary = original.copy()
    obj.data = temporary
    mesh = bmesh.new()
    try:
        mesh.from_mesh(temporary)
        for position, normal in (((0, 0, start_z), (0, 0, 1)), ((0, plane_y, 0), (0, 1, 0))):
            bmesh.ops.bisect_plane(mesh, geom=list(mesh.verts) + list(mesh.edges) + list(mesh.faces),
                                  dist=1e-6, plane_co=position, plane_no=normal)
        remove = [face for face in mesh.faces if face.calc_center_median().z > start_z - 1e-5 and face.calc_center_median().y < plane_y + 1e-5]
        bmesh.ops.delete(mesh, geom=remove, context='FACES')
        mesh.to_mesh(temporary)
    except Exception:
        obj.data = original
        bpy.data.meshes.remove(temporary)
        raise
    finally:
        mesh.free()
    return obj, original, temporary


def capture(scene, output, recipe, level):
    meshes = [obj for obj in scene.objects if obj.type == 'MESH']
    hidden = {obj.name: obj.hide_render for obj in meshes}
    camera = scene.camera
    camera_state = (camera.location.copy(), camera.rotation_euler.copy(), camera.data.type, camera.data.ortho_scale, camera.data.lens)
    resolution = (scene.render.resolution_x, scene.render.resolution_y)
    changed = []
    try:
        for obj in meshes:
            obj.hide_render = obj.get('stage', 0) >= 4
        host.render_png(scene, output / 'architectural-isometric.png')
        camera.location = (0, -300, 90)
        host.aim(camera, (0, 0, 90))
        host.render_png(scene, output / 'architectural-elevation.png')
        scene.render.resolution_x, scene.render.resolution_y = 1500, 1000
        camera.data.ortho_scale = 38
        camera.location = (17, -56, 12)
        host.aim(camera, (0, -20, 6.7))
        host.render_png(scene, output / 'entrance.png')
        camera.data.type = 'PERSP'
        camera.data.lens = 16
        camera.location = (-6.5, -3.8, 168.8)
        host.aim(camera, (0, 0, 172.8))
        host.render_png(scene, output / 'crown-interior.png')
        floor = recipe['floors'][level - 1]
        z = floor['ffl']
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = floor['radius'] * 2.2
        for obj in meshes:
            obj.hide_render = obj.get('level') != level or obj.get('stage', 0) >= 4
        scene.render.resolution_x, scene.render.resolution_y = 1400, 1400
        camera.location = (46, -64, z + 61)
        host.aim(camera, (0, 0, z + 0.7))
        host.render_png(scene, output / 'furnished-floor.png')
        camera.location = (0, -0.001, z + 75)
        host.aim(camera, (0, 0, z))
        host.render_png(scene, output / 'floor-plan.png')
        for obj in meshes:
            obj.hide_render = obj.get('level') != level or category(obj) == 'INT_RAISED' or obj.get('stage') in (3, 4)
        host.render_png(scene, output / 'electrical-floor.png')
        for obj in meshes:
            obj.hide_render = obj.get('stage', 0) >= 4
        presentation = recipe['architecture']['presentation']
        for obj in meshes:
            if obj.hide_render or category(obj) == 'INT_CROWN':
                continue
            if max(v.co.z for v in obj.data.vertices) < presentation['cutaway_start_z_m']:
                continue
            if min(v.co.y for v in obj.data.vertices) >= presentation['cutaway_front_plane_y_m']:
                continue
            changed.append(cut_mesh(obj, presentation['cutaway_front_plane_y_m'], presentation['cutaway_start_z_m']))
        scene.render.resolution_x, scene.render.resolution_y = 1400, 2000
        camera.data.ortho_scale = 205
        camera.location = (85, -230, 198)
        host.aim(camera, (0, 0, 88))
        host.render_png(scene, output / 'architectural-cutaway.png')
    finally:
        for obj, original, temporary in changed:
            obj.data = original
            bpy.data.meshes.remove(temporary)
        for obj in meshes:
            obj.hide_render = hidden[obj.name]
        camera.location, camera.rotation_euler, camera.data.type, camera.data.ortho_scale, camera.data.lens = camera_state
        scene.render.resolution_x, scene.render.resolution_y = resolution
