import json
import math
import os
import sys
import time
from pathlib import Path

from MSPyBentley import BentleyStatus
from MSPyBentleyGeom import CurveVector, DPoint3d, DPoint3dArray, DRange3d, DVec3d, DgnConeDetail, DgnExtrusionDetail, IFacetOptions, IPolyfaceConstruction, Int32Array, ISolidPrimitive, PolyfaceHeader, RotMatrix
import MSPyECObjects
from MSPyDgnPlatform import DgnSaveReason, DraftingElementSchema, EditElementHandle, ElementHandle, ElementPropertiesGetter, ElementPropertiesSetter, LEVEL_NULL_CODE, LEVEL_NULL_ID, MeshHeaderHandler
import MSPyDgnView
from MSPyMstnPlatform import ISessionMgr, MstnView, PyCadInputQueue

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from gherkin import generate, geometry_digest, load_parameters, write_json
from privacy import create_output_directory, error_summary


def success(status, action):
    if int(status) != int(BentleyStatus.eSUCCESS):
        raise RuntimeError(action + ' failed with status ' + str(status))


def xyz(point, units):
    return [point.x / units, point.y / units, point.z / units]


def primitive_for(item, units):
    z, thickness = item['elevation'] * units, item['thickness'] * units
    if item['kind'] == 'cylinder':
        radius = item['radius'] * units
        return ISolidPrimitive.CreateDgnCone(DgnConeDetail(DPoint3d(0, 0, z), DPoint3d(0, 0, z + thickness), radius, radius, True))
    points = DPoint3dArray()
    points.extend(DPoint3d(x * units, y * units, z) for x, y in item['profile'] + item['profile'][:1])
    profile = CurveVector.CreateLinear(points, CurveVector.eBOUNDARY_TYPE_Outer)
    return ISolidPrimitive.CreateDgnExtrusion(DgnExtrusionDetail(profile, DVec3d(0, 0, thickness), True))


def floor_volume(item):
    if item['kind'] == 'cylinder':
        return math.pi * item['radius'] ** 2 * item['thickness']
    profile = item['profile']
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(profile, profile[1:] + profile[:1])) / 2
    return area * item['thickness']


def read_mesh(handle, units):
    query = handle.GetIMeshQuery()
    if query is None:
        raise RuntimeError('Element does not expose native mesh geometry')
    status, polyface = query.GetMeshData(handle)
    success(status, 'Read mesh')
    return read_polyface(polyface, units)


def read_polyface(polyface, units):
    vertices = [xyz(p, units) for p in polyface.Point()]
    triangles, face = [], []
    for index in polyface.PointIndex():
        if index == 0:
            if len(face) != 3:
                raise RuntimeError('Expected triangular native mesh faces')
            triangles.append(face)
            face = []
        else:
            face.append(abs(index) - 1)
    if face:
        raise RuntimeError('Unterminated mesh face')
    return vertices, triangles


def verify(model, recipe, mapping, units):
    checks, readback = [], []
    native_ids = {ElementHandle(ref, model).GetElementId() for ref in model.GetDgnModel().GetGraphicElements()}
    expected_ids = {int(record['element_id']) for record in mapping['objects']}
    checks.append({'check': 'native_element_ids', 'pass': native_ids == expected_ids, 'actual': len(native_ids)})
    for item, record in zip(recipe['objects'], mapping['objects']):
        handle = ElementHandle(int(record['element_id']), model)
        if not handle.IsValid():
            checks.append({'check': item['name'], 'pass': False, 'reason': 'element missing'})
            continue
        properties = ElementPropertiesGetter(handle)
        level = model.GetDgnFile().GetLevelCache().GetLevel(properties.GetLevel())
        opacity = 1 - properties.GetTransparency()
        valid = str(level.GetName()) == item['category'] and abs(opacity - item['opacity']) < 1e-5
        data = {'id': item['name'], 'element_id': str(handle.GetElementId()), 'level': str(level.GetName()), 'opacity': opacity}
        if item['kind'] == 'mesh':
            vertices, triangles = read_mesh(handle, units)
            error = max((math.dist(a, b) for a, b in zip(vertices, item['vertices'])), default=math.inf)
            valid = valid and len(vertices) == len(item['vertices']) and triangles == item['triangles'] and error < 1e-6
            data.update(vertices_m=vertices, triangles=triangles, geometry_digest=geometry_digest(vertices, triangles), maximum_vertex_error_m=error)
        else:
            query = handle.GetISolidPrimitiveQuery()
            if query is None:
                raise RuntimeError('Floor does not expose native solid primitive geometry')
            status, primitive = query.GetSolidPrimitive(handle)
            success(status, 'Read floor primitive')
            expected = primitive_for(item, units)
            if item['kind'] == 'cylinder':
                same = primitive.IsSameStructureAndGeometry(expected, units * 1e-6)
                moments_ok, native_volume = primitive.ComputePrincipalMoments(DVec3d(), RotMatrix(), DVec3d())
            else:
                builder = IPolyfaceConstruction(IFacetOptions.CreateForSurfaces(units * 1e-7, 0.05, 0, True))
                if not builder.AddSolidPrimitive(primitive):
                    raise RuntimeError('Native floor faceting failed')
                polyface = builder.GetClientMesh()
                vertices, triangles = read_polyface(polyface, units)
                expected_points = {(round(x, 6), round(y, 6), round(item['elevation'] + dz, 6))
                                   for x, y in item['profile'] for dz in (0, item['thickness'])}
                actual_points = {tuple(round(v, 6) for v in point) for point in vertices}
                same = expected_points == actual_points
                moments_ok, native_volume = polyface.ComputePrincipalMoments(DPoint3d(), RotMatrix(), DVec3d(), True)
                data.update(vertices_m=vertices, triangles=triangles, profile_points_match=same)
            volume = abs(native_volume) / units ** 3
            bounds = DRange3d()
            range_ok = primitive.GetRange(bounds)
            closed = primitive.IsClosedVolume()
            valid = (valid and same and moments_ok and range_ok and closed
                     and abs(volume - floor_volume(item)) <= max(1e-6, floor_volume(item) * 1e-8)
                     and abs(bounds.low.z / units - item['elevation']) < 1e-6
                     and abs(bounds.high.z / units - item['elevation'] - item['thickness']) < 1e-6)
            data.update(volume_m3=volume, closed=closed, native_geometry_matches_recipe=same,
                        range_m=[xyz(bounds.low, units), xyz(bounds.high, units)], kind=str(primitive.GetSolidPrimitiveType()))
        readback.append(data)
        checks.append({'check': item['name'], 'pass': bool(valid)})
    return {'passed': all(c['pass'] for c in checks), 'checks': checks, 'uor_per_meter': units,
            'source': 'Persistent native element handles, mesh topology and analytic solid queries'}, readback


def report_folder(filename):
    return filename.parent / (filename.stem + '-gherkin-report')


def verify_saved():
    model = ISessionMgr.GetActiveDgnModelRef()
    filename = Path(str(ISessionMgr.GetActiveDgnFile().GetFileName()))
    output = report_folder(filename)
    parameters = load_parameters(output / 'parameters.json')
    mapping = json.loads((output / 'object-mapping.json').read_text(encoding='utf-8'))
    recipe = generate(parameters)
    if len(mapping['objects']) != len(recipe['objects']) or [o['id'] for o in mapping['objects']] != [o['name'] for o in recipe['objects']]:
        raise RuntimeError('Object mapping does not match the recipe')
    report, readback = verify(model, recipe, mapping, model.GetModelInfo().GetUorPerMeter())
    write_json(output / 'reopened-validation.json', report)
    write_json(output / 'reopened-readback.json', readback)
    if not report['passed']:
        raise RuntimeError('Saved model verification failed')
    print('Gherkin: saved model verification passed.')


def build():
    started = time.perf_counter()
    parameters = load_parameters(os.environ.get('GHERKIN_PARAMETERS') or ROOT / 'parameters.json')
    recipe = generate(parameters)
    model = ISessionMgr.GetActiveDgnModelRef()
    file = ISessionMgr.GetActiveDgnFile()
    if model is None or file is None or not model.Is3d() or file.IsReadOnly():
        raise RuntimeError('Open a new writable 3D DGN before running this script')
    if any(True for _ in model.GetDgnModel().GetGraphicElements()):
        raise RuntimeError('Active model must be empty; existing geometry is never removed')
    units = model.GetModelInfo().GetUorPerMeter()
    if not math.isfinite(units) or units <= 0:
        raise RuntimeError('Invalid native model unit scale')
    output = report_folder(Path(str(file.GetFileName())))
    create_output_directory(output)
    log = []
    mapping = {'counts': recipe['counts'], 'objects': [], 'nodes': recipe['nodes'], 'members': recipe['members'], 'floors': recipe['floors']}

    def record(event, **values):
        log.append({'elapsed_seconds': round(time.perf_counter() - started, 6), 'event': event, **values})
        write_json(output / 'run-log.json', log)

    def checkpoint():
        success(file.ProcessChanges(DgnSaveReason.eUserInitiated), 'Save DGN')
        write_json(output / 'object-mapping.json', mapping)
        record('saved_checkpoint', objects=len(mapping['objects']))

    try:
        record('started', python_version=sys.version.split()[0], uor_per_meter=units)
        write_json(output / 'parameters.json', parameters)
        cache, levels = file.GetLevelCache(), {}
        for category in sorted({o['category'] for o in recipe['objects']}):
            level = cache.GetLevelByName(category)
            if not level.IsValid():
                level = cache.CreateLevel(category, LEVEL_NULL_CODE, LEVEL_NULL_ID)
            if not level.IsValid():
                raise RuntimeError('Could not create level ' + category)
            levels[category] = level.GetLevelId()
        success(cache.Write(), 'Write levels')
        for index, item in enumerate(recipe['objects']):
            handle = EditElementHandle()
            if item['kind'] == 'mesh':
                points, indices = DPoint3dArray(), Int32Array()
                points.extend(DPoint3d(*(coordinate * units for coordinate in vertex)) for vertex in item['vertices'])
                indices.extend(value for a, b, c in item['triangles'] for value in (a + 1, b + 1, c + 1, 0))
                polyface = PolyfaceHeader.CreateIndexedMesh(0, points, indices)
                success(MeshHeaderHandler.CreateMeshElement(handle, None, polyface, True, model), 'Create mesh')
            else:
                success(DraftingElementSchema.ToElement(handle, primitive_for(item, units), None, model), 'Create native floor')
            setter = ElementPropertiesSetter()
            setter.SetLevel(levels[item['category']])
            setter.SetColor(item['color'])
            setter.SetWeight(0)
            setter.SetLinestyle(0, None)
            setter.SetTransparency(1 - item['opacity'])
            setter.Apply(handle)
            success(handle.AddToModel(), 'Add native element')
            mapping['objects'].append({'id': item['name'], 'element_id': str(handle.GetElementId()), 'level': item['category'],
                                       'logical_vertex_ids': item.get('logical_vertex_ids'), 'logical_face_ids': item.get('logical_face_ids')})
            if (index + 1) % 16 == 0 or index + 1 in (40, 85, len(recipe['objects'])):
                checkpoint()
        report, readback = verify(model, recipe, mapping, units)
        write_json(output / 'validation.json', report)
        write_json(output / 'native-readback.json', readback)
        record('validated', passed=report['passed'])
        if not report['passed']:
            raise RuntimeError('Native read-back failed; inspect the validation report')
        fitted_views = []
        for view in range(8):
            if int(MstnView.fit(view, None)) == 0:
                MstnView.updateSingle(view)
                fitted_views.append(view + 1)
        record('views_fitted', views=fitted_views)
        checkpoint()
        PyCadInputQueue.SendKeyin('filedesign')
        record('complete', counts=recipe['counts'])
        print('Gherkin: created, saved and verified ' + str(len(mapping['objects'])) + ' native elements.')
        print('Reports saved beside the active DGN in its Gherkin report folder.')
    except Exception as error:
        write_json(output / 'object-mapping.json', mapping)
        record('error', **error_summary(error))
        raise


if __name__ == '__main__':
    build()
