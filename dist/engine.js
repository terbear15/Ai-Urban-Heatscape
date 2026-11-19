/* HeatScape shade engine (one city at a time).
 *
 * Works in a local planar frame (meters). For a sun position it:
 *   1. casts building shadows (footprint + wall quads swept by height / tan(elevation)),
 *   2. optionally casts tree shadows (LiDAR-height crowns, swept the same way),
 *   3. samples every street segment every 10 m and stores the sunlit share (edge.sun),
 *   4. finds the shortest walk and a lower-sun (summer) or sunnier (winter) walk that
 *      only takes local detours within the allowed extra time.
 */
(function (root) {
// Local planar frame, centered on the city data when create() runs.
let origin = [-75.163, 39.9525];
let sx = 111320 * Math.cos(origin[1] * Math.PI / 180);
const sy = 111320;
const xy = p => [(p[0] - origin[0]) * sx, (p[1] - origin[1]) * sy];
const ll = p => [p[0] / sx + origin[0], p[1] / sy + origin[1]];
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const WALK_M_PER_MIN = 80.4672; // 3 mph
const CELL = 40; // spatial index cell size in meters

function contains(p, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i], b = ring[j];
    if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
}

// Convex hull (monotone chain), closed ring.
function hull(points) {
  const pts = points.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [], upper = [];
  for (const p of pts) { while (lower.length >= 2 && cross(lower.at(-2), lower.at(-1), p) <= 0) lower.pop(); lower.push(p); }
  for (const p of pts.reverse()) { while (upper.length >= 2 && cross(upper.at(-2), upper.at(-1), p) <= 0) upper.pop(); upper.push(p); }
  const ring = lower.slice(0, -1).concat(upper.slice(0, -1));
  ring.push(ring[0]);
  return ring;
}

function outerRings(geometry) {
  if (geometry.type === 'Polygon') return [geometry.coordinates[0]];
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.map(polygon => polygon[0]);
  return [];
}

function create(data) {
  if (data.meta && data.meta.bounds) {
    const [w, s, ea, n] = data.meta.bounds;
    origin = [(w + ea) / 2, (s + n) / 2];
    sx = 111320 * Math.cos(origin[1] * Math.PI / 180);
  }
  // ---- walking network ----
  const nodes = new Map();
  // Compact segments are [a, b, lon1, lat1, lon2, lat2].
  const rawEdges = data.edges.map(e => Array.isArray(e) ? {a: String(e[0]), b: String(e[1]), p: [e[2], e[3]], q: [e[4], e[5]]} : e);
  const edges = rawEdges.map((e, id) => {
    for (const [k, p] of [[e.a, e.p], [e.b, e.q]]) if (!nodes.has(k)) nodes.set(k, {p: xy(p), links: []});
    const edge = {...e, id, length: distance(xy(e.p), xy(e.q)), sun: 1};
    nodes.get(e.a).links.push(edge);
    nodes.get(e.b).links.push(edge);
    return edge;
  });
  // Keep the largest connected component so every snapped point can reach every other.
  let largest = new Set();
  const visited = new Set();
  for (const key of nodes.keys()) {
    if (visited.has(key)) continue;
    const component = new Set([key]), queue = [key];
    visited.add(key);
    while (queue.length) {
      const k = queue.pop();
      for (const e of nodes.get(k).links) {
        const other = e.a === k ? e.b : e.a;
        if (!visited.has(other)) { visited.add(other); component.add(other); queue.push(other); }
      }
    }
    if (component.size > largest.size) largest = component;
  }
  const reachable = [...largest];

  // ---- shade sources in the planar frame ----
  const buildings = data.buildings.features.map(f => ({ring: f.geometry.coordinates[0].map(xy), height: f.properties.height}));
  const trees = ((data.trees && data.trees.features) || []).flatMap(f =>
    outerRings(f.geometry).map(ring => ({ring: ring.map(xy), height: f.properties.h ?? f.properties.height_m})));

  let lastShade = null;

  function updateShade(azimuth, altitude, options = {}) {
    const {geometry = false, withTrees = false} = options;
    const bins = new Map(), polys = [];
    const buildingShadows = [], treeShadows = [];
    function add(ring, sink) {
      const index = polys.length;
      polys.push(ring);
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      for (const [x, y] of ring) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      for (let x = Math.floor(x0 / CELL); x <= Math.floor(x1 / CELL); x++)
        for (let y = Math.floor(y0 / CELL); y <= Math.floor(y1 / CELL); y++) {
          const key = x + ',' + y;
          if (!bins.has(key)) bins.set(key, []);
          bins.get(key).push(index);
        }
    }
    const night = altitude <= 0;
    if (!night) {
      // Very low sun gives extremely long shadows; cap them at 400 m.
      const reach = h => Math.min(400, h / Math.tan(Math.max(altitude, .02)));
      // SunCalc azimuth: 0 = sun due south, positive toward west. The sun lies along
      // (-sin, -cos) in (east, north) terms, so shadows fall along (+sin, +cos).
      const dx = Math.sin(azimuth), dy = Math.cos(azimuth);
      const sweep = (source, sink, footprintToo) => {
        for (const {ring, height} of source) {
          const len = reach(height), ox = dx * len, oy = dy * len;
          const moved = ring.map(([x, y]) => [x + ox, y + oy]);
          if (footprintToo) add(ring, null);
          // Exact shadow for scoring: the shifted footprint plus one quad per wall.
          add(moved, null);
          for (let i = 0; i < ring.length - 1; i++) {
            const p = ring[i], q = ring[i + 1];
            add([p, q, moved[i + 1], moved[i], p], null);
          }
          // One polygon per object for drawing: the hull of footprint and shifted footprint.
          if (sink) sink.push({type: 'Feature', properties: {}, geometry: {type: 'Polygon', coordinates: [hull(ring.concat(moved)).map(ll)]}});
        }
      };
      sweep(buildings, geometry ? buildingShadows : null, true);
      if (withTrees) sweep(trees, geometry ? treeShadows : null, true);
    }
    function shaded(p) {
      const list = bins.get(Math.floor(p[0] / CELL) + ',' + Math.floor(p[1] / CELL));
      return Boolean(list && list.some(i => contains(p, polys[i])));
    }
    for (const e of edges) {
      if (night) { e.sun = 0; continue; }
      const p = xy(e.p), q = xy(e.q), n = Math.max(1, Math.ceil(e.length / 10));
      let count = 0;
      for (let i = 0; i < n; i++) {
        const t = (i + .5) / n;
        if (shaded([p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])])) count++;
      }
      e.sun = 1 - count / n;
    }
    lastShade = {azimuth, altitude, withTrees, night};
    return {
      night,
      buildings: {type: 'FeatureCollection', features: buildingShadows},
      trees: {type: 'FeatureCollection', features: treeShadows},
    };
  }

  function snap(coord) {
    const p = xy(coord);
    let best = null, d = Infinity;
    for (const k of reachable) {
      const dd = distance(p, nodes.get(k).p);
      if (dd < d) { d = dd; best = k; }
    }
    return {id: best, meters: d, coord: ll(nodes.get(best).p)};
  }

  // Dijkstra with cost = length × (1 + penalty × badness), badness = sun (summer) or shade (winter).
  function path(start, end, penalty, winter) {
    const costs = new Map([[start, 0]]), previous = new Map(), heap = [];
    const push = item => {
      heap.push(item);
      let i = heap.length - 1;
      while (i) { const p = (i - 1) >> 1; if (heap[p][0] <= item[0]) break; heap[i] = heap[p]; i = p; }
      heap[i] = item;
    };
    const pop = () => {
      const first = heap[0], last = heap.pop();
      if (heap.length) {
        let i = 0;
        while (i * 2 + 1 < heap.length) {
          let c = i * 2 + 1;
          if (c + 1 < heap.length && heap[c + 1][0] < heap[c][0]) c++;
          if (heap[c][0] >= last[0]) break;
          heap[i] = heap[c]; i = c;
        }
        heap[i] = last;
      }
      return first;
    };
    push([0, start]);
    while (heap.length) {
      const [cost, k] = pop();
      if (cost !== costs.get(k)) continue;
      if (k === end) break;
      for (const e of nodes.get(k).links) {
        const next = e.a === k ? e.b : e.a;
        const badness = winter ? 1 - e.sun : e.sun;
        const value = cost + e.length * (1 + penalty * badness);
        if (value < (costs.get(next) ?? Infinity)) { costs.set(next, value); previous.set(next, {k, e}); push([value, next]); }
      }
    }
    if (!costs.has(end)) return null;
    let k = end;
    const segments = [];
    while (k !== start) { const prev = previous.get(k); segments.push(prev.e); k = prev.k; }
    segments.reverse();
    return finish(segments, start);
  }

  function metrics(segments) {
    return {
      length: segments.reduce((sum, e) => sum + e.length, 0),
      exposure: segments.reduce((sum, e) => sum + e.length * e.sun, 0),
    };
  }
  function routeNodes(segments, start) {
    const keys = [start];
    for (const e of segments) keys.push(e.a === keys.at(-1) ? e.b : e.a);
    return keys;
  }
  function finish(segments, start) {
    return {...metrics(segments), segments, coords: routeNodes(segments, start).map(key => ll(nodes.get(key).p))};
  }
  // Lower is better: sun minutes in summer, shade minutes in winter.
  const badness = (m, winter) => winter ? m.length - m.exposure : m.exposure;

  // Accept a candidate's detours one at a time, each only if it stays within the extra-time budget.
  function localDetours(fast, candidate, start, maxExtra, winter) {
    const fastKeys = routeNodes(fast.segments, start);
    const positions = new Map(fastKeys.map((key, index) => [key, index]));
    const joins = routeNodes(candidate.segments, start).flatMap((key, index) => positions.has(key) ? [[positions.get(key), index]] : []);
    const segments = [];
    for (let i = 1; i < joins.length; i++) {
      const [from, altFrom] = joins[i - 1], [to, altTo] = joins[i];
      if (to <= from) return fast;
      const direct = fast.segments.slice(from, to), detour = candidate.segments.slice(altFrom, altTo);
      const base = metrics(direct), alt = metrics(detour);
      segments.push(...(alt.length <= base.length + maxExtra + 1e-6 && badness(alt, winter) < badness(base, winter) - 1e-6 ? detour : direct));
    }
    const result = finish(segments, start);
    return badness(result, winter) >= badness(fast, winter) - 1e-6 ? fast : result;
  }

  function routes(a, b, extraMinutes, winter = false) {
    const start = snap(a), end = snap(b);
    if (start.id === end.id) throw Error('Choose two places farther apart.');
    if (start.meters > 150 || end.meters > 150) throw Error('Choose points on or near a street inside Center City.');
    const fast = path(start.id, end.id, 0, winter);
    if (!fast) throw Error('No connected walking route between these points.');
    let best = fast;
    if (!(lastShade && lastShade.night)) {
      for (const penalty of [.5, 1, 2, 4, 8, 16, 40]) {
        const candidate = path(start.id, end.id, penalty, winter);
        if (!candidate) continue;
        const mixed = localDetours(fast, candidate, start.id, extraMinutes * WALK_M_PER_MIN, winter);
        if (badness(mixed, winter) < badness(best, winter)) best = mixed;
      }
    }
    return {fast, shade: best, start, end};
  }

  return {nodes, edges, updateShade, routes, snap, componentSize: largest.size, treeCount: trees.length, buildingCount: buildings.length};
}

root.HeatEngine = {create, xy, ll, contains, distance, WALK_M_PER_MIN};
if (typeof module !== 'undefined') module.exports = root.HeatEngine;
})(typeof window !== 'undefined' ? window : globalThis);
