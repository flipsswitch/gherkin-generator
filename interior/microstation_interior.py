import gzip
import json
import math
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import microstation_gherkin as host
from MSPyMstnPlatform import MstnView, PyCadInputQueue
from gherkin import load_parameters, write_json
from interior.generator import generate, load_settings, schedules
from interior.validation import validate


def context():
    model, file = host.ISessionMgr.GetActiveDgnModelRef(), host.ISessionMgr.GetActiveDgnFile()
    if model is None or file is None or not model.Is3d() or file.IsReadOnly():
        raise RuntimeError('Open a writable 3D DGN')
    filename = Path(str(file.GetFileName()))
    units = model.GetModelInfo().GetUorPerMeter()
    if not math.isfinite(units) or units <= 0:
        raise RuntimeError('Invalid model units')
    return model, file, units, filename.parent / (filename.stem + '-gherkin-interior-report')


def verify_saved():
    model, file, units, output = context()
    settings, exterior = load_settings(output / 'parameters.json'), load_parameters(output / 'exterior-parameters.json')
    recipe = generate(exterior, settings)
    mapping = json.loads((output / 'object-mapping.json').read_text(encoding='utf-8'))
    if [o['id'] for o in mapping['objects']] != [o['name'] for o in recipe['objects']]:
        raise RuntimeError('Mapping does not match the interior recipe')
    native, readback = host.verify(model, recipe, mapping, units)
    report = validate(recipe, settings, readback)
    write_json(output / 'reopened-native-validation.json', native)
    write_json(output / 'reopened-design-validation.json', report)
    with gzip.open(output / 'reopened-readback.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(readback, stream, separators=(',', ':'), allow_nan=False)
    if not native['passed'] or not report['passed']:
        raise RuntimeError('Reopened interior verification failed')
    print('Gherkin interior: reopened native geometry and design checks passed.')


def build():
    started = time.perf_counter()
    model, file, units, output = context()
    if any(True for _ in model.GetDgnModel().GetGraphicElements()):
        raise RuntimeError('Active model must be empty; existing geometry is never removed')
    output.mkdir(exist_ok=False)
    settings = load_settings(os.environ.get('GHERKIN_INTERIOR_PARAMETERS') or ROOT / 'interior/parameters.json')
    exterior = load_parameters(os.environ.get('GHERKIN_PARAMETERS') or ROOT / 'parameters.json')
    log, mapping = [], {'objects': [], 'components': [], 'rooms': [], 'doors': [], 'networks': []}
    def record(event, **values):
        log.append({'elapsed_seconds': round(time.perf_counter() - started, 6), 'event': event, **values})
        write_json(output / 'run-log.json', log)
    def checkpoint(stage):
        host.success(file.ProcessChanges(host.DgnSaveReason.eUserInitiated), 'Save interior DGN')
        write_json(output / 'object-mapping.json', mapping)
        record('saved_checkpoint', stage=stage, objects=len(mapping['objects']))
    try:
        record('started', python_version=sys.version.split()[0], uor_per_meter=units)
        recipe = generate(exterior, settings)
        record('geometry_generated', counts=recipe['counts'])
        for key in ('components', 'rooms', 'doors', 'networks'):
            mapping[key] = recipe[key]
        write_json(output / 'parameters.json', settings)
        write_json(output / 'exterior-parameters.json', exterior)
        schedules(output, recipe)
        cache, levels = file.GetLevelCache(), {}
        for category in sorted({o['category'] for o in recipe['objects']}):
            level = cache.GetLevelByName(category)
            if not level.IsValid():
                level = cache.CreateLevel(category, host.LEVEL_NULL_CODE, host.LEVEL_NULL_ID)
            if not level.IsValid():
                raise RuntimeError('Cannot create level: ' + category)
            levels[category] = level.GetLevelId()
        host.success(cache.Write(), 'Write levels')
        for i, item in enumerate(recipe['objects']):
            points, indices = host.DPoint3dArray(), host.Int32Array()
            points.extend(host.DPoint3d(*(v * units for v in vertex)) for vertex in item['vertices'])
            indices.extend(value for a, b, c in item['triangles'] for value in (a + 1, b + 1, c + 1, 0))
            mesh = host.PolyfaceHeader.CreateIndexedMesh(0, points, indices)
            handle = host.EditElementHandle()
            host.success(host.MeshHeaderHandler.CreateMeshElement(handle, None, mesh, True, model), 'Create interior mesh')
            setter = host.ElementPropertiesSetter()
            setter.SetLevel(levels[item['category']])
            setter.SetColor(item['color'])
            setter.SetWeight(0)
            setter.SetLinestyle(0, None)
            setter.SetTransparency(1 - item['opacity'])
            setter.Apply(handle)
            host.success(handle.AddToModel(), 'Add interior mesh')
            mapping['objects'].append({'id': item['name'], 'element_id': str(handle.GetElementId()), 'level': item['category'], 'floor': item['level'], 'stage': item['stage']})
            if (i + 1) % settings['mesh_limits']['native_objects_per_checkpoint'] == 0 or i + 1 == len(recipe['objects']) or recipe['objects'][i + 1]['stage'] != item['stage']:
                checkpoint(item['stage'])
        native, readback = host.verify(model, recipe, mapping, units)
        write_json(output / 'native-validation.json', native)
        with gzip.open(output / 'native-readback.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump(readback, stream, separators=(',', ':'), allow_nan=False)
        record('native_validation', passed=native['passed'])
        report = validate(recipe, settings, readback)
        write_json(output / 'design-validation.json', report)
        record('design_validation', passed=report['passed'])
        if not native['passed'] or not report['passed']:
            raise RuntimeError('Interior verification failed; inspect validation reports')
        for view in range(8):
            if int(MstnView.fit(view, None)) == 0:
                MstnView.updateSingle(view)
        checkpoint(4)
        PyCadInputQueue.SendKeyin('filedesign')
        record('complete', counts=recipe['counts'])
        print('Gherkin interior: created, saved and verified ' + str(len(mapping['objects'])) + ' native meshes.')
    except Exception as error:
        write_json(output / 'object-mapping.json', mapping)
        record('error', type=type(error).__name__, message=str(error))
        raise


if __name__ == '__main__':
    build()
