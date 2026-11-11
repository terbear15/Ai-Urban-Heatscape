"""HeatScape's UI and callbacks, authored in Python and deployed with Panel WASM."""
import asyncio
import csv
import gzip
import html
import io
import json
import math
from pathlib import Path

import panel as pn
from bokeh.models import ColumnDataSource, HoverTool
from bokeh.plotting import figure

from routing import RoutingEngine
from search import AddressSearch, LANDMARKS, find_places

pn.extension('deckgl', sizing_mode='stretch_width', loading_spinner='dots', loading_color='#345b43')
DATA_PATH = Path(globals().get('__file__', 'app.py')).parent / 'data' / 'philadelphia.json.gz'
with gzip.open(DATA_PATH, 'rt', encoding='utf-8') as source:
    data = json.load(source)
engine = RoutingEngine(data)
address_search = AddressSearch()

TEXT_STYLE = {'color': '#254b3e', 'font-family': 'Arial, sans-serif'}
state = {'start': LANDMARKS['Rittenhouse Square'], 'end': LANDMARKS['LOVE Park'],
         'start_label': 'Rittenhouse Square', 'end_label': 'LOVE Park',
         'result': None, 'pick': None, 'search_version': {'start': 0, 'end': 0}}
status = pn.pane.Alert('Ready. Search a Philadelphia address or place, then compare your walk.', alert_type='light')
coverage_note = pn.pane.Alert('', alert_type='warning')
results = pn.pane.Markdown('', styles=TEXT_STYLE)
gap_note = pn.pane.Markdown('', styles={'font-size': '11px', 'color': '#778174'})
hour = pn.widgets.IntSlider(name='Summer time · July 15, 2026 · EDT', start=8, end=19, value=15)
allowance = pn.widgets.IntSlider(name='Extra walking minutes allowed', start=0, end=15, value=5)
perspective = pn.widgets.RadioButtonGroup(name='View', options=['2D map', '3D buildings'], value='3D buildings', button_type='success')
route_choice = pn.widgets.RadioButtonGroup(name='Route', options=['Lower sun', 'Shortest'], value='Lower sun')
show_shadows = pn.widgets.Checkbox(name='Show estimated building shadows', value=True)
compare_button = pn.widgets.Button(name='Compare my walk ↗', button_type='success', height=43)
recenter_button = pn.widgets.Button(name='Recenter route', width=145, height=32, sizing_mode='fixed')


def initial_view():
    return {'longitude': -75.167, 'latitude': 39.9515, 'zoom': 14.6, 'pitch': 48, 'bearing': -18}


tooltip = {'html': '<b>{name}</b><br/>{detail}', 'style': {'color': '#254b3e', 'backgroundColor': '#fffef6'}}
map_pane = pn.pane.DeckGL({}, height=600, sizing_mode='stretch_width', tooltips={
    'buildings': {**tooltip, 'html': '<b>{properties.name}</b><br/>{properties.detail}'},
    'fastest': tooltip, 'alternative': tooltip, 'endpoints': tooltip})


def map_spec(fit=False):
    frame = data['frames'][str(hour.value)]
    buildings = []
    for feature in data['buildings']['features']:
        properties = feature['properties']
        buildings.append({'type': 'Feature', 'geometry': feature['geometry'],
            'properties': {'height': properties['height'], 'name': html.escape(properties['name']),
            'detail': f"{properties['height'] * 3.28084:.0f} ft · {properties['basis']}"}})
    layers = [
        {'@@type': 'GeoJsonLayer', 'id': 'city-boundary', 'data': {'type': 'Feature', 'geometry': data['boundary'], 'properties': {}},
         'filled': False, 'stroked': True, 'getLineColor': [111, 132, 103], 'getLineWidth': 2, 'lineWidthUnits': 'pixels'},
        {'@@type': 'GeoJsonLayer', 'id': 'coverage', 'data': {'type': 'Feature', 'geometry': data['coverage'], 'properties': {}},
         'filled': False, 'stroked': True, 'getLineColor': [184, 130, 74], 'getLineWidth': 2, 'lineWidthUnits': 'pixels'},
    ]
    if show_shadows.value:
        layers.append({'@@type': 'GeoJsonLayer', 'id': 'shadows',
            'data': {'type': 'Feature', 'geometry': frame['geometry'], 'properties': {}},
            'filled': True, 'stroked': False, 'getFillColor': [108, 132, 108, 140]})
    layers.append({'@@type': 'GeoJsonLayer', 'id': 'buildings', 'data': {'type': 'FeatureCollection', 'features': buildings},
        'getElevation': '@@=properties.height',
        'extruded': perspective.value == '3D buildings', 'getFillColor': [216, 215, 191],
        'getLineColor': [185, 188, 167], 'stroked': True, 'lineWidthMinPixels': .3, 'pickable': True})
    view = dict(map_pane.view_state or initial_view())
    view['pitch'] = 48 if perspective.value == '3D buildings' else 0
    result = state['result']
    if result:
        paths = [('fastest', 'Shortest', [195, 128, 77])]
        if result['alternative']:
            paths.append(('alternative', 'Lower sun', [39, 110, 78]))
        paths.sort(key=lambda item: item[1] == route_choice.value)
        for key, name, color in paths:
            route = result[key]
            layers.append({'@@type': 'PathLayer', 'id': key, 'data': [{'path': route['path'], 'name': name,
                'detail': f"{route['miles']:.2f} mi · {route['minutes']:.1f} min at 3 mph"}],
                'getPath': '@@=path', 'getColor': color, 'widthUnits': 'pixels',
                'getWidth': 6 if name == route_choice.value else 3, 'pickable': True})
        if fit:
            coords = result['fastest']['path'] + (result['alternative']['path'] if result['alternative'] else [])
            xs, ys = zip(*coords)
            span = max((max(xs) - min(xs)) * .77, max(ys) - min(ys), .003)
            view = {'longitude': (max(xs) + min(xs)) / 2, 'latitude': (max(ys) + min(ys)) / 2,
                    'zoom': min(16, max(10, math.log2(180 / span) - .65)),
                    'pitch': 48 if perspective.value == '3D buildings' else 0, 'bearing': -18 if perspective.value == '3D buildings' else 0}
    points = [{'position': state[key], 'name': html.escape(state[key + '_label']), 'detail': label,
               'color': color, 'label': label[0]} for key, label, color in
              [('start', 'A · Start', [42, 97, 67]), ('end', 'B · Destination', [183, 117, 77])]]
    layers.extend([
        {'@@type': 'ScatterplotLayer', 'id': 'endpoints', 'data': points, 'getPosition': '@@=position',
         'getFillColor': '@@=color', 'getRadius': 12, 'radiusUnits': 'pixels', 'pickable': True},
        {'@@type': 'TextLayer', 'id': 'endpoint-labels', 'data': points, 'getPosition': '@@=position',
         'getText': '@@=label', 'getSize': 13, 'getColor': [255, 255, 255], 'getTextAnchor': 'middle', 'getAlignmentBaseline': 'center'},
    ])
    # Panel 1.9 uses the URL's 'carto' marker to select its MapLibre adapter.
    # This local style uses Esri tiles and requires no Mapbox/CARTO token.
    return {'mapStyle': './carto-style.json', 'initialViewState': view, 'controller': True, 'layers': layers}


comparison_source = ColumnDataSource(data={'route': [], 'sun': [], 'shade': [], 'unknown': []})
comparison_plot = figure(height=190, y_range=['Shortest', 'Lower sun'], toolbar_location=None,
                         title='Walking minutes by estimated exposure', sizing_mode='stretch_width')
comparison_plot.hbar_stack(['shade', 'sun', 'unknown'], y='route', height=.45, source=comparison_source,
                          color=['#8ca583', '#d9ae71', '#d3d6cc'], legend_label=['Building shade', 'Direct sun', 'No shade data'])
comparison_plot.add_tools(HoverTool(tooltips=[('Route', '@route'), ('Shade', '@shade{0.0} min'),
    ('Sun', '@sun{0.0} min'), ('Unknown', '@unknown{0.0} min')]))
comparison_plot.legend.location = 'bottom_right'
comparison_plot.legend.label_text_font_size = '9px'
comparison_plot.xaxis.axis_label = 'Minutes at 3 mph'
comparison_plot.outline_line_color = None
comparison_plot.background_fill_color = '#fafbf5'

daily_source = ColumnDataSource(data={'hour': [], 'fastest': [], 'alternative': []})
daily_plot = figure(height=225, title='These same routes at different summer hours',
                    x_axis_label='Hour · EDT · July 15, 2026', y_axis_label='Modeled direct-sun minutes',
                    sizing_mode='stretch_width', tools='pan,wheel_zoom,reset,save')
daily_plot.line('hour', 'fastest', source=daily_source, color='#bd8057', line_width=3, legend_label='Shortest')
daily_plot.line('hour', 'alternative', source=daily_source, color='#3e7353', line_width=3, legend_label='Lower sun')
daily_plot.add_tools(HoverTool(tooltips=[('Hour', '@hour'), ('Shortest', '@fastest{0.0} min'), ('Alternative', '@alternative{0.0} min')], mode='vline'))
daily_plot.legend.location = 'top_left'
daily_plot.outline_line_color = None
daily_plot.background_fill_color = '#fafbf5'
daily_pane = pn.Column(pn.pane.Bokeh(daily_plot), visible=True, margin=0)
steps_pane = pn.pane.Markdown('')


def update_steps():
    result = state['result']
    if not result:
        steps_pane.object = ''
        return
    route = result['alternative'] if route_choice.value == 'Lower sun' and result['alternative'] else result['fastest']
    lines = [f"{index + 1}. {html.escape(step['street'])} — {step['feet']:.0f} ft" for index, step in enumerate(route['steps'])]
    steps_pane.object = '**Street sequence**\n\n' + '\n'.join(lines) + '\n\nStreet sequence only. Crossings and entrances need verification.'


def calculate(fit=False):
    if compare_button.disabled:
        return
    try:
        result = engine.compare(state['start'], state['end'], hour.value, allowance.value)
        state['result'] = result
        fast, alternative = result['fastest'], result['alternative']
        rows = [('Shortest', fast)]
        if alternative:
            rows.append(('Lower sun', alternative))
        comparisons = {'route': [], 'sun': [], 'shade': [], 'unknown': []}
        cards = []
        for name, route in rows:
            exposure = f"{route['sun_minutes']:.1f} min modeled sun" if route['complete'] else f"{route['covered']:.0%} shade-data coverage"
            cards.append(f"### {name}\n**{route['minutes']:.0f} min · {route['miles']:.2f} mi**  \n{exposure}")
            comparisons['route'].append(name)
            comparisons['sun'].append(route['sun_minutes'])
            comparisons['shade'].append(route['shade_minutes'])
            comparisons['unknown'].append(route['minutes'] * (1 - route['covered']))
        comparison_source.data = comparisons
        results.object = '\n\n'.join(cards)
        gap_note.object = f"Endpoints are {result['origin_gap_ft']:.0f} ft and {result['destination_gap_ft']:.0f} ft from the network. Those gaps and crossing waits are excluded."
        if alternative:
            saved = fast['sun_minutes'] - alternative['sun_minutes']
            extra = alternative['minutes'] - fast['minutes']
            status.object = (f"{saved:.1f} fewer modeled sun minutes for {extra:.1f} extra walking minutes."
                             if saved > .1 else 'No meaningful lower-sun alternative found within this allowance.')
            status.alert_type = 'success'
            coverage_note.object = 'Building-only shadow scenario · July 15, 2026. Tree shade and sidewalk-side geometry are still pending.'
            daily_source.data = {'hour': list(range(8, 20)),
                'fastest': [engine.summarize(fast['edges'], h)['sun_minutes'] for h in range(8, 20)],
                'alternative': [engine.summarize(alternative['edges'], h)['sun_minutes'] for h in range(8, 20)]}
            daily_pane.visible = True
        else:
            status.object = 'Walking route found. Shade comparison is available only when the whole route has modeled coverage.'
            status.alert_type = 'light'
            coverage_note.object = f"This route has {fast['covered']:.0%} building-shadow coverage. Gray chart segments represent missing data. The amber rectangle marks the current shadow study area."
            daily_pane.visible = False
        update_steps()
    except ValueError as error:
        state['result'] = None
        status.object = str(error)
        status.alert_type = 'danger'
        results.object = ''
        gap_note.object = ''
        comparison_source.data = {'route': [], 'sun': [], 'shade': [], 'unknown': []}
        daily_pane.visible = False
        steps_pane.object = ''
        coverage_note.object = 'Resolve both locations to compare a walk.'
    map_pane.object = map_spec(fit)


def endpoint_controls(key, title):
    field = pn.widgets.TextInput(name=title, value=state[key + '_label'], placeholder='Address or place name in Philadelphia')
    search_button = pn.widgets.Button(name='Search', button_type='default', width=85, height=32, sizing_mode='fixed')
    matches = pn.widgets.Select(name='Choose a search result', options={}, visible=False)
    message = pn.pane.Markdown('', styles={'font-size': '11px', 'color': '#6a785e'})
    candidates = {}

    def mark_changed(event):
        state['search_version'][key] += 1
        matches.visible = False
        message.object = 'Press Search to resolve this location.'
        compare_button.disabled = True
        state['result'] = None
        results.object = ''
        gap_note.object = ''
        steps_pane.object = ''
        comparison_source.data = {'route': [], 'sun': [], 'shade': [], 'unknown': []}
        daily_pane.visible = False
        status.object = 'Resolve the edited location with Search before comparing.'
        status.alert_type = 'light'
        map_pane.object = map_spec()

    def accept(match):
        point = match['point']
        if not engine.inside_city(point):
            raise ValueError('That result is outside Philadelphia. Try another location.')
        state[key] = point
        state[key + '_label'] = match['label']
        message.object = '✓ ' + html.escape(match['label'])
        field.tags = [field.value]
        compare_button.disabled = any(controls[k]['field'].tags != [controls[k]['field'].value] for k in controls)
        calculate(True)

    async def resolve_match(event):
        if not matches.value or matches.value not in candidates:
            return
        state['search_version'][key] += 1
        version = state['search_version'][key]
        match = dict(candidates[matches.value])
        try:
            if match['point'] is None:
                address_matches = await address_search.geocode(match['address'])
                if len(address_matches) != 1:
                    raise ValueError('This name maps to several addresses. Enter its full street address.')
                match['point'] = address_matches[0]['point']
            if version == state['search_version'][key]:
                accept(match)
        except Exception as error:
            if version == state['search_version'][key]:
                message.object = 'Search unavailable. ' + html.escape(str(error))

    async def search_clicked(event):
        query = field.value.strip()
        state['search_version'][key] += 1
        version = state['search_version'][key]
        search_button.disabled = True
        message.object = 'Searching Philadelphia…'
        try:
            found = find_places(query, data['places']) if len(query) >= 2 else []
            if not found:
                found = await address_search.geocode(query)
            if version != state['search_version'][key]:
                return
            candidates.clear()
            candidates.update({match['label']: match for match in found})
            # Disable selection callbacks while replacing the result list.
            with pn.io.hold():
                matches.options = {'Select a result…': '', **{name: name for name in candidates}}
                matches.value = ''
                matches.visible = True
            message.object = f'{len(found)} result(s). Choose the intended location below.'
            if len(found) == 1 and found[0]['point'] is not None:
                accept(found[0])
        except Exception as error:
            if version == state['search_version'][key]:
                message.object = 'Could not resolve this search. ' + html.escape(str(error))
        finally:
            search_button.disabled = False

    field.tags = [field.value]
    field.param.watch(mark_changed, 'value')
    search_button.on_click(search_clicked)
    matches.param.watch(resolve_match, 'value')
    return {'field': field, 'search': search_clicked, 'matches': matches, 'message': message,
            'view': pn.Column(field, search_button, matches, message, margin=(5, 0, 15, 0))}


controls = {}
controls['start'] = endpoint_controls('start', 'Starting point')
controls['end'] = endpoint_controls('end', 'Destination')


def compare_clicked(event):
    calculate(True)


def update_selection(event):
    map_pane.object = map_spec()
    update_steps()


compare_button.on_click(compare_clicked)
hour.param.watch(lambda event: calculate(), 'value_throttled')
allowance.param.watch(lambda event: calculate(), 'value_throttled')
perspective.param.watch(update_selection, 'value')
route_choice.param.watch(update_selection, 'value')
show_shadows.param.watch(update_selection, 'value')
recenter_button.on_click(lambda event: setattr(map_pane, 'object', map_spec(True)))


def export_route():
    output = io.StringIO()
    fields = ['route', 'miles', 'minutes', 'shade_data_coverage', 'modeled_sun_minutes_on_covered_segments']
    writer = csv.writer(output)
    writer.writerow(fields)
    result = state['result']
    if result:
        for name, route in [('Shortest', result['fastest']), ('Lower sun', result['alternative'])]:
            if route:
                writer.writerow([name, route['miles'], route['minutes'], route['covered'], route['sun_minutes']])
    return io.BytesIO(output.getvalue().encode('utf-8'))


download = pn.widgets.FileDownload(callback=export_route, filename='heatscape-route-comparison.csv', label='Download comparison CSV')
methods = pn.pane.Markdown('''
### How to read this map
The green city outline marks Philadelphia. The amber rectangle marks building-shadow coverage.
Citywide routes use a directed OSMnx walking network. Some mapped ways are road centerlines.
Access, crossings and entrances require field verification. Outdoor landmarks are not verified cooling centers.

### What runs in Python
OSMnx prepares the street graph. GeoPandas, Shapely and NumPy prepare hourly building-shadow scenarios.
The route engine, address search and interactive callbacks run in Python through Panel and Pyodide.
The browser downloads the Python environment once on first use. The framework generates browser rendering code.

### Model assumptions
July 15, 2026, at hourly times from 8 AM to 7 PM EDT. Sun position uses a NOAA fractional-year approximation.
Flat ground, opaque buildings, 3 mph walking, a fixed departure-time shadow throughout the trip.
974 of 2,649 building heights are assumed. Trees, weather and terrain are absent.
Boundary effects and incorrect heights can change shade estimates. Estimated sun exposure is not a measured temperature.

Seven exposure penalties generate alternatives within the detour limit. This candidate search does not guarantee a global constrained optimum.
Incomplete shade coverage disables the full-route shade comparison. The time chart evaluates the same two selected routes at other hours.

### Data and attribution
[OpenStreetMap contributors · ODbL](https://www.openstreetmap.org/copyright),
[Philadelphia place names](https://services.arcgis.com/fLeGjb7u4uXqeF9q/arcgis/rest/services/place_names/FeatureServer),
[Philadelphia AIS address service](https://github.com/CityOfPhiladelphia/ais), Census ACS 2024 city boundary.
Basemap © Esri. Street and building data acquired November 10, 2026. Address searches are sent to the city AIS service when submitted.
''', styles=TEXT_STYLE)

calculate(True)
template = pn.template.FastListTemplate(
    title='HeatScape · Philadelphia', site='HeatScape', header_background='#294d3b',
    accent_base_color='#42694c', header_color='#ffffff', background_color='#f5f4ed',
    main_layout=None, sidebar_width=305,
    sidebar=[pn.pane.Markdown('## Where are you headed?\nSearch a place or street address.\n\n[Project & methods ↗](../research/methods.html)', styles=TEXT_STYLE),
             controls['start']['view'], controls['end']['view'], allowance, compare_button,
             results, gap_note, download],
    main=[pn.pane.Markdown('## A little more shade. A better way there.\nPhiladelphia walking routes, with a growing view of the shade along the way.', styles=TEXT_STYLE),
          status, pn.Row(perspective, route_choice, recenter_button), map_pane,
          pn.Row(hour, show_shadows), coverage_note,
          pn.Row(pn.pane.Bokeh(comparison_plot), daily_pane),
          pn.Accordion(('Street sequence', steps_pane), ('Data & methods', methods), active=[])],
)
template.servable()
