/* HeatScape shade map page. CITY is set by shade.html; the heavy work runs in shade-worker.js.
 * Sections: helpers · worker · map · search · time and season · routes · results · controls. */
(function () {
'use strict';
const $ = id => document.getElementById(id);
const fc = features => ({type: 'FeatureCollection', features});
const empty = fc([]);
const WALK = 80.4672; // meters per minute (3 mph)
const css = name => getComputedStyle(document.body).getPropertyValue(name).trim() || '#888';
const cityBounds = CITY.bounds;
const center = [(cityBounds[0][0] + cityBounds[1][0]) / 2, (cityBounds[0][1] + cityBounds[1][1]) / 2];

// ---------- units (U16) ----------
let units = (() => { try { return localStorage.getItem('heatscape-units') || 'imperial'; } catch (e) { return 'imperial'; } })();
function distance(m) {
  if (units === 'metric') return m < 950 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 9500 ? 2 : 1)} km`;
  const mi = m / 1609.344;
  return mi < .1 ? `${Math.round(m * 3.28084 / 10) * 10} ft` : `${mi.toFixed(2)} mi`;
}
const shortDistance = m => units === 'metric' ? `${Math.round(m)} m` : `${Math.round(m * 3.28084)} ft`;
const minutes = v => v < 1 && v > 0 ? `${Math.round(v * 60)} sec` : `${(Math.round(v * 10) / 10).toFixed(v < 10 ? 1 : 0)} min`;

// ---------- status and errors (T7) ----------
function status(text) { $('routeStatus').textContent = text; }
function problem(text) {
  const box = $('mapError');
  box.hidden = !text;
  box.textContent = text || '';
}

// ---------- worker ----------
const worker = new Worker('shade-worker.js?' + CITY.version);
let seq = 0;
const pending = new Map();
function call(msg) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, {resolve, reject});
    worker.postMessage({...msg, id});
  });
}
worker.onmessage = ({data}) => {
  if (data.type === 'ready') return onData(data.stats);
  const job = pending.get(data.id);
  if (!job) return;
  pending.delete(data.id);
  data.type === 'error' ? job.reject(new Error(data.message)) : job.resolve(data);
};
worker.onerror = () => {
  problem('The shade model could not start in this browser. Please refresh the page.');
  loading(null);
};
worker.postMessage({type: 'init', slug: CITY.slug, version: CITY.version});

// ---------- loading steps (U5) ----------
const steps = ['stepMap', 'stepData', 'stepShade'];
function loading(step) {
  if (step === null) { $('mapLoading').hidden = true; return; }
  const index = steps.indexOf(step);
  steps.forEach((id, i) => { $(id).className = i < index ? 'done' : i === index ? 'active' : ''; });
  $('loadBar').style.width = `${(index + .5) / steps.length * 100}%`;
}

// ---------- state ----------
let season = 'summer', ready = false, mapReady = false, dataReady = false, stats = null;
let picking = null, result = null, selected = 'best', routeVersion = 0, shadeVersion = 0;
const endpoints = {start: null, end: null};
const markers = {};
const hasLocation = key => Boolean(endpoints[key] && endpoints[key].label === $(key).value.trim());
const hasTrip = () => hasLocation('start') && hasLocation('end');

// ---------- study area ----------
let areaRings = null;
const contains = (p, ring) => {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
};
fetch('cities/' + CITY.slug + '.geojson').then(r => r.json()).then(collection => {
  const g = collection.features.find(f => f.properties.layer === 'land').geometry;
  areaRings = (g.type === 'Polygon' ? [g.coordinates] : g.coordinates).map(polygon => polygon[0]);
}).catch(() => {});
// Inside the dashed area, or within ~120 m of its edge (the data reaches 150 m beyond it).
function inArea(p) {
  if (!areaRings) return true;
  if (areaRings.some(r => contains(p, r))) return true;
  const kx = 111320 * Math.cos(p[1] * Math.PI / 180);
  return areaRings.some(r => r.some(q => Math.hypot((q[0] - p[0]) * kx, (q[1] - p[1]) * 110540) < 120));
}

// ---------- map ----------
let map;
try {
  map = new maplibregl.Map({
    container: 'map', center, zoom: 14, minZoom: 10, maxZoom: 19, maxPitch: 0, dragRotate: false, pitchWithRotate: false,
    attributionControl: {compact: true},
    style: {version: 8, sources: {
      base: {type: 'raster', tileSize: 256, maxzoom: 16, tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
             attribution: 'Basemap © Esri · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors · LiDAR: USGS 3DEP / NOAA'},
      labels: {type: 'raster', tileSize: 256, maxzoom: 16, tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}']},
    }, layers: [{id: 'background', type: 'background', paint: {'background-color': '#ecebe6'}}, {id: 'basemap', type: 'raster', source: 'base', paint: {'raster-fade-duration': 0}}]},
  });
} catch (error) {
  problem('This browser could not start the map (WebGL is needed). Routes cannot be shown here.');
  $('calculate').disabled = true;
}
const scale = map && new maplibregl.ScaleControl({unit: units});
if (map) {
  map.addControl(new maplibregl.NavigationControl({showCompass: false}), 'top-right');
  map.addControl(scale, 'bottom-left');
  map.on('error', event => {
    if (event.sourceId === 'base' || event.sourceId === 'labels') problem('Background map tiles are not loading. Routes and shade still work.');
  });
  map.on('load', () => {
    const v = CITY.version;
    map.addSource('area', {type: 'geojson', data: 'cities/' + CITY.slug + '.geojson', tolerance: 0});
    map.addLayer({id: 'labels', type: 'raster', source: 'labels', paint: {'raster-fade-duration': 0, 'raster-opacity': .8}});
    map.addSource('building-shadows', {type: 'geojson', data: empty, tolerance: .3});
    map.addLayer({id: 'building-shadows', type: 'fill', source: 'building-shadows', paint: {'fill-color': css('--map-building-shadow'), 'fill-opacity': .9, 'fill-antialias': false}});
    map.addSource('tree-shadows', {type: 'geojson', data: empty, tolerance: .3});
    map.addLayer({id: 'tree-shadows', type: 'fill', source: 'tree-shadows', paint: {'fill-color': css('--map-tree-shadow'), 'fill-opacity': .9, 'fill-antialias': false}});
    map.addSource('trees', {type: 'geojson', data: `data/${CITY.slug}-trees.geojson?${v}`});
    map.addLayer({id: 'trees', type: 'fill', source: 'trees', paint: {'fill-color': css('--map-tree'), 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 13, .55, 16, .9]}});
    map.addSource('buildings', {type: 'geojson', data: `data/${CITY.slug}-buildings.geojson?${v}`});
    map.addLayer({id: 'buildings', type: 'fill', source: 'buildings', paint: {
      'fill-color': css('--map-building'), 'fill-outline-color': css('--map-building-edge'),
      // Zoomed out, buildings fade so the shade pattern reads (D7).
      'fill-opacity': ['interpolate', ['linear'], ['zoom'], 13, .15, 15, .5, 16.5, .95]}});
    map.addLayer({id: 'city-mask', type: 'fill', source: 'area', filter: ['==', ['get', 'layer'], 'mask'], paint: {'fill-color': css('--map-mask'), 'fill-opacity': .62, 'fill-antialias': false}});
    map.addLayer({id: 'city-limits', type: 'line', source: 'area', filter: ['==', ['get', 'layer'], 'land'], paint: {'line-color': css('--map-boundary'), 'line-width': 1.6, 'line-opacity': .9, 'line-dasharray': [3, 2]}});
    for (const key of ['fast', 'mid', 'best']) {
      map.addSource('route-' + key, {type: 'geojson', data: empty});
      const layout = {'line-join': 'round', 'line-cap': 'round'};
      map.addLayer({id: 'route-' + key + '-halo', type: 'line', source: 'route-' + key, layout, paint: {'line-color': '#fff', 'line-width': 8, 'line-opacity': .9}});
      map.addLayer({id: 'route-' + key, type: 'line', source: 'route-' + key, layout, paint: {'line-width': 4}});
    }
    map.addSource('pause', {type: 'geojson', data: empty});
    map.addLayer({id: 'pause', type: 'circle', source: 'pause', paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 3, 17, 7], 'circle-color': ['match', ['get', 'kind'],
        'water', '#3f8fd6', 'park', '#4f9a62', 'library', '#8a63c2', 'community', '#c2782f', 'mall', '#b0577e', 'station', '#4c6a8a', '#666'],
      'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5}});
    map.on('click', 'pause', event => {
      const p = event.features[0].properties;
      new maplibregl.Popup({closeButton: false}).setLngLat(event.lngLat)
        .setHTML(`<b>${escapeHtml(p.name)}</b><br><span style="color:#666">${PAUSE_LABEL[p.kind] || p.kind}</span>`).addTo(map);
    });
    map.on('mouseenter', 'pause', () => { if (!picking) map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'pause', () => { if (!picking) map.getCanvas().style.cursor = ''; });
    // U10: picking outside the area shows a "not allowed" cursor.
    map.on('mousemove', event => {
      if (picking) map.getCanvas().style.cursor = inArea([event.lngLat.lng, event.lngLat.lat]) ? 'crosshair' : 'not-allowed';
    });
    map.on('click', event => {
      if (!picking) return;
      const point = [event.lngLat.lng, event.lngLat.lat];
      if (!inArea(point)) { status('That point is outside the dashed area. Pick a spot inside it.'); return; }
      useLocation(picking, `Pin at ${point[1].toFixed(5)}, ${point[0].toFixed(5)}`, point);
      stopPicking();
    });
    map.fitBounds(cityBounds, {padding: 40, duration: 0});
    mapReady = true;
    paintColors();
    loading(dataReady ? 'stepShade' : 'stepData');
    start();
  });
}

const PAUSE_LABEL = {water: 'Drinking water', park: 'Park', library: 'Library (indoor, public)',
                     community: 'Community center (indoor)', mall: 'Shopping mall (indoor)', station: 'Station (indoor)'};
const PAUSE_SEASON = {summer: ['water', 'park', 'library', 'community'], winter: ['library', 'community', 'mall', 'station']};
const escapeHtml = s => String(s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

function onData(s) {
  stats = s;
  dataReady = true;
  const meta = s.meta;
  const fill = {areaNote: meta.area || '', treeNote: meta.tree_method || meta.tree_source || ''};
  for (const node of document.querySelectorAll('[data-t]')) if (fill[node.dataset.t]) node.textContent = fill[node.dataset.t];
  for (const node of document.querySelectorAll('[data-t-href]')) if (meta.lidar_url) node.href = meta.lidar_url;
  if (!s.trees) { $('treeShade').checked = false; $('treeShade').disabled = true; }
  loading(mapReady ? 'stepShade' : 'stepMap');
  start();
}

function start() {
  if (!mapReady || !dataReady || ready) return;
  ready = true;
  updatePause();
  restoreFromUrl();
  if (!hasTrip()) status('Enter where you start and where you are going, or pick both on the map.');
  refreshShade().then(() => loading(null));
  if (hasTrip()) calculate(true);
}

// ---------- colors (D2, D7) ----------
function paintColors() {
  if (!mapReady) return;
  const set = (layer, prop, token) => map.setPaintProperty(layer, prop, css(token));
  set('building-shadows', 'fill-color', '--map-building-shadow');
  set('tree-shadows', 'fill-color', '--map-tree-shadow');
  set('trees', 'fill-color', '--map-tree');
  set('buildings', 'fill-color', '--map-building');
  set('buildings', 'fill-outline-color', '--map-building-edge');
  set('city-mask', 'fill-color', '--map-mask');
  set('city-limits', 'line-color', '--map-boundary');
  styleRoutes();
}

// Selected route: colored by sun along the way; others: their own color, thinner.
function styleRoutes() {
  if (!mapReady) return;
  const own = {fast: css('--route-short'), mid: css('--ink-2'), best: css('--route-better')};
  const ramp = ['interpolate', ['linear'], ['get', 'sun'], 0, css('--ramp-shade'), 1, css('--ramp-sun')];
  for (const key of ['fast', 'mid', 'best']) {
    const active = key === selected;
    map.setPaintProperty('route-' + key, 'line-color', active ? ramp : own[key]);
    map.setPaintProperty('route-' + key, 'line-width', active ? 6 : 3.5);
    map.setPaintProperty('route-' + key, 'line-opacity', active ? 1 : .75);
    map.setPaintProperty('route-' + key + '-halo', 'line-width', active ? 10 : 6);
  }
  const layer = 'route-' + selected;
  map.moveLayer(layer + '-halo'); map.moveLayer(layer); map.moveLayer('pause');
}

// ---------- places to pause (F9) ----------
function updatePause() {
  if (!ready) return;
  const kinds = PAUSE_SEASON[season];
  $('pauseLabel').textContent = season === 'winter' ? 'Places to warm up' : 'Places to cool off';
  const features = $('pauseToggle').checked ? (stats.pois || []).filter(p => kinds.includes(p[1])).map(([name, kind, lon, lat]) =>
    ({type: 'Feature', properties: {name, kind}, geometry: {type: 'Point', coordinates: [lon, lat]}})) : [];
  map.getSource('pause').setData(fc(features));
}

// ---------- search (U8, U9) ----------
const normalize = text => text.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[’'`.]/g, '').replace(/[^a-z0-9]+/g, ' ').trim();
const placeIndex = (window.PLACES || []).map(([name, kind, lon, lat, street]) =>
  ({name, kind, street: street || '', point: [lon, lat], key: normalize(name), words: normalize(name).split(' ')}));
function findPlaces(query) {
  const q = normalize(query);
  if (!q) return [];
  const tokens = q.split(' ');
  const scored = [];
  for (const place of placeIndex) {
    let score;
    if (place.key === q) score = 0;
    else if (place.key.startsWith(q)) score = 1;
    else if (tokens.every(t => place.words.some(w => w.startsWith(t)))) score = 2;
    else if (place.key.includes(q)) score = 3;
    else continue;
    scored.push([score, place.key.length, place]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const out = [], seen = new Set();
  for (const [, , place] of scored) {
    const key = place.key + '|' + place.street; // same name on another street is another place
    if (seen.has(key) || !inArea(place.point)) continue;
    seen.add(key);
    out.push({label: place.name, detail: [place.kind, place.street].filter(Boolean).join(' · '), point: place.point});
    if (out.length === 8) break;
  }
  return out;
}
async function findAddresses(query) {
  const [[w, s], [e, n]] = [CITY.limit[0], CITY.limit[1]];
  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(query + ' ' + CITY.name)}&bbox=${w},${s},${e},${n}&limit=10&lang=en`;
  let response;
  try { response = await fetch(url); } catch (error) { response = null; }
  if (!response || !response.ok) throw new Error('Address search is not responding. Try a landmark name, or pick the point on the map.');
  const data = await response.json();
  const out = [], seen = new Set();
  for (const f of data.features || []) {
    const point = f.geometry.coordinates;
    if (!inArea(point)) continue;
    const p = f.properties;
    const street = [p.housenumber, p.street].filter(Boolean).join(' ');
    const label = p.name || street || 'Address';
    const detail = p.name ? street : (p.district || p.city || '');
    if (seen.has(label + detail)) continue;
    seen.add(label + detail);
    out.push({label, detail, point});
  }
  return out;
}
async function lookup(query, suggest) {
  const local = /^\d/.test(query.trim()) ? [] : findPlaces(query);
  if (local.length) return local;
  if (suggest && query.trim().length < 4) return [];
  const found = await findAddresses(query);
  if (!found.length && !suggest) throw new Error(`Nothing found inside the ${CITY.areaName.toLowerCase()} area. Try a landmark or a street address, or pick the point on the map.`);
  return found;
}
const timers = {}, searches = {start: 0, end: 0};
async function search(key, suggest = false) {
  clearTimeout(timers[key]);
  const version = ++searches[key];
  const query = $(key).value.trim(), list = $(key + 'Matches');
  if (!query) { status('Type a place or address first.'); return; }
  if (!suggest) { $(key + 'Search').disabled = true; status('Searching…'); }
  try {
    const matches = await lookup(query, suggest);
    if ($(key).value.trim() !== query || searches[key] !== version) return;
    if (!suggest && matches.length === 1) { useLocation(key, matches[0].label, matches[0].point); return; }
    list.replaceChildren(...matches.map(match => {
      const option = document.createElement('button');
      option.type = 'button';
      option.innerHTML = `${escapeHtml(match.label)}${match.detail ? `<small>${escapeHtml(match.detail)}</small>` : ''}`;
      option.onclick = () => useLocation(key, match.label, match.point);
      return option;
    }));
    list.hidden = !matches.length;
    if (!suggest) status(matches.length ? 'Choose the matching place.' : 'No match.');
  } catch (error) {
    if (!suggest && $(key).value.trim() === query) status(error.message);
  } finally {
    if (!suggest) $(key + 'Search').disabled = false;
  }
}
function useLocation(key, label, point) {
  endpoints[key] = {label, point};
  $(key).value = label;
  $(key + 'Matches').hidden = true;
  marker(key, point);
  clearRoute();
  if (hasTrip()) calculate(true);
  else status(key === 'start' ? 'Now choose where you are going.' : 'Now choose where you start.');
}
function marker(key, point) {
  if (!map) return;
  if (!markers[key]) {
    const el = document.createElement('div');
    el.className = 'marker' + (key === 'end' ? ' end' : '');
    el.textContent = key === 'start' ? 'A' : 'B';
    el.setAttribute('aria-label', key === 'start' ? 'Start' : 'Destination');
    markers[key] = new maplibregl.Marker({element: el}).setLngLat(point).addTo(map);
  } else markers[key].setLngLat(point);
}

// ---------- time and season ----------
const SEASONS = {
  summer: {min: '2026-06-01', max: '2026-08-31', date: '2026-07-15', hour: 15, last: 19, offset: CITY.tz.summer, zone: CITY.tz.summerName},
  winter: {min: '2026-12-01', max: '2027-02-28', date: '2027-01-15', hour: 12, last: 17, offset: CITY.tz.winter, zone: CITY.tz.winterName},
};
function clock() {
  const t = +$('time').value, h = Math.floor(t), m = Math.round((t - h) * 60);
  $('timeLabel').textContent = `${h % 12 || 12}:${String(m).padStart(2, '0')} ${h >= 12 ? 'PM' : 'AM'}`;
  return {h, m};
}
function departure(hour) {
  const {h, m} = hour === undefined ? clock() : {h: Math.floor(hour), m: Math.round((hour % 1) * 60)};
  const date = $('date').value || SEASONS[season].date;
  return new Date(`${date}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00${SEASONS[season].offset}`).getTime();
}
const useTrees = () => season === 'summer' && $('treeShade').checked && !$('treeShade').disabled;

function setSeason(next, quiet) {
  season = next;
  const winter = next === 'winter', s = SEASONS[next];
  document.body.dataset.season = next;
  $('seasonTitle').textContent = winter ? 'Find the sunnier way.' : 'Find the shadier way.';
  $('walkMode').textContent = winter ? 'WINTER · SEEK SUN' : 'SUMMER · SEEK SHADE';
  $('candidateLegend').textContent = winter ? 'Sunniest route' : 'Shadiest route';
  $('dateLabel').textContent = winter ? 'WINTER DAY' : 'SUMMER DAY';
  $('timezone').textContent = s.zone;
  $('lastHour').textContent = winter ? '5 PM' : '7 PM';
  $('detourAutoRow').hidden = !winter;
  $('treeShade').disabled = winter || (stats && !stats.trees);
  Object.assign($('date'), {min: s.min, max: s.max, value: s.date});
  Object.assign($('time'), {max: s.last, value: s.hour});
  clock();
  detourLabel();
  if (quiet || !ready) return;
  paintColors();
  updatePause();
  clearRoute();
  refreshShade();
  if (hasTrip()) calculate();
}

// Shadows on the map. While the slider moves only the shadows update (U13).
let shadeBusy = false, shadeAgain = false;
async function refreshShade() {
  if (!ready) return;
  if (shadeBusy) { shadeAgain = true; return; }
  shadeBusy = true;
  const version = ++shadeVersion, trees = useTrees();
  try {
    const out = await call({type: 'shade', time: departure(), lat: center[1], lon: center[0], trees});
    if (version === shadeVersion) {
      map.getSource('building-shadows').setData(fc(out.geometry ? out.geometry.buildings : []));
      map.getSource('tree-shadows').setData(fc(out.geometry ? out.geometry.trees : []));
      const sun = SunCalc.getPosition(new Date(departure()), center[1], center[0]);
      $('solarLabel').textContent = out.night ? 'The sun is below the horizon' : `Sun ${Math.round(sun.altitude * 180 / Math.PI)}° above the horizon`;
      $('treeStatus').textContent = season === 'winter' ? 'Leaf-off: trees are not counted in winter' :
        trees ? `${stats.trees.toLocaleString()} LiDAR-measured tree crowns` : 'Buildings only';
    }
  } catch (error) {
    problem('Shade could not be computed: ' + error.message);
  } finally {
    shadeBusy = false;
    if (shadeAgain) { shadeAgain = false; refreshShade(); }
  }
}

// ---------- routes ----------
function extraMinutes() {
  if (season === 'winter' && $('detourAuto').checked && hasTrip()) {
    // F7: about 15% of the walk, estimated from the straight-line distance.
    const [a, b] = [endpoints.start.point, endpoints.end.point];
    const kx = 111320 * Math.cos(a[1] * Math.PI / 180);
    const walk = Math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * 110540) * 1.3 / WALK;
    return Math.max(1, Math.min(8, Math.round(walk * .15)));
  }
  return +$('detour').value;
}
function detourLabel() {
  const auto = season === 'winter' && $('detourAuto').checked;
  $('detour').disabled = auto;
  $('detourLabel').textContent = auto ? (hasTrip() ? `Auto · up to ${extraMinutes()} min` : 'Auto') : `Up to ${$('detour').value} min`;
}

async function calculate(zoom = false) {
  if (!ready || !hasTrip()) return;
  const version = ++routeVersion;
  const a = endpoints.start.point, b = endpoints.end.point;
  if (!inArea(a) || !inArea(b)) { clearRoute(); status('Both points need to be inside the dashed area.'); return; }
  detourLabel();
  status('Comparing routes…');
  $('calculate').disabled = true;
  try {
    const out = await call({type: 'route', a, b, time: departure(), lat: center[1], lon: center[0],
                            trees: useTrees(), extra: extraMinutes(), winter: season === 'winter'});
    if (version !== routeVersion) return;
    result = out.result;
    if (!result.mid && selected === 'mid') selected = 'best';
    drawRoutes();
    renderResults();
    saveToUrl();
    if (zoom) fitRoute();
    bestTime(version);
  } catch (error) {
    if (version === routeVersion) { clearRoute(); status(error.message); }
  } finally {
    if (version === routeVersion) $('calculate').disabled = false;
  }
}
function lineFeatures(route) {
  return fc(route.parts.map(p => ({type: 'Feature', properties: {sun: p.sun}, geometry: {type: 'LineString', coordinates: p.coords}})));
}
function drawRoutes() {
  for (const key of ['fast', 'mid', 'best']) {
    const r = result[key];
    const show = r && (key === 'fast' || !same(r, result.fast));
    map.getSource('route-' + key).setData(show ? lineFeatures(r) : empty);
  }
  styleRoutes();
}
const same = (x, y) => x && y && Math.abs(x.length - y.length) < .5 && Math.abs(x.exposure - y.exposure) < .5;
function clearRoute() {
  result = null;
  ++routeVersion;
  if (mapReady) for (const key of ['fast', 'mid', 'best']) map.getSource('route-' + key).setData(empty);
  $('results').replaceChildren();
}
function fitRoute() {
  if (!result) return map.fitBounds(cityBounds, {padding: 40, duration: 600});
  const box = new maplibregl.LngLatBounds();
  for (const key of ['fast', 'mid', 'best']) if (result[key]) result[key].coords.forEach(p => box.extend(p));
  map.fitBounds(box, {padding: {top: 60, bottom: 80, left: 60, right: 60}, maxZoom: 17, duration: 700});
}

// ---------- results (D10, U11, U12, U14, U15) ----------
function profile(route) {
  const total = route.length || 1;
  return `<div class="profile" aria-hidden="true">${route.parts.map(p =>
    `<i style="width:${(p.length / total * 100).toFixed(2)}%;background:${mix(p.sun)}"></i>`).join('')}</div>`;
}
// Color between shade and sun tokens.
function mix(t) {
  const a = hex(css('--ramp-shade')), b = hex(css('--ramp-sun'));
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`;
}
function hex(color) {
  const c = color.replace('#', '');
  const full = c.length === 3 ? c.split('').map(x => x + x).join('') : c;
  return [0, 2, 4].map(i => parseInt(full.slice(i, i + 2), 16));
}
function card(key, title, tag) {
  const r = result[key];
  const winter = season === 'winter';
  const share = winter ? r.exposure / r.length : 1 - r.exposure / r.length;
  return `<button type="button" class="route-card ${key === 'fast' ? 'direct' : key === 'mid' ? 'mid' : ''}" data-route="${key}" aria-pressed="${key === selected}">
    <div class="card-title"><span><i style="background:${key === 'fast' ? 'var(--route-short)' : key === 'mid' ? 'var(--ink-2)' : 'var(--route-better)'}"></i>${title}</span><small>${tag}</small></div>
    <div class="route-stats"><strong>${Math.round(r.minutes)} min</strong><span>${distance(r.length)}</span></div>
    ${profile(r)}
    <div class="card-foot"><span>${minutes(r.sunMinutes)} in direct sun</span><span>${Math.round(share * 100)}% ${winter ? 'sun' : 'shade'}</span></div>
  </button>`;
}
function renderResults() {
  const winter = season === 'winter', fast = result.fast, best = result.best;
  const better = !same(best, fast);
  const gain = winter ? best.sunMinutes - fast.sunMinutes : fast.sunMinutes - best.sunMinutes;
  const extra = best.minutes - fast.minutes;
  const night = SunCalc.getPosition(new Date(departure()), center[1], center[0]).altitude <= 0;
  let hero;
  if (better) {
    hero = `<div class="result-hero"><div class="big">${minutes(gain)} <span>${winter ? 'more sun' : 'less direct sun'}</span></div>
      <p>for ${extra < .05 ? 'no' : minutes(extra)} extra walking · ${Math.round((winter ? best.exposure / best.length : 1 - best.exposure / best.length) * 100)}% of the way in ${winter ? 'sun' : 'shade'}</p></div>`;
  } else {
    hero = `<div class="result-hero"><div class="big" style="font-size:22px">${night ? 'Sun is down' : 'Shortest is best'}</div>
      <p>${night ? 'No direct sun at this time.' : `No ${winter ? 'sunnier' : 'shadier'} route within ${extraMinutes()} extra min.`}</p></div>`;
  }
  const cards = (better ? card('best', winter ? 'Sunniest' : 'Shadiest', 'BEST') : '') +
    (result.mid && better && !same(result.mid, best) ? card('mid', 'Balanced', 'UP TO 1 MIN EXTRA') : '') +
    card('fast', 'Shortest', better ? 'BASELINE' : 'RECOMMENDED');
  if (!better) selected = 'fast';
  $('results').innerHTML = hero + cards +
    `<details class="panel" id="streetsPanel"><summary>Street by street</summary><ol class="streets" id="streets"></ol></details>
     <details class="panel" id="timePanel"><summary>Best time to leave</summary><div class="best-time" id="bestTime"><p class="small">Working it out…</p></div></details>
     <p class="result-note">${winter ? 'Winter: leaf-off, buildings only.' : useTrees() ? 'Buildings and LiDAR trees.' : 'Buildings only.'}
     Start and end snapped ${shortDistance(result.start.meters)} / ${shortDistance(result.end.meters)} to the walking network.</p>
     <button type="button" class="swap" id="share">Copy a link to this route</button>`;
  for (const button of document.querySelectorAll('.route-card')) button.onclick = () => select(button.dataset.route);
  $('share').onclick = share;
  select(selected);
  status(`Walking at 3 mph${winter ? '' : ', leaving at ' + $('timeLabel').textContent}.`);
}
function select(key) {
  if (!result || !result[key]) key = 'fast';
  selected = key;
  for (const b of document.querySelectorAll('.route-card')) {
    const on = b.dataset.route === key;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', String(on));
  }
  styleRoutes();
  streets();
  if (lastBest) drawBestTime(lastBest);
}
function streets() {
  const list = $('streets');
  if (!list || !result) return;
  const groups = [];
  for (const p of result[selected].parts) {
    const last = groups.at(-1);
    if (last && last.name === p.name && last.side === p.side) { last.length += p.length; last.sunM += p.length * p.sun; }
    else groups.push({name: p.name || 'Unnamed way', side: p.side, length: p.length, sunM: p.length * p.sun});
  }
  list.innerHTML = groups.filter(g => g.length >= 8).map(g => `<li><b style="background:${mix(g.sunM / g.length)}"></b>
    <span>${escapeHtml(g.name)}${g.side ? ` <span class="small">· ${g.side} side</span>` : ''}</span>
    <span>${distance(g.length)} · ${Math.round(g.sunM / g.length * 100)}% sun</span></li>`).join('');
}
let lastBest = null;
async function bestTime(version) {
  const s = SEASONS[season];
  const hours = [];
  for (let h = 8; h <= s.last; h++) hours.push(h);
  lastBest = null;
  try {
    const out = await call({type: 'besttime', segments: result.segmentIds, times: hours.map(h => departure(h)),
                            lat: center[1], lon: center[0], trees: useTrees(), winter: season === 'winter'});
    if (version !== routeVersion) return;
    lastBest = out.hours.map((v, i) => ({...v, hour: hours[i]}));
    drawBestTime(lastBest);
  } catch (error) {
    const box = $('bestTime');
    if (box) box.innerHTML = `<p class="small">Could not compute: ${escapeHtml(error.message)}</p>`;
  }
}
function drawBestTime(rows) {
  const box = $('bestTime');
  if (!box) return;
  const key = selected === 'fast' ? 'fast' : 'best';
  const winter = season === 'winter';
  const values = rows.map(r => r[key]);
  const max = Math.max(...values, .1);
  const pick = values.indexOf(winter ? Math.max(...values) : Math.min(...values));
  const now = +$('time').value;
  const W = 300, H = 92, bw = W / rows.length;
  const bars = rows.map((r, i) => {
    const h = Math.max(1.5, (r[key] / max) * (H - 26));
    const cls = 'bar' + (i === pick ? ' best' : '') + (Math.floor(now) === r.hour ? ' now' : '');
    return `<rect class="${cls}" x="${i * bw + 2}" y="${H - 14 - h}" width="${bw - 4}" height="${h}" rx="2"><title>${label(r.hour)}: ${minutes(r[key])} of sun</title></rect>` +
      (i % 2 === 0 ? `<text x="${i * bw + bw / 2}" y="${H - 2}" text-anchor="middle">${label(r.hour, true)}</text>` : '');
  }).join('');
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Minutes of direct sun by departure hour">${bars}</svg>
    <p class="small">Leave around <b>${label(rows[pick].hour)}</b> for the ${winter ? 'most' : 'least'} sun on this route (${minutes(values[pick])}).
    <button type="button" class="swap" id="useBest">Use ${label(rows[pick].hour)}</button></p>`;
  $('useBest').onclick = () => { $('time').value = rows[pick].hour; clock(); refreshShade(); calculate(); };
}
const label = (h, short) => short ? `${h % 12 || 12}${h >= 12 ? 'p' : 'a'}` : `${h % 12 || 12} ${h >= 12 ? 'PM' : 'AM'}`;

// ---------- share (U15) ----------
function saveToUrl() {
  if (!hasTrip()) return;
  const p = new URLSearchParams({city: CITY.slug});
  const pt = q => `${q[0].toFixed(5)},${q[1].toFixed(5)}`;
  p.set('from', pt(endpoints.start.point)); p.set('fromName', endpoints.start.label);
  p.set('to', pt(endpoints.end.point)); p.set('toName', endpoints.end.label);
  p.set('season', season); p.set('date', $('date').value); p.set('time', $('time').value); p.set('extra', $('detour').value);
  history.replaceState(null, '', '?' + p.toString());
}
function restoreFromUrl() {
  const p = new URLSearchParams(location.search);
  const read = s => s && s.split(',').map(Number).every(Number.isFinite) ? s.split(',').map(Number) : null;
  const from = read(p.get('from')), to = read(p.get('to'));
  if (p.get('date')) $('date').value = p.get('date');
  if (p.get('time')) { $('time').value = p.get('time'); clock(); }
  if (p.get('extra')) { $('detour').value = p.get('extra'); detourLabel(); }
  for (const [key, point, name] of [['start', from, p.get('fromName')], ['end', to, p.get('toName')]]) {
    if (!point) continue;
    endpoints[key] = {label: name || 'Shared point', point};
    $(key).value = endpoints[key].label;
    marker(key, point);
  }
}
async function share() {
  saveToUrl();
  try { await navigator.clipboard.writeText(location.href); $('share').textContent = 'Link copied'; }
  catch (error) { $('share').textContent = 'Copy the address bar to share'; }
}

// ---------- controls ----------
function stopPicking() {
  picking = null;
  if (map) map.getCanvas().style.cursor = '';
  document.querySelectorAll('.pick-row button').forEach(b => b.classList.remove('active'));
}
for (const [id, key] of [['pickStart', 'start'], ['pickEnd', 'end']]) {
  $(id).onclick = () => {
    if (!ready) return;
    if (picking === key) { stopPicking(); status('Map picking canceled.'); return; }
    picking = key;
    document.querySelectorAll('.pick-row button').forEach(b => b.classList.toggle('active', b.id === id));
    status(`Click inside the dashed area to choose your ${key === 'start' ? 'start' : 'destination'}.`);
  };
}
for (const key of ['start', 'end']) {
  $(key + 'Search').onclick = () => search(key);
  $(key).addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); search(key); }
    else if (event.key === 'Escape') { ++searches[key]; $(key + 'Matches').hidden = true; }
    else if (event.key === 'ArrowDown') { const first = $(key + 'Matches').querySelector('button'); if (first) { event.preventDefault(); first.focus(); } }
  });
  $(key + 'Matches').addEventListener('keydown', event => {
    const items = [...$(key + 'Matches').querySelectorAll('button')], i = items.indexOf(document.activeElement);
    if (event.key === 'ArrowDown' && i < items.length - 1) { event.preventDefault(); items[i + 1].focus(); }
    if (event.key === 'ArrowUp') { event.preventDefault(); (i > 0 ? items[i - 1] : $(key)).focus(); }
    if (event.key === 'Escape') { $(key + 'Matches').hidden = true; $(key).focus(); }
  });
  $(key).addEventListener('input', () => {
    $(key + 'Matches').hidden = true;
    ++searches[key];
    clearTimeout(timers[key]);
    const query = $(key).value.trim();
    if (!query) { endpoints[key] = null; if (markers[key]) { markers[key].remove(); delete markers[key]; } clearRoute(); return; }
    if (hasLocation(key)) return;
    if (query.length >= 2) timers[key] = setTimeout(() => search(key, true), 140);
  });
}
$('swap').onclick = () => {
  [endpoints.start, endpoints.end] = [endpoints.end, endpoints.start];
  for (const key of ['start', 'end']) {
    $(key).value = endpoints[key] ? endpoints[key].label : '';
    if (endpoints[key]) marker(key, endpoints[key].point);
    else if (markers[key]) { markers[key].remove(); delete markers[key]; }
  }
  clearRoute();
  if (hasTrip()) calculate();
};
$('locate').onclick = () => {
  if (!navigator.geolocation) { status('This browser cannot share your location.'); return; }
  status('Finding your location…');
  navigator.geolocation.getCurrentPosition(position => {
    const point = [position.coords.longitude, position.coords.latitude];
    if (!inArea(point)) { status(`You seem to be outside the ${CITY.name} area, so your location was not used.`); return; }
    useLocation('start', 'My location', point);
  }, () => status('Location was not shared. Type a place or pick it on the map.'), {enableHighAccuracy: true, timeout: 10000});
};
$('calculate').onclick = async () => {
  for (const key of ['start', 'end']) {
    if (hasLocation(key)) continue;
    if (!$(key).value.trim()) { status(key === 'start' ? 'Add where you start.' : 'Add where you are going.'); $(key).focus(); return; }
    await search(key);
    return;
  }
  calculate(true);
};
$('detour').addEventListener('input', detourLabel);
$('detour').addEventListener('change', () => calculate());
$('detourAuto').addEventListener('change', () => { detourLabel(); calculate(); });
$('time').addEventListener('input', () => { clock(); refreshShade(); });
$('time').addEventListener('change', () => calculate());
$('date').addEventListener('change', () => { refreshShade(); calculate(); });
$('treeShade').addEventListener('change', () => { refreshShade(); calculate(); });
$('pauseToggle').addEventListener('change', updatePause);
$('cityOverview').onclick = () => map && map.fitBounds(cityBounds, {padding: 40, duration: 600});
$('reset').onclick = () => map && fitRoute();
function setUnits(next) {
  units = next;
  try { localStorage.setItem('heatscape-units', next); } catch (e) { /* ignore */ }
  $('unitImperial').setAttribute('aria-pressed', String(next === 'imperial'));
  $('unitMetric').setAttribute('aria-pressed', String(next === 'metric'));
  if (scale) scale.setUnit(next);
  if (result) { renderResults(); if (lastBest) drawBestTime(lastBest); }
}
$('unitImperial').onclick = () => setUnits('imperial');
$('unitMetric').onclick = () => setUnits('metric');
const methods = $('methods');
for (const id of ['about', 'limits']) $(id).onclick = () => methods.showModal();
methods.querySelector('.close').onclick = () => methods.close();

// Season is shared across pages (site.js).
setSeason(window.HeatSeason ? HeatSeason.get() : 'summer', true);
setUnits(units);
document.addEventListener('seasonchange', event => setSeason(event.detail));
loading('stepMap');
})();
