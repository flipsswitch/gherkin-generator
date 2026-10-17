import math
from collections import Counter

from interior.generator import Builder
from interior.geometry import box, clear_point, combine, corners, in_rect, local_xy, overlaps, section_member, tube


def validate_researched_settings(p):
    if p['lifts']['bank_counts'] != [6, 5, 5] or len(p['stairs']['poses_m_radians']) != 2:
        raise ValueError('The researched topology requires three banks totalling 16 office lifts and two stairs')
    if not 0.12 <= p['raised_floor_m'] <= 0.3 or not 0.01 <= p['raised_panel_m'] < p['raised_floor_m']:
        raise ValueError('Invalid raised-floor construction')
    for pose in p['stairs']['poses_m_radians']:
        if len(pose) != 3 or math.hypot(*pose[:2]) > 12:
            raise ValueError('Stair pose is outside the supported core')
    e = p['electrical']
    if not 2 <= e['luminaire_grid_m'] <= 6 or e['luminaire_grid_m'] / p['services']['routing_grid_m'] % 1:
        raise ValueError('Luminaire grid must be bounded and aligned with routing grid')
    for key in ('outlets_per_circuit', 'lights_per_circuit', 'addresses_per_control_link'):
        if not isinstance(e[key], int) or not 1 <= e[key] <= 64:
            raise ValueError('Invalid circuit or control group size')
    if not 0 < e['route_radius_m'] < 0.04 or not 0 < e['control_radius_m'] < e['route_radius_m']:
        raise ValueError('Invalid electrical route radii')
    if not 0.03 <= e['power_height_above_slab_m'] <= p['raised_floor_m'] - p['raised_panel_m'] - 0.03:
        raise ValueError('Power containment must fit inside the raised-floor void')
    if not p['clear_ceiling_m'] < e['control_route_height_m'] < e['lighting_route_height_m'] < p['services']['pipe_height_m']:
        raise ValueError('Electrical and sprinkler service layers must remain separated')
    for rect in p['service_shafts']['rectangles_m_radians']:
        if len(rect) != 5 or min(rect[2:4]) <= 0:
            raise ValueError('Invalid service shaft')
    if not 6 <= p['structure']['core_column_count'] <= 36 or p['structure']['radial_beam_step_degrees'] != 10:
        raise ValueError('Unsupported structural sampling')


class ResearchBuilder(Builder):
    def __init__(self, exterior, settings):
        super().__init__(exterior, settings)
        self.lifts, self.circuits, self.electrical_networks = [], [], []
        p = settings['lifts']
        for bank, angle in enumerate(p['bank_angles_degrees']):
            theta = math.radians(angle)
            count = p['bank_counts'][bank]
            for side in (-1, 1):
                for index, radial in enumerate(p['bank_radii_m']):
                    if count == 5 and side == -1 and index == 2:
                        continue
                    xy = local_xy([0, 0, 0, 0, theta], radial, side * p['bank_lateral_offset_m'])
                    last = p['bank_last_levels'][bank]
                    served = sorted({1, *range(p['bank_first_served_levels'][bank], last + 1)})
                    self.lifts.append({'id': f'LIFT-{len(self.lifts) + 1:02d}', 'bank': bank + 1,
                                       'rect': [*xy, *p['shaft_size_m'], theta + (math.pi if side < 0 else 0)],
                                       'first_level': 1, 'last_level': last, 'served_levels': served,
                                       'evidence': 'R02 count; R03 sector topology; dimensions and stop allocation inferred'})
        for j, (x, y, angle) in enumerate(p['upper_shuttles']):
            first, last = p['shuttle_first_level'], p['shuttle_last_level']
            self.lifts.append({'id': f'SHUTTLE-{j + 1:02d}', 'bank': 'upper-concept', 'rect': [x, y, *p['shaft_size_m'], angle],
                               'first_level': first, 'last_level': last, 'served_levels': list(range(first, last + 1)),
                               'evidence': 'assumed upper-level access proxy; not a resolution of the 16/18 lift-source conflict'})

    def add(self, identifier, category, stage, level, mesh, role, **metadata):
        metadata.setdefault('evidence', 'inferred geometry; see research/EVIDENCE.md')
        metadata.setdefault('source_ids', ['R03'] if category in ('INT_CORE', 'INT_STAIRS', 'INT_LIFTS') else [])
        return super().add(identifier, category, stage, level, mesh, role, **metadata)

    def shell_and_core(self):
        super().shell_and_core()
        p = self.settings['structure']
        core_radius = p['core_radius_m']
        for floor in self.floors:
            level, z = floor['level'], floor['slab_z']
            floor['published_level_match'] = 'approximate model index; no surveyed level datum'
            floor['core_clear_radius_m'] = 8.0 if level > 22 else self.settings['fitout']['core_clear_radius_m']
            if level > 1:
                for j in range(36):
                    angle = math.radians(j * p['radial_beam_step_degrees'] + floor['phase'])
                    a = [core_radius * math.cos(angle), core_radius * math.sin(angle)]
                    b = [(floor['radius'] - 0.12) * math.cos(angle), (floor['radius'] - 0.12) * math.sin(angle)]
                    if floor['radius'] <= core_radius + 0.4 or not all(clear_point([a[k] + t * (b[k] - a[k]) for k in (0, 1)], floor['profile'], 0.10) for t in (0, 0.25, 0.5, 0.75, 1)):
                        continue
                    self.add(f'INT-L{level:02d}-RADIAL-BEAM-{j:02d}', 'INT_FRAME', 1, level,
                             section_member([*a, z - p['beam_depth_m'] / 2], [*b, z - p['beam_depth_m'] / 2],
                                            p['beam_width_m'], p['beam_depth_m'], p['beam_web_m'], p['beam_flange_m']),
                             'radial_steel_beam_proxy', source_ids=['R01'], evidence='10 degree spacing documented; section and end conditions assumed')
            for j in range(p['core_column_count']):
                angle = math.tau * j / p['core_column_count'] + math.radians(10)
                xy = [core_radius * math.cos(angle), core_radius * math.sin(angle)]
                rect = [*xy, p['core_column_size_m'], p['core_column_size_m'], angle]
                if not self.fits(rect, floor, floor['next_z'] - floor['ffl'], 0.05) or any(overlaps(rect, other, 0.12) for other in floor['obstacles']):
                    self.omissions.append({'id': f'INT-L{level:02d}-COLUMN-{j:02d}', 'reason': 'Inferred column rejected by envelope or protected core zone'})
                    continue
                self.add(f'INT-L{level:02d}-COLUMN-{j:02d}', 'INT_FRAME', 1, level,
                         box(rect, floor['ffl'], floor['next_z'] - floor['ffl']), 'core_steel_column_proxy', source_ids=['R01'])
                floor['obstacles'].append(rect)
        rings = {}
        for node in self.base['nodes']:
            rings.setdefault(node['ring'], []).append(node['xyz'])
        for index, nodes in rings.items():
            for j, (a, b) in enumerate(zip(nodes, nodes[1:] + nodes[:1])):
                self.add(f'INT-HOOP-{index:02d}-{j:02d}', 'INT_FRAME', 1, 0, tube(a, b, p['hoop_radius_m']),
                         'perimeter_hoop_proxy', source_ids=['R01'], evidence='Hoop existence documented; section and setting-out inferred')
        top = self.exterior['diagrid_body_top_m']
        previous = None
        for k, z in enumerate([top] + self.exterior['glazing_crown_ring_elevations_m'] + [self.exterior['height_m'] - 0.05]):
            radial = max(0.1, self.radius(z) - 0.07)
            points = [[radial * math.cos(math.tau * j / 36 + k * math.pi / 36), radial * math.sin(math.tau * j / 36 + k * math.pi / 36), z] for j in range(36)]
            if previous:
                for j in range(36):
                    for side in (0, -1):
                        self.add(f'INT-DOME-{k:02d}-{j:02d}-{side}', 'INT_FRAME', 1, 0,
                                 tube(previous[j], points[(j + side) % 36], 0.065, 6), 'dome_lattice_proxy', source_ids=['R01'])
            previous = points

    def plan_rooms(self):
        p = self.settings['rooms']
        for floor in self.floors:
            level = floor['level']
            if level <= 37:
                self.room(f'INT-L{level:02d}-WC-BLOCK', 'washroom_block', [-9.0,0,4.8,5.0,math.pi / 2], floor)
                self.room(f'INT-L{level:02d}-ELECTRICAL', 'electrical', [-10,5.0,2.8,2.0,0], floor)
                self.room(f'INT-L{level:02d}-IT', 'it', [-10,-5.0,2.8,2.0,math.pi], floor)
            if self.settings['office_levels'][0] <= level <= self.settings['office_levels'][1]:
                for sector in range(6):
                    angle = math.radians(floor['phase'] + 30 + sector * 60)
                    radial = (self.settings['structure']['core_radius_m'] + floor['radius']) / 2
                    if sector % 2 == 0:
                        rect = [radial * math.cos(angle), radial * math.sin(angle), *p['meeting_size_m'], angle + math.pi / 2]
                        self.room(f'INT-L{level:02d}-MEETING-{sector + 1}', 'meeting', rect, floor)
                    else:
                        for j, offset in enumerate((-12,12)):
                            theta = angle + math.radians(offset)
                            radius = floor['radius'] - 2.4
                            rect = [radius * math.cos(theta),radius * math.sin(theta),2.8,3.6,theta + math.pi / 2]
                            self.room(f'INT-L{level:02d}-OFFICE-{sector + 1}-{j + 1}', 'private_office', rect, floor)
            if level in self.settings['plant_levels']:
                rect = [0,-17.5,8,4,0] if level == 2 else [-5.5,7.5,5,3.5,math.pi]
                self.room(f'INT-L{level:02d}-PLANT', 'plant', rect, floor)
        for room in self.rooms:
            room['evidence'] = 'R03 west WC topology; dimensions inferred' if room['use'] == 'washroom_block' else 'assumed fit-out; public layouts are indicative'

    def fitout(self):
        super().fitout()
        for floor in self.floors:
            for room in floor['rooms']:
                if room['use'] == 'private_office':
                    rect = [*room['rect'][:2],*self.settings['fitout']['workstation_clearance_m'],room['rect'][4]]
                    self.desk(room['id'] + '-DESK',rect,floor)
                if room['use'] != 'washroom_block':
                    continue
                rect = room['rect']
                for j, x in enumerate((-1.65,-0.55,0.55,1.65)):
                    cubicle = [*local_xy(rect, x, 1.2), 1.04, 1.7, rect[4]]
                    identifier = room['id'] + f'-CUBICLE-{j + 1}'
                    self.enclosure(identifier, cubicle, floor, 2.25, 0.045, 0.70, 'INT_PARTITIONS', 3, 'wc_cubicle')
                    xy = local_xy(rect, x, 1.55)
                    self.add(identifier + '-WC', 'INT_FIXTURES', 3, floor['level'],
                             box([*xy,0.42,0.65,rect[4]], floor['ffl'], 0.42), 'wc_proxy')
                for j, x in enumerate((-1.65,1.65)):
                    xy = local_xy(rect, x, -1.55)
                    identifier = room['id'] + f'-BASIN-{j + 1}'
                    self.add(identifier, 'INT_FIXTURES', 3, floor['level'], box([*xy,0.55,0.48,rect[4]], floor['ffl'] + 0.76, 0.12), 'washbasin')
                    floor['service_destinations'].append({'id': identifier, 'xy': xy, 'z': floor['ffl'] + 0.8})

    def services(self):
        p = self.settings['services']
        fx, fy = p['fire_root_m']
        wx, wy = p['wet_root_m']
        definitions = [('FIRE','INT_FIRE',[fx,fy],p['fire_radius_m'],0),
                       ('COLD','INT_COLD',[wx,wy - 0.25],p['water_radius_m'],0.12),
                       ('HOT','INT_HOT',[wx,wy + 0.25],p['water_radius_m'],0.24),
                       ('DRAIN','INT_DRAIN',[wx,wy + 0.5],p['drain_radius_m'],0.36)]
        for name, category, xy, radius, offset in definitions:
            cuts = [self.floors[0]['ffl']] + [f['ffl'] + p['pipe_height_m'] + offset for f in self.floors]
            for j, (low, high) in enumerate(zip(cuts, cuts[1:])):
                self.pipe(f'INT-{name}-RISER-{j:02d}', category, j + 1, [*xy,low], [*xy,high], radius, system=name)
        for floor in self.floors:
            level, z = floor['level'], floor['ffl'] + p['pipe_height_m']
            spacing = p['routing_grid_m'] * p['head_grid_multiple']
            count = math.ceil(floor['radius'] / spacing)
            targets = [{'id': f'INT-L{level:02d}-HEAD-{x:+03d}-{y:+03d}', 'xy': [x * spacing,y * spacing + 0.5]}
                       for x in range(-count,count + 1) for y in range(-count,count + 1)
                       if math.hypot(x * spacing,y * spacing + 0.5) > 3 and clear_point([x * spacing,y * spacing + 0.5], floor['profile'], 0.7)]
            segments, ends, _, reachable = self.route_tree(floor, [fx,fy], targets, p['pipe_height_m'])
            for j, (a,b) in enumerate(segments):
                self.pipe(f'INT-L{level:02d}-FIRE-MAIN-{j:03d}', 'INT_FIRE', level, [*a,z], [*b,z], p['branch_radius_m'], system='FIRE')
            for target, node in ends:
                xy = [v * p['routing_grid_m'] for v in node]
                bottom = floor['ffl'] + p['head_height_m']
                self.pipe(target['id'] + '-DROP', 'INT_FIRE', level, [*xy,z], [*xy,bottom], 0.012, system='FIRE')
                self.add(target['id'], 'INT_FIRE', 4, level, tube([*xy,bottom - 0.03],[*xy,bottom],0.055,12), 'sprinkler_head', system='FIRE')
            self.networks.append({'id':f'FIRE-L{level:02d}','level':level,'root_m':[fx,fy,z],
                                  'routed_terminals':len(ends),'requested_terminals':len(targets),'routing_nodes':reachable,
                                  'terminals':[t['id'] for t,_ in ends],'evidence':'assumed; no coverage or hydraulic design'})
            if floor['service_destinations']:
                root = [wx - 1.5,wy]
                segments, ends, _, _ = self.route_tree(floor, root, floor['service_destinations'], p['pipe_height_m'] + 0.12)
                for name, category, xy, radius, offset in definitions[1:3]:
                    height = z + offset
                    self.pipe(f'INT-L{level:02d}-{name}-TAKEOFF-A', category, level, [*xy,height], [root[0],xy[1],height], radius, system=name)
                    self.pipe(f'INT-L{level:02d}-{name}-TAKEOFF-B', category, level, [root[0],xy[1],height], [*root,height], radius, system=name)
                    for j,(a,b) in enumerate(segments):
                        self.pipe(f'INT-L{level:02d}-{name}-BRANCH-{j:03d}', category, level, [*a,height], [*b,height], radius, system=name)
                    for j,(target,node) in enumerate(ends):
                        a = [v * p['routing_grid_m'] for v in node]
                        b = [target['xy'][0] + (-0.06 if name == 'COLD' else 0.06),target['xy'][1]]
                        self.pipe(f'INT-L{level:02d}-{name}-FINAL-{j:02d}', category, level, [*a,height], [*b,height], radius, system=name)
                        self.pipe(f'INT-L{level:02d}-{name}-DROP-{j:02d}', category, level, [*b,height], [*b,target['z']], radius, system=name)
            if 3 <= level <= 35:
                for j in range(p['fan_coil_count_per_floor']):
                    angle = math.radians(floor['phase'] + 30 + j * 60)
                    radius = floor['radius'] - 2.5
                    rect = [radius * math.cos(angle),radius * math.sin(angle),1.2,0.65,angle]
                    if not self.fits(rect,floor,3.15,0.2):
                        continue
                    identifier = f'INT-L{level:02d}-FCU-{j + 1}'
                    self.add(identifier,'INT_HVAC',4,level,box(rect,floor['ffl'] + 2.85,0.25),'four_pipe_fan_coil_proxy',source_ids=['R02'])
                    for k,system in enumerate(('CHWS','CHWR','HHWS','HHWR')):
                        a = local_xy(rect,-0.45 + k * 0.3,0.325)
                        b = local_xy(rect,-0.45 + k * 0.3,0.7)
                        self.add(identifier + '-' + system,'INT_HVAC',4,level,tube([*a,floor['ffl'] + 2.98],[*b,floor['ffl'] + 2.98],0.018),
                                 'unconnected_fan_coil_port',system=system,network_status='stub only; full hydronic network omitted')

    def electrical_route(self, identifier, system, level, a, b, radius=None):
        if math.dist(a,b) < 1e-8:
            return
        p = self.settings['electrical']
        category = 'INT_CONTROLS' if system == 'CONTROL' else 'INT_POWER' if system == 'POWER' else 'INT_LIGHTS'
        radius = radius or (p['control_radius_m'] if system == 'CONTROL' else p['route_radius_m'])
        self.add(identifier,category,5,level,tube(a,b,radius,8),'electrical_route',system=system,
                 start_m=a,end_m=b,radius_m=radius,endpoint_ring_size=8,source_ids=['R04','R05'])

    def route_tree(self, floor, root, targets, height):
        if getattr(self, 'electrical_routing', False):
            z = floor['ffl'] + height
            keepouts = []
            for c in self.pipe_route_obstacles:
                a, b = c['start_m'], c['end_m']
                if min(a[2],b[2]) - 0.06 <= z <= max(a[2],b[2]) + 0.06 and abs(a[0] - b[0]) < 1e-8 and abs(a[1] - b[1]) < 1e-8:
                    keepouts.append([a[0],a[1],0.3,0.3,0])
            floor['routing_keepouts'] = keepouts
        result = super().route_tree(floor,root,targets,height)
        floor.pop('routing_keepouts',None)
        return result

    def electrical(self):
        p = self.settings['electrical']
        self.electrical_routing = True
        self.pipe_route_obstacles = [c for c in self.components if c['role'] == 'service_pipe']
        origins = {'POWER':p['source_a_m'],'LIGHTING':p['source_b_m'],'CONTROL':p['control_root_m']}
        heights = {'POWER':-self.settings['raised_floor_m'] + p['power_height_above_slab_m'],
                   'LIGHTING':p['lighting_route_height_m'],'CONTROL':p['control_route_height_m']}
        start_z = self.floors[0]['slab_z'] + self.exterior['slab_thickness_m'] + 0.025
        for system,root in origins.items():
            cuts = [start_z] + [f['ffl'] + heights[system] for f in self.floors]
            for j,(a,b) in enumerate(zip(cuts,cuts[1:])):
                self.electrical_route(f'INT-{system}-RISER-{j:02d}',system,j + 1,[*root,a],[*root,b],p['control_radius_m'] if system == 'CONTROL' else p['riser_radius_m'])
        for floor in self.floors:
            level = floor['level']
            for system,root in origins.items():
                identifier = f'INT-L{level:02d}-{system}-BOARD'
                self.add(identifier,'INT_BOARDS',5,level,box([root[0],root[1] + 0.25,0.44,0.18,0],floor['ffl'] + 0.4,1.25),
                         'lighting_controller_proxy' if system == 'CONTROL' else 'distribution_board_proxy',system=system,
                         source='A' if system == 'POWER' else 'B' if system == 'LIGHTING' else 'DALI/LON/BMS concept',ratings=None)
                self.electrical_route(identifier + '-CONNECTION',system,level,[*root,floor['ffl'] + heights[system]],[*root,floor['ffl'] + 1.0])
            power = []
            for furniture in floor['furniture']:
                if furniture['type'] != 'workstation':
                    continue
                xy = local_xy(furniture['rect'],0,0.45)
                power.append({'id':furniture['id'] + '-OUTLET','xy':xy,'parent':furniture['id']})
            spacing = p['luminaire_grid_m']
            count = math.ceil(floor['radius'] / spacing)
            lighting = [{'id':f'INT-L{level:02d}-LIGHT-{x:+03d}-{y:+03d}','xy':[x * spacing,y * spacing]}
                        for x in range(-count,count + 1) for y in range(-count,count + 1)
                        if math.hypot(x * spacing,y * spacing) > self.settings['structure']['core_radius_m']
                        and self.fits([x * spacing,y * spacing,1.2,0.18,0],floor,p['luminaire_height_m'],0.25)]
            for j,theta in enumerate((0,120,240)):
                xy = [round(8 * math.cos(math.radians(theta)) * 2) / 2,round(8 * math.sin(math.radians(theta)) * 2) / 2]
                lighting.append({'id':f'INT-L{level:02d}-LOBBY-LIGHT-{j + 1}','xy':xy})
            for room in floor['rooms']:
                lighting.append({'id':room['id'] + '-LIGHT','xy':room['rect'][:2]})
            for system,targets in [('POWER',power),('LIGHTING',lighting)]:
                root, height = origins[system], heights[system]
                segments,ends,_,reachable = self.route_tree(floor,root,targets,height)
                z = floor['ffl'] + height
                for j,(a,b) in enumerate(segments):
                    identifier = f'INT-L{level:02d}-{system}-ROUTE-{j:04d}'
                    self.electrical_route(identifier,system,level,[*a,z],[*b,z])
                    if system == 'POWER':
                        angle = math.atan2(b[1] - a[1],b[0] - a[0])
                        rect = [(a[0] + b[0]) / 2,(a[1] + b[1]) / 2,math.dist(a,b),p['tray_width_m'],angle]
                        self.add(identifier + '-TRAY','INT_POWER',5,level,box(rect,z - p['tray_height_m'],0.004),'underfloor_containment_proxy')
                terminals = []
                count_per = p['outlets_per_circuit'] if system == 'POWER' else p['lights_per_circuit']
                for j,(target,node) in enumerate(ends):
                    xy = target['xy']
                    snapped = [v * self.settings['services']['routing_grid_m'] for v in node]
                    self.electrical_route(target['id'] + '-FINAL',system,level,[*snapped,z],[*xy,z])
                    terminal_z = floor['ffl'] - 0.025 if system == 'POWER' else floor['ffl'] + p['luminaire_height_m']
                    self.electrical_route(target['id'] + '-DROP',system,level,[*xy,z],[*xy,terminal_z])
                    circuit = f'{system}-L{level:02d}-C{j // count_per + 1:03d}'
                    category = 'INT_POWER' if system == 'POWER' else 'INT_LIGHTS'
                    rect = [*xy,0.20,0.16,0] if system == 'POWER' else [*xy,1.2,0.18,0]
                    self.add(target['id'],category,5,level,box(rect,terminal_z - 0.04,0.04),
                             'floor_power_outlet' if system == 'POWER' else 'luminaire_proxy',system=system,circuit=circuit,
                             connection_m=[*xy,terminal_z],parent=target.get('parent'),ratings=None)
                    terminals.append(target['id'])
                for index in range(0,len(terminals),count_per):
                    self.circuits.append({'id':f'{system}-L{level:02d}-C{index // count_per + 1:03d}', 'level':level,'system':system,
                                          'board':f'INT-L{level:02d}-{system}-BOARD','source':'A' if system == 'POWER' else 'B',
                                          'terminals':terminals[index:index + count_per],'ratings':None,'evidence':'assumed grouping; no load or protection design'})
                self.electrical_networks.append({'id':f'{system}-L{level:02d}','system':system,'level':level,'source_m':[*root,start_z],
                                                 'terminals':terminals,'requested_terminals':len(targets),'routing_nodes':reachable})
                if system == 'LIGHTING':
                    self.controls(floor,[target for target,_ in ends],origins['CONTROL'],heights['CONTROL'],start_z)

    def controls(self,floor,lights,root,height,start_z):
        p = self.settings['electrical']
        level, z = floor['level'], floor['ffl'] + height
        targets = [{'id':light['id'] + '-CONTROL','xy':light['xy'],'parent':light['id']} for light in lights]
        segments,ends,_,reachable = self.route_tree(floor,root,targets,height)
        for j,(a,b) in enumerate(segments):
            self.electrical_route(f'INT-L{level:02d}-CONTROL-ROUTE-{j:04d}','CONTROL',level,[*a,z],[*b,z])
        terminals = []
        for j,(target,node) in enumerate(ends):
            xy = target['xy']
            snapped = [v * self.settings['services']['routing_grid_m'] for v in node]
            self.electrical_route(target['id'] + '-FINAL','CONTROL',level,[*snapped,z],[*xy,z])
            self.add(target['id'],'INT_CONTROLS',5,level,box([*xy,0.08,0.08,0],z - 0.025,0.025),'dali_interface_proxy',system='CONTROL',
                     connection_m=[*xy,z],parent=target['parent'],link=j // p['addresses_per_control_link'] + 1,
                     address=j % p['addresses_per_control_link'],source_ids=['R05'])
            terminals.append(target['id'])
            if j % 4 == 0:
                self.add(target['id'] + '-SENSOR','INT_CONTROLS',5,level,box([xy[0] + 0.7,xy[1],0.12,0.12,0],floor['ffl'] + 2.70,0.04),
                         'occupancy_daylight_sensor_proxy',source_ids=['R05'],network_status='symbolic sensor; control branch not routed')
        self.electrical_networks.append({'id':f'CONTROL-L{level:02d}','system':'CONTROL','level':level,'source_m':[*root,start_z],
                                         'terminals':terminals,'requested_terminals':len(targets),'routing_nodes':reachable})

    def finish(self):
        recipe = super().finish()
        recipe.update(lift_schedule=self.lifts,electrical_circuits=self.circuits,electrical_networks=self.electrical_networks,
                      source_registry=self.settings['source_registry'],variant='researched')
        recipe['counts'].update(electrical_circuits=len(self.circuits),electrical_networks=len(self.electrical_networks),
                                office_lifts=sum(lift['bank'] != 'upper-concept' for lift in self.lifts),upper_shuttle_proxies=2)
        return recipe
