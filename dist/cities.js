'use strict';

const el = id => document.getElementById(id);
const endpoints = {start: null, end: null};
const markers = {};
const empty = {type: 'FeatureCollection', features: []};
let map, view, land, picking, generation = 0, routeRequest;
let lastRouteRequest = 0;

async function json(url, signal) {
  const response = await fetch(url, {signal: signal ?? AbortSignal.timeout(15000)});
  if (!response.ok) throw new Error('The map service is busy. Please try again.');
  return response.json();
}

function inRing([x, y], ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [ax, ay] = ring[i], [bx, by] = ring[j];
    if ((ay > y) !== (by > y) && x < (bx - ax) * (y - ay) / (by - ay) + ax) inside = !inside;
  }
  return inside;
}

function onLand(point) {
  const polygons = land.type === 'Polygon' ? [land.coordinates] : land.coordinates;
  return polygons.some(([outline, ...holes]) => inRing(point, outline) && !holes.some(hole => inRing(point, hole)));
}

function clearRoute() {
  generation++;
  routeRequest?.abort();
  el('calculate').disabled = false;
  map.getSource('walk-route').setData(empty);
  el('results').replaceChildren();
}

function choose(key, label, point) {
  if (!onLand(point)) {
    el('status').textContent = 'Choose a point on land inside the highlighted area.';
    return;
  }
  clearRoute();
  endpoints[key] = point;
  el(key).value = label;
  el(key + '-matches').hidden = true;
  if (!markers[key]) {
    const pin = document.createElement('div');
    pin.className = key === 'end' ? 'marker end' : 'marker';
    pin.textContent = key === 'start' ? 'A' : 'B';
    markers[key] = new maplibregl.Marker({element: pin}).setLngLat(point).addTo(map);
  } else markers[key].setLngLat(point);
  el('status').textContent = endpoints.start && endpoints.end ? 'Ready to find a walking route.' :
    key === 'start' ? 'Choose a destination.' : 'Choose a starting point.';
}

async function lookup(key) {
  const field = el(key), list = el(key + '-matches'), button = el(key + '-search');
  const query = field.value.trim();
  if (query.length < 3 || button.disabled) return;
  button.disabled = true;
  list.hidden = true;
  el('status').textContent = 'Searching within ' + view.name + '…';
  try {
    const url = new URL('https://photon.komoot.io/api/');
    url.search = new URLSearchParams({q: query, bbox: view.bounds.flat().join(','), limit: '12'});
    const data = await json(url);
    if (field.value.trim() !== query || endpoints[key]) return;
    const matches = data.features.filter(f => f.geometry?.type === 'Point' && onLand(f.geometry.coordinates));
    list.replaceChildren();
    for (const match of matches.slice(0, 8)) {
      const p = match.properties;
      const street = [p.housenumber, p.street].filter(Boolean).join(' ');
      const label = [...new Set([p.name, street, p.city].filter(Boolean))].join(' · ') || query;
      const option = document.createElement('button');
      option.type = 'button';
      option.textContent = label;
      option.onclick = () => choose(key, label, match.geometry.coordinates);
      list.append(option);
    }
    list.hidden = !matches.length;
    el('status').textContent = matches.length ? 'Choose a search result.' :
      'No matches inside the map area. Try another address or pick a point on the map.';
  } catch (error) {
    if (field.value.trim() === query) el('status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function walk(event) {
  event.preventDefault();
  for (const key of ['start', 'end']) {
    if (!endpoints[key]) {
      if (el(key).value.trim().length >= 3) await lookup(key);
      else {
        el(key).focus();
        el('status').textContent = 'Search for an address or pick a point on the map.';
      }
      return;
    }
  }
  if (Date.now() - lastRouteRequest < 1100) return;
  clearRoute();
  const version = generation;
  routeRequest = new AbortController();
  const request = routeRequest;
  const timeout = setTimeout(() => request.abort(), 15000);
  lastRouteRequest = Date.now();
  el('calculate').disabled = true;
  el('status').textContent = 'Finding a walking route…';
  try {
    const coords = [endpoints.start, endpoints.end].map(p => p.join(',')).join(';');
    const url = 'https://routing.openstreetmap.de/routed-foot/route/v1/driving/' + coords +
      '?steps=true&overview=full&geometries=geojson&radiuses=80;80';
    const data = await json(url, request.signal);
    if (version !== generation) return;
    const route = data.routes?.[0];
    if (!route || route.distance <= 0 || !route.legs.every(leg =>
      leg.steps.length > 0 && leg.steps.every(step => step.mode === 'walking'))) {
      throw new Error('No continuous walking route found. Choose points near connected sidewalks or paths.');
    }
    map.getSource('walk-route').setData({type: 'Feature', properties: {}, geometry: route.geometry});
    const result = document.createElement('p');
    result.className = 'route-card direct';
    result.textContent = `Walking route · ${Math.ceil(route.duration / 60)} min · ${(route.distance / 1609.344).toFixed(2)} mi`;
    el('results').append(result);
    el('status').textContent = 'Walking estimate from OpenStreetMap paths.';
    const bounds = new maplibregl.LngLatBounds();
    for (const point of route.geometry.coordinates) bounds.extend(point);
    map.fitBounds(bounds, {padding: 55, maxZoom: 16, duration: 500});
  } catch (error) {
    if (version === generation) el('status').textContent = error.name === 'AbortError' ?
      'Routing took too long. Try again.' : error.message;
  } finally {
    clearTimeout(timeout);
    if (version === generation) el('calculate').disabled = false;
  }
}

async function init() {
  const views = await json('cities/views.json');
  const select = el('city');
  const requested = new URLSearchParams(location.search).get('city');
  const key = Object.hasOwn(views, requested) ? requested : 'new-york';
  view = views[key];
  select.append(new Option('Philadelphia', 'philadelphia'));
  for (const [slug, city] of Object.entries(views)) select.append(new Option(city.name, slug));
  select.value = key;
  select.onchange = () => {
    location.href = select.value === 'philadelphia' ? './' : '?city=' + select.value;
  };
  document.title = 'HeatScape · ' + view.name;
  el('city-name').textContent = view.custom ? 'Los Angeles area' : view.name;
  el('coverage').textContent = (view.custom ?
    'Study area includes Santa Monica, Pasadena and Inglewood. ' : '') +
    'Walking routes are available. Shade and seasonal comparisons are available in Philadelphia.';
  const geometry = await json('cities/' + key + '.geojson');
  land = geometry.features.find(f => f.properties.layer === 'land').geometry;
  map = new maplibregl.Map({
    container: 'map', bounds: view.bounds, fitBoundsOptions: {padding: 38},
    maxBounds: view.limit, renderWorldCopies: false,
    maxZoom: 19, maxPitch: 0, dragRotate: false, pitchWithRotate: false,
    style: {
      version: 8,
      sources: {
        satellite: {
          type: 'raster', tileSize: 256, maxzoom: 19,
          tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
          attribution: 'Imagery © Esri and contributors · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        },
        area: {type: 'geojson', data: geometry, tolerance: 0},
        'walk-route': {type: 'geojson', data: empty},
      },
      layers: [
        {id: 'satellite', source: 'satellite', type: 'raster'},
        {id: 'outside', source: 'area', type: 'fill', filter: ['==', ['get', 'layer'], 'mask'],
          paint: {'fill-color': '#fff', 'fill-opacity': .36, 'fill-antialias': false}},
        {id: 'outline', source: 'area', type: 'line', filter: ['==', ['get', 'layer'], 'land'],
          paint: {'line-color': '#fff', 'line-width': 1.8}},
        {id: 'walk-halo', source: 'walk-route', type: 'line', paint: {'line-color': '#172c23', 'line-width': 8}},
        {id: 'walk', source: 'walk-route', type: 'line', paint: {'line-color': '#8bd5a6', 'line-width': 5}},
      ],
    },
  });
  map.addControl(new maplibregl.NavigationControl({showCompass: false}));
  map.addControl(new maplibregl.ScaleControl({unit: 'imperial'}), 'bottom-right');
  map.on('load', () => {
    el('overview').onclick = () => map.fitBounds(view.bounds, {padding: 38, duration: 500});
    map.on('click', event => {
      if (!picking) return;
      const point = [event.lngLat.lng, event.lngLat.lat];
      if (!onLand(point)) {
        el('status').textContent = 'Choose a point on land inside the highlighted area.';
        return;
      }
      choose(picking, 'Map pin · ' + point[1].toFixed(5) + ', ' + point[0].toFixed(5), point);
      picking = null;
      map.getCanvas().style.cursor = '';
      for (const key of ['start', 'end']) el('pick-' + key).setAttribute('aria-pressed', 'false');
    });
    for (const key of ['start', 'end']) {
      el('pick-' + key).onclick = () => {
        picking = picking === key ? null : key;
        for (const name of ['start', 'end']) el('pick-' + name).setAttribute('aria-pressed', String(picking === name));
        map.getCanvas().style.cursor = picking ? 'crosshair' : '';
        el('status').textContent = picking ? 'Click a point on land to set the ' + key + '.' : 'Map selection canceled.';
      };
      el(key + '-search').onclick = () => lookup(key);
      el(key).oninput = () => {
        endpoints[key] = null;
        markers[key]?.remove();
        delete markers[key];
        el(key + '-matches').hidden = true;
        clearRoute();
      };
      el(key).onkeydown = event => {
        if (event.key === 'Enter') {
          event.preventDefault();
          if (endpoints[key]) el('walk').requestSubmit();
          else lookup(key);
        }
      };
    }
    el('walk').onsubmit = walk;
    el('calculate').disabled = false;
    el('status').textContent = 'Search for an address or pick both points on the map.';
  });
}

el('calculate').disabled = true;
el('walk').onsubmit = event => event.preventDefault();
init().catch(error => {el('status').textContent = error.message;});
