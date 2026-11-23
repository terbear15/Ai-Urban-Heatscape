/* Background thread for the shade map: loads the city data, computes shade for sun
 * positions (cached) and routes, so the page never freezes while it works.
 *
 * Messages in:  {type:'init', slug, version}
 *               {type:'shade', id, time, lat, lon, trees, colors}      -> PNG of shadows and crowns for the map
 *               {type:'route', id, a, b, time, lat, lon, trees, extra, winter}
 *               {type:'besttime', id, segments:{fast,best}, times:[...], lat, lon, trees, winter}
 * Messages out: {type:'ready'|'shade'|'route'|'besttime'|'error', id, ...}
 * Times are epoch milliseconds.
 */
/* global importScripts, HeatEngine, SunCalc, CITYDATA */
// suncalc.js and the data files attach to `window`, which a worker does not have.
self.window = self;
let engine = null;
const cache = new Map(); // `${minute}|${trees}` -> slot

const SLOT_MS = 15 * 60 * 1000;

function slot(time, lat, lon, trees, geometry) {
  const minute = Math.round(time / 60000);
  const key = minute + '|' + trees;
  let value = cache.get(key);
  if (!value || (geometry && !value.geometry)) {
    value = engine.shadeSlot(SunCalc.getPosition(new Date(time), lat, lon), trees, geometry);
    cache.set(key, value);
    if (cache.size > 48) cache.delete(cache.keys().next().value);
  }
  return value;
}

// Slots after departure, computed only when a route reaches them.
const slotsFrom = (time, lat, lon, trees) => i => slot(time + i * SLOT_MS, lat, lon, trees, false);

// While idle, compute the next slots after the shown time so a route request is quick.
let prefetch = null;
function schedulePrefetch(time, lat, lon, trees) {
  clearTimeout(prefetch);
  let i = 1;
  const step = () => {
    if (i > 3) return;
    slot(time + i++ * SLOT_MS, lat, lon, trees, false);
    prefetch = setTimeout(step, 0);
  };
  prefetch = setTimeout(step, 30);
}

let areaRings = null;
function loadArea(slug) {
  if (areaRings) return areaRings;
  try {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', 'cities/' + slug + '.geojson', false);
    xhr.send();
    const land = JSON.parse(xhr.responseText).features.find(f => f.properties.layer === 'land').geometry;
    areaRings = land.type === 'Polygon' ? [land.coordinates] : land.coordinates;
  } catch (e) { areaRings = []; }
  return areaRings;
}
function inRing(x, y, ring) {
  let hit = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[j];
    if ((y1 > y) !== (y2 > y) && x < (x2 - x1) * (y - y1) / (y2 - y1) + x1) hit = !hit;
  }
  return hit;
}
function inside(collection, slug) {
  const polys = loadArea(slug);
  if (!collection || !polys.length) return collection || {type: 'FeatureCollection', features: []};
  const features = collection.features.filter(f => {
    const ring = f.geometry.coordinates[0];
    let x = 0, y = 0;
    for (let i = 0; i < ring.length - 1; i++) { x += ring[i][0]; y += ring[i][1]; }
    x /= ring.length - 1; y /= ring.length - 1;
    return polys.some(([outer, ...holes]) => inRing(x, y, outer) && !holes.some(h => inRing(x, y, h)));
  });
  return {type: 'FeatureCollection', features};
}

// Shadows are convex (each is a hull), so the part inside the area is the area ring
// clipped by the shadow (Sutherland-Hodgman with the convex shadow as the clipper).
function clipToConvex(subject, clip) {
  let area2 = 0;
  for (let i = 0; i < clip.length - 1; i++) area2 += clip[i][0] * clip[i + 1][1] - clip[i + 1][0] * clip[i][1];
  const sign = area2 >= 0 ? 1 : -1;
  const side = (a, b, p) => sign * ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) >= 0;
  const cross = (p, q, a, b) => {
    const x1 = p[0], y1 = p[1], x2 = q[0], y2 = q[1], x3 = a[0], y3 = a[1], x4 = b[0], y4 = b[1];
    const d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4) || 1e-15;
    const t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d;
    return [x1 + t * (x2 - x1), y1 + t * (y2 - y1)];
  };
  let out = subject.slice(0, -1);
  for (let i = 0; i < clip.length - 1 && out.length; i++) {
    const a = clip[i], b = clip[i + 1], input = out;
    out = [];
    for (let j = 0; j < input.length; j++) {
      const p = input[j], q = input[(j + 1) % input.length];
      const pin = side(a, b, p), qin = side(a, b, q);
      if (pin) out.push(p);
      if (pin !== qin) out.push(cross(p, q, a, b));
    }
  }
  return out.length >= 3 ? [...out, out[0]] : null;
}
function clipShadows(features, slug) {
  const polys = loadArea(slug);
  if (!polys.length) return features;
  const inArea = ([x, y]) => polys.some(([outer, ...holes]) => inRing(x, y, outer) && !holes.some(h => inRing(x, y, h)));
  const out = [];
  for (const f of features) {
    const ring = f.geometry.coordinates[0];
    const flags = ring.slice(0, -1).map(inArea);
    if (flags.every(Boolean)) { out.push(f); continue; }
    for (const [outer] of polys) {
      const piece = clipToConvex(outer, ring);
      if (piece) out.push({type: 'Feature', properties: {}, geometry: {type: 'Polygon', coordinates: [piece]}});
    }
  }
  return out;
}
let citySlug = '';

self.onmessage = ({data: msg}) => {
  try {
    if (msg.type === 'init') {
      citySlug = msg.slug;
      importScripts('vendor/suncalc.js', 'engine.js?' + msg.version, 'data/' + msg.slug + '.js?' + msg.version);
      const data = CITYDATA.v === 3 ? HeatEngine.unpack(CITYDATA) : CITYDATA;
      engine = HeatEngine.create(data);
      engine.setDisplayArea(loadArea(msg.slug));
      self.postMessage({type: 'ready', stats: {
        buildings: engine.buildingCount, trees: engine.treeCount, segments: engine.edges.length,
        component: engine.componentSize, meta: CITYDATA.meta, pois: CITYDATA.pois || [],
      }});
      // Map layers come from the same download: buildings and crowns inside the area only
      // (the data reaches 150 m further so edge streets get the right shade).
      self.postMessage({type: 'layers', buildings: inside(data.buildings, msg.slug)});
      CITYDATA.buildings = CITYDATA.trees = data.buildings = data.trees = null; // engine has its own copies
    } else if (msg.type === 'shade') {
      const s = slot(msg.time, msg.lat, msg.lon, msg.trees, 'raster');
      const r = s.geometry.raster, rgba = new Uint8ClampedArray(r.width * r.height * 4);
      const palette = [null, msg.colors[1], msg.colors[2], msg.colors[3]];
      for (let i = 0; i < r.data.length; i++) {
        const c = palette[r.data[i]];
        if (c) { const k = i * 4; rgba[k] = c[0]; rgba[k + 1] = c[1]; rgba[k + 2] = c[2]; rgba[k + 3] = c[3]; }
      }
      const canvas = new OffscreenCanvas(r.width, r.height);
      canvas.getContext('2d').putImageData(new ImageData(rgba, r.width, r.height), 0, 0);
      s.geometry = null; // keep the shade numbers cached, not the 12 MB picture
      const id = msg.id, night = s.night;
      canvas.convertToBlob({type: 'image/png'}).then(image => self.postMessage({type: 'shade', id, night, image, corners: r.corners}));
      schedulePrefetch(msg.time, msg.lat, msg.lon, msg.trees);
    } else if (msg.type === 'route') {
      const result = engine.routes(msg.a, msg.b, slotsFrom(msg.time, msg.lat, msg.lon, msg.trees), msg.extra, msg.winter);
      self.postMessage({type: 'route', id: msg.id, result});
    } else if (msg.type === 'besttime') {
      const out = msg.times.map(time => {
        const s = slot(time, msg.lat, msg.lon, msg.trees, false);
        return {time, night: s.night,
                fast: engine.exposureOf(msg.segments.fast, s, msg.winter),
                best: engine.exposureOf(msg.segments.best, s, msg.winter)};
      });
      self.postMessage({type: 'besttime', id: msg.id, hours: out});
    }
  } catch (error) {
    self.postMessage({type: 'error', id: msg.id, message: error.message || String(error), during: msg.type});
  }
};
