/* Background thread for the shade map: loads the city data, computes shade for sun
 * positions (cached) and routes, so the page never freezes while it works.
 *
 * Messages in:  {type:'init', slug, version}
 *               {type:'shade', id, time, lat, lon, trees}              -> shadow geometry for the map
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

self.onmessage = ({data: msg}) => {
  try {
    if (msg.type === 'init') {
      importScripts('vendor/suncalc.js', 'engine.js?' + msg.version, 'data/' + msg.slug + '.js?' + msg.version);
      engine = HeatEngine.create(CITYDATA);
      self.postMessage({type: 'ready', stats: {
        buildings: engine.buildingCount, trees: engine.treeCount, segments: engine.edges.length,
        component: engine.componentSize, meta: CITYDATA.meta, pois: CITYDATA.pois || [],
      }});
      CITYDATA.buildings = CITYDATA.trees = null; // engine has its own copies
    } else if (msg.type === 'shade') {
      const s = slot(msg.time, msg.lat, msg.lon, msg.trees, true);
      self.postMessage({type: 'shade', id: msg.id, night: s.night, geometry: s.geometry});
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
