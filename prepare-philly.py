"""Convert a public OSM API extract to the bounded prototype dataset (stdlib only)."""
import json, pathlib, xml.etree.ElementTree as ET
root = pathlib.Path(__file__).parent
xml = ET.parse(root / 'osm-philly.xml').getroot()
nodes = {n.attrib['id']: [float(n.attrib['lon']), float(n.attrib['lat'])] for n in xml.findall('node')}
buildings, edges = [], []
def inside(p): return -75.176 <= p[0] <= -75.158 and 39.946 <= p[1] <= 39.957
allowed = {'footway','pedestrian','path','living_street','residential','tertiary','secondary','primary','unclassified','service','steps'}
for w in xml.findall('way'):
    tags = {t.attrib['k']:t.attrib['v'] for t in w.findall('tag')}
    ids = [n.attrib['ref'] for n in w.findall('nd')]
    if not all(i in nodes for i in ids): continue
    coords = [nodes[i] for i in ids]
    if tags.get('building') and tags['building'] != 'no' and len(coords)>3 and ids[0]==ids[-1] and any(inside(p) for p in coords):
        height, source = 12, 'assumed 39 ft'
        try:
            if tags.get('height'):
                height=float(tags['height'].replace('m','').strip()); source='OSM height'
            elif tags.get('building:levels'):
                height=float(tags['building:levels'])*3; source='OSM floors × 9.8 ft'
        except ValueError: pass
        buildings.append({'type':'Feature','properties':{'id':w.attrib['id'],'height':max(3,min(300,height)),'basis':source,'name':tags.get('name','Building')},'geometry':{'type':'Polygon','coordinates':[coords]}})
    if tags.get('highway') in allowed and tags.get('access') not in {'private','no'} and tags.get('foot') not in {'no','private'} and tags.get('service')!='parking_aisle' and tags.get('area')!='yes':
        for a,b in zip(ids,ids[1:]):
            if inside(nodes[a]) and inside(nodes[b]) and a!=b:
                edges.append({'a':a,'b':b,'p':nodes[a],'q':nodes[b],'name':tags.get('name',tags['highway'].replace('_',' ')),'kind':tags['highway']})
data={'buildings':{'type':'FeatureCollection','features':buildings},'edges':edges,'meta':{'source':'https://api.openstreetmap.org/api/0.6/map?bbox=-75.176,39.946,-75.158,39.957','retrieved':'2026-11-10','license':'ODbL, © OpenStreetMap contributors','bounds':[-75.176,39.946,-75.158,39.957],'limitations':'OSM ways only; relation buildings omitted. Road centerlines are not verified sidewalks. Heights may be assumed. No tree canopy or live closures.'}}
(root/'dist'/'philly-data.js').write_text('window.PHILLY='+json.dumps(data,separators=(',',':'))+';',encoding='utf-8')
print(len(buildings),'buildings;',len(edges),'network segments;',sum(b['properties']['basis'].startswith('assumed') for b in buildings),'assumed heights')
