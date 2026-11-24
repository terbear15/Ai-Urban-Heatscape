/* HeatScape shade and routing engine (version 2). Runs in a Web Worker or in Node.
 *
 * Planar frame in meters centered on the city data. For a sun position:
 *   - every building and tree crown is swept away from the sun by height / tan(elevation)
 *     (capped at 400 m); the shadow pieces are scan-filled into a sparse 2 m grid;
 *   - each street segment is sampled every 5 m on both sidewalks (offset from the
 *     centerline by the segment's sidewalk distance) and gets the sunlit share per side.
 * Routing: time-dependent Dijkstra. The sun is updated as the walk goes on: shade is
 * computed for 15-minute slots after departure, and each segment uses the slot in which
 * the walker reaches it. On each segment the walker takes the better sidewalk
 * (shadier in summer, sunnier in winter).
 */
(function (root) {
'use strict';
const WALK_M_PER_MIN = 80.4672; // 3 mph
const CELL = 2;                 // shade grid, meters
const BLOCK = 64;               // cells per sparse block side
const SLOT_MIN = 15;            // minutes per sun slot
const SAMPLE_M = 5;

function outerRings(g) {
  if (g.type === 'Polygon') return [g.coordinates[0]];
  if (g.type === 'MultiPolygon') return g.coordinates.map(p => p[0]);
  return [];
}

// Convex hull (monotone chain), closed ring, for drawing one shadow per object.
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

// Boolean shade raster. Dense typed array when the area is compact, otherwise sparse
// 64x64 blocks allocated on first write. Polygons are scan-filled row by row.
class Grid {
  constructor(bounds) {
    const [x0, y0, x1, y1] = bounds;
    this.c0 = Math.floor(x0 / CELL); this.r0 = Math.floor(y0 / CELL);
    this.cols = Math.ceil(x1 / CELL) - this.c0 + 1; this.rows = Math.ceil(y1 / CELL) - this.r0 + 1;
    this.dense = this.cols * this.rows <= 24e6 ? new Uint8Array(this.cols * this.rows) : null;
    this.blocks = this.dense ? null : new Map();
  }
  span(r, ca, cb) {
    if (this.dense) {
      const rr = r - this.r0;
      if (rr < 0 || rr >= this.rows) return;
      const a = Math.max(0, ca - this.c0), b = Math.min(this.cols - 1, cb - this.c0);
      if (a <= b) this.dense.fill(1, rr * this.cols + a, rr * this.cols + b + 1);
      return;
    }
    const br = Math.floor(r / BLOCK), ir = ((r % BLOCK) + BLOCK) % BLOCK;
    for (let c = ca; c <= cb;) {
      const bc = Math.floor(c / BLOCK), end = Math.min(cb, bc * BLOCK + BLOCK - 1);
      const key = br * 1e6 + bc;
      let block = this.blocks.get(key);
      if (!block) { block = new Uint8Array(BLOCK * BLOCK); this.blocks.set(key, block); }
      const base = ir * BLOCK - bc * BLOCK;
      block.fill(1, base + c, base + end + 1);
      c = end + 1;
    }
  }
  fillPolygon(ring) {
    let y0 = Infinity, y1 = -Infinity;
    for (const p of ring) { if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
    const r0 = Math.ceil(y0 / CELL - .5), r1 = Math.floor(y1 / CELL - .5);
    const xs = [];
    for (let r = r0; r <= r1; r++) {
      const y = (r + .5) * CELL;
      xs.length = 0;
      for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const a = ring[i], b = ring[j];
        if ((a[1] > y) !== (b[1] > y)) xs.push(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]));
      }
      if (xs.length === 2) { if (xs[0] > xs[1]) { const t = xs[0]; xs[0] = xs[1]; xs[1] = t; } }
      else xs.sort((p, q) => p - q);
      for (let k = 0; k + 1 < xs.length; k += 2) {
        const ca = Math.ceil(xs[k] / CELL - .5), cb = Math.floor(xs[k + 1] / CELL - .5);
        if (ca <= cb) this.span(r, ca, cb);
      }
    }
  }
  hit(x, y) {
    const r = Math.floor(y / CELL), c = Math.floor(x / CELL);
    if (this.dense) {
      const rr = r - this.r0, cc = c - this.c0;
      return rr >= 0 && cc >= 0 && rr < this.rows && cc < this.cols && this.dense[rr * this.cols + cc] === 1;
    }
    const block = this.blocks.get(Math.floor(r / BLOCK) * 1e6 + Math.floor(c / BLOCK));
    return block ? block[(((r % BLOCK) + BLOCK) % BLOCK) * BLOCK + (((c % BLOCK) + BLOCK) % BLOCK)] === 1 : false;
  }
}

// Picture of the shade for the map: one byte per cell (0 none, 1 tree shadow, 2 building
// shadow, 3 tree crown), drawn as a single image instead of hundreds of thousands of polygons.
class Raster {
  constructor([x0, y0, x1, y1], cell) {
    this.x0 = x0; this.y1 = y1; this.cell = cell;
    this.w = Math.ceil((x1 - x0) / cell); this.h = Math.ceil((y1 - y0) / cell);
    this.data = new Uint8Array(this.w * this.h);
  }
  // Even-odd scanline fill of one or more rings (local metres); writes `value`.
  fill(rings, value) {
    let ya = Infinity, yb = -Infinity;
    for (const ring of rings) for (const p of ring) { if (p[1] < ya) ya = p[1]; if (p[1] > yb) yb = p[1]; }
    const ra = Math.max(0, Math.floor((this.y1 - yb) / this.cell)), rb = Math.min(this.h - 1, Math.ceil((this.y1 - ya) / this.cell));
    const xs = [];
    for (let r = ra; r <= rb; r++) {
      const y = this.y1 - (r + .5) * this.cell;
      xs.length = 0;
      for (const ring of rings) for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
        const a = ring[i], b = ring[j];
        if ((a[1] > y) !== (b[1] > y)) xs.push(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]));
      }
      xs.sort((p, q) => p - q);
      for (let k = 0; k + 1 < xs.length; k += 2) {
        const ca = Math.max(0, Math.ceil((xs[k] - this.x0) / this.cell - .5)), cb = Math.min(this.w - 1, Math.floor((xs[k + 1] - this.x0) / this.cell - .5));
        if (ca <= cb) this.data.fill(value, r * this.w + ca, r * this.w + cb + 1);
      }
    }
  }
}

const ringArea = ring => { let s = 0; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) s += (ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1]); return Math.abs(s / 2); };

// Packed city data (format 3, python/pack_city_data.py) back to the readable form.
function unpack(d) {
  const [ox, oy] = d.origin, q = d.q;
  const rings = (flat, key) => {
    const out = [];
    for (let i = 0; i < flat.length;) {
      const h = flat[i] / 10, n = flat[i + 1], ring = [];
      let x = 0, y = 0;
      for (let k = 0; k < n; k++) { x += flat[i + 2 + 2 * k]; y += flat[i + 3 + 2 * k]; ring.push([ox + x / q, oy + y / q]); }
      ring.push(ring[0]);
      out.push({type: 'Feature', properties: {[key]: h}, geometry: {type: 'Polygon', coordinates: [ring]}});
      i += 2 + 2 * n;
    }
    return {type: 'FeatureCollection', features: out};
  };
  const N = d.nodes, edges = [];
  for (let i = 0; i < d.edges.length; i += 4) {
    const a = d.edges[i], b = d.edges[i + 1];
    edges.push([a, b, ox + N[2 * a] / q, oy + N[2 * a + 1] / q, ox + N[2 * b] / q, oy + N[2 * b + 1] / q, d.edges[i + 2] / 10, d.edges[i + 3]]);
  }
  return {meta: d.meta, names: d.names, pois: d.pois, edges, buildings: rings(d.buildings, 'height'), trees: rings(d.trees, 'h')};
}

function create(data) {
  if (data.v === 3) data = unpack(data);
  const [w0, s0, e0, n0] = data.meta.bounds;
  const origin = [(w0 + e0) / 2, (s0 + n0) / 2];
  const sx = 111320 * Math.cos(origin[1] * Math.PI / 180), sy = 111320;
  const xy = p => [(p[0] - origin[0]) * sx, (p[1] - origin[1]) * sy];
  const ll = p => [p[0] / sx + origin[0], p[1] / sy + origin[1]];
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const names = data.names || [];

  // ---- network ----
  const nodes = new Map();
  const edges = data.edges.map((e, id) => {
    const raw = Array.isArray(e)
      ? {a: String(e[0]), b: String(e[1]), p: [e[2], e[3]], q: [e[4], e[5]], w: e[6] || 0, name: names[e[7]] ?? ''}
      : {a: e.a, b: e.b, p: e.p, q: e.q, w: e.w || 0, name: e.name || ''};
    const P = xy(raw.p), Q = xy(raw.q), length = dist(P, Q);
    for (const [k, p] of [[raw.a, P], [raw.b, Q]]) if (!nodes.has(k)) nodes.set(k, {p, links: []});
    // Unit normal pointing to the left of a -> b.
    const nx = length ? -(Q[1] - P[1]) / length : 0, ny = length ? (Q[0] - P[0]) / length : 0;
    const edge = {id, a: raw.a, b: raw.b, P, Q, length, w: raw.w, name: raw.name, nx, ny};
    nodes.get(raw.a).links.push(edge);
    nodes.get(raw.b).links.push(edge);
    return edge;
  });
  // Largest connected component.
  let largest = new Set();
  const visited = new Set();
  for (const key of nodes.keys()) {
    if (visited.has(key)) continue;
    const component = new Set([key]), stack = [key];
    visited.add(key);
    while (stack.length) {
      const k = stack.pop();
      for (const e of nodes.get(k).links) {
        const o = e.a === k ? e.b : e.a;
        if (!visited.has(o)) { visited.add(o); component.add(o); stack.push(o); }
      }
    }
    if (component.size > largest.size) largest = component;
  }
  const reachable = [...largest];
  // Spatial index of reachable nodes for snapping (100 m cells).
  const nodeCells = new Map();
  for (const k of reachable) {
    const p = nodes.get(k).p, key = Math.floor(p[0] / 100) + ',' + Math.floor(p[1] / 100);
    if (!nodeCells.has(key)) nodeCells.set(key, []);
    nodeCells.get(key).push(k);
  }

  // ---- shade sources ----
  // Near-convex objects (area >= 92% of their hull) are swept as one hull: the same shadow, one fill.
  const prep = (ring, h, forceHull) => {
    const convex = forceHull || ringArea(ring) >= .92 * ringArea(hull(ring));
    return {ring, h, convex};
  };
  const buildings = data.buildings.features.map(f => prep(f.geometry.coordinates[0].map(xy), f.properties.height, false));
  const trees = ((data.trees && data.trees.features) || []).flatMap(f =>
    outerRings(f.geometry).map(ring => prep(ring.map(xy), f.properties.h ?? f.properties.height_m, true)));
  let bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
  for (const {ring} of buildings.concat(trees)) for (const [x, y] of ring) { if (x < bx0) bx0 = x; if (y < by0) by0 = y; if (x > bx1) bx1 = x; if (y > by1) by1 = y; }
  for (const e of edges) for (const [x, y] of [e.P, e.Q]) { if (x < bx0) bx0 = x; if (y < by0) by0 = y; if (x > bx1) bx1 = x; if (y > by1) by1 = y; }
  const gridBounds = [bx0 - 450, by0 - 450, bx1 + 450, by1 + 450];

  // ---- shade for one sun position ----
  function shadeSlot(sun, withTrees, wantGeometry) {
    const n = edges.length;
    const left = new Float32Array(n), right = new Float32Array(n);
    const asRaster = wantGeometry === 'raster' && display;
    const picture = asRaster ? new Raster(display.frame, display.cell) : null;
    const geometry = wantGeometry && !asRaster ? {buildings: [], trees: []} : null;
    if (sun.altitude <= 0) return {left, right, night: true, geometry: asRaster ? finishRaster(picture, false) : geometry};
    const grid = new Grid(gridBounds);
    const reach = h => Math.min(400, h / Math.tan(Math.max(sun.altitude, .02)));
    const dx = Math.sin(sun.azimuth), dy = Math.cos(sun.azimuth); // SunCalc: shadows fall along (+sin, +cos)
    const sweep = (list, sink) => {
      for (const {ring, h, convex} of list) {
        const len = reach(h), ox = dx * len, oy = dy * len;
        const moved = ring.map(([x, y]) => [x + ox, y + oy]);
        const swept = hull(ring.concat(moved));
        if (convex) grid.fillPolygon(swept);
        else {
          grid.fillPolygon(ring);
          grid.fillPolygon(moved);
          for (let i = 0; i < ring.length - 1; i++) grid.fillPolygon([ring[i], ring[i + 1], moved[i + 1], moved[i], ring[i]]);
        }
        if (sink) sink.push({type: 'Feature', properties: {}, geometry: {type: 'Polygon', coordinates: [swept.map(ll)]}});
        if (picture && inFrame(swept)) picture.fill([swept], paint);
      }
    };
    let paint = 1;
    if (withTrees) sweep(trees, geometry && geometry.trees);
    paint = 2;
    sweep(buildings, geometry && geometry.buildings);
    for (const e of edges) {
      const k = Math.max(1, Math.ceil(e.length / SAMPLE_M));
      let sl = 0, sr = 0;
      for (let i = 0; i < k; i++) {
        const t = (i + .5) / k;
        const x = e.P[0] + t * (e.Q[0] - e.P[0]), y = e.P[1] + t * (e.Q[1] - e.P[1]);
        if (!grid.hit(x + e.nx * e.w, y + e.ny * e.w)) sl++;
        if (!grid.hit(x - e.nx * e.w, y - e.ny * e.w)) sr++;
      }
      left[e.id] = sl / k;
      right[e.id] = sr / k;
    }
    return {left, right, night: false, geometry: asRaster ? finishRaster(picture, true) : geometry};
  }

  // ---- map picture (set once per city with the area to show) ----
  let display = null;
  const inFrame = ring => {
    const [x0, y0, x1, y1] = display.frame;
    for (const [x, y] of ring) if (x >= x0 && x <= x1 && y >= y0 && y <= y1) return true;
    return false;
  };
  function setDisplayArea(polygons) {
    // polygons: [[outerRing, ...holes], ...] in lon/lat
    const rings = polygons.flat().map(r => r.map(([lon, lat]) => xy([lon, lat])));
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const r of rings) for (const [x, y] of r) { if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y; }
    const cell = Math.max(2, Math.ceil(Math.max(x1 - x0, y1 - y0) / 4000));  // at most 4000 px: phone GPU limit
    const frame = [x0 - cell, y0 - cell, x1 + cell, y1 + cell];
    const mask = new Raster(frame, cell);
    mask.fill(rings, 1);
    display = {frame, cell};
    const crowns = new Raster(frame, cell);
    for (const t of trees) if (inFrame(t.ring)) crowns.fill([t.ring], 1);
    Object.assign(display, {mask: mask.data, crowns: crowns.data});
    const [w, n] = ll([frame[0], frame[3]]), [e, s] = ll([frame[2], frame[1]]);
    display.corners = [[w, n], [e, n], [e, s], [w, s]];
    display.w = mask.w; display.h = mask.h;
    return {width: mask.w, height: mask.h, cell};
  }
  function finishRaster(picture, day) {
    const {mask, crowns} = display, data = picture.data;
    for (let i = 0; i < data.length; i++) {
      if (!mask[i]) data[i] = 0;
      else if (crowns[i]) data[i] = 3;
      else if (!day) data[i] = 0;
    }
    return {raster: {width: picture.w, height: picture.h, data, corners: display.corners}};
  }

  // ---- routing ----
  function snap(coord) {
    const p = xy(coord), cx = Math.floor(p[0] / 100), cy = Math.floor(p[1] / 100);
    let best = null, d = Infinity;
    for (let r = 0; r <= 6 && (best === null || r <= 2); r++) {
      for (let i = cx - r; i <= cx + r; i++) for (let j = cy - r; j <= cy + r; j++) {
        if (Math.max(Math.abs(i - cx), Math.abs(j - cy)) !== r) continue;
        for (const k of nodeCells.get(i + ',' + j) || []) {
          const dd = dist(p, nodes.get(k).p);
          if (dd < d) { d = dd; best = k; }
        }
      }
    }
    if (best === null) return null;
    return {id: best, meters: d, coord: ll(nodes.get(best).p)};
  }

  // Sun share on an edge in a slot, taking the better sidewalk for the season.
  const sideSun = (slot, e, winter) => {
    const l = slot.left[e.id], r = slot.right[e.id];
    return winter ? Math.max(l, r) : Math.min(l, r);
  };
  // `slots` is a function: slot index -> shade for that 15-minute slot (computed lazily by the caller).
const slotFor = (slots, meters) => slots(Math.min(7, Math.floor(meters / WALK_M_PER_MIN / SLOT_MIN)));

  function path(start, end, slots, penalty, winter) {
    const cost = new Map([[start, 0]]), walked = new Map([[start, 0]]), prev = new Map(), heap = [[0, start]];
    const push = item => {
      heap.push(item);
      let i = heap.length - 1;
      while (i) { const p = (i - 1) >> 1; if (heap[p][0] <= item[0]) break; heap[i] = heap[p]; i = p; }
      heap[i] = item;
    };
    const pop = () => {
      const top = heap[0], last = heap.pop();
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
      return top;
    };
    while (heap.length) {
      const [c, k] = pop();
      if (c !== cost.get(k)) continue;
      if (k === end) break;
      const m = walked.get(k);
      const slot = slotFor(slots, m);
      for (const e of nodes.get(k).links) {
        const o = e.a === k ? e.b : e.a;
        const sun = sideSun(slot, e, winter);
        const bad = winter ? 1 - sun : sun;
        const value = c + e.length * (1 + penalty * bad);
        if (value < (cost.get(o) ?? Infinity)) {
          cost.set(o, value); walked.set(o, m + e.length); prev.set(o, {k, e}); push([value, o]);
        }
      }
    }
    if (!cost.has(end)) return null;
    const segments = [];
    for (let k = end; k !== start;) { const p = prev.get(k); segments.push(p.e); k = p.k; }
    return segments.reverse();
  }

  function describe(segments, start, slots, winter) {
    let meters = 0, sunM = 0;
    const keys = [start], parts = [];
    for (const e of segments) {
      const from = keys.at(-1), forward = e.a === from;
      keys.push(forward ? e.b : e.a);
      const slot = slotFor(slots, meters);
      const l = slot.left[e.id], r = slot.right[e.id];
      const useLeft = winter ? l >= r : l <= r;
      const sun = useLeft ? l : r;
      // Compass side of the sidewalk used, relative to the walking direction.
      let nx = useLeft ? e.nx : -e.nx, ny = useLeft ? e.ny : -e.ny;
      const side = e.w > 0 ? (Math.abs(nx) > Math.abs(ny) ? (nx > 0 ? 'east' : 'west') : (ny > 0 ? 'north' : 'south')) : '';
      parts.push({name: e.name, length: e.length, sun, side,
                  coords: [ll(nodes.get(from).p), ll(nodes.get(keys.at(-1)).p)]});
      meters += e.length;
      sunM += e.length * sun;
    }
    return {length: meters, exposure: sunM, minutes: meters / WALK_M_PER_MIN, sunMinutes: sunM / WALK_M_PER_MIN,
            coords: keys.map(k => ll(nodes.get(k).p)), parts, segments};
  }

  // Lower is better: sun meters in summer, shade meters in winter.
  const badness = (r, winter) => winter ? r.length - r.exposure : r.exposure;

  // Replace parts of the shortest walk with a candidate's detours, each only if it helps
  // and the total extra length stays within the budget.
  function blend(fast, candidate, start, slots, winter, budget) {
    const fastKeys = [start];
    for (const e of fast.segments) fastKeys.push(e.a === fastKeys.at(-1) ? e.b : e.a);
    const candKeys = [start];
    for (const e of candidate) candKeys.push(e.a === candKeys.at(-1) ? e.b : e.a);
    const pos = new Map(fastKeys.map((k, i) => [k, i]));
    const joins = candKeys.flatMap((k, i) => pos.has(k) ? [[pos.get(k), i]] : []);
    const out = [];
    let extra = 0;
    for (let i = 1; i < joins.length; i++) {
      const [f0, c0] = joins[i - 1], [f1, c1] = joins[i];
      if (f1 <= f0) return fast.segments;
      const direct = fast.segments.slice(f0, f1), detour = candidate.slice(c0, c1);
      const dl = direct.reduce((s, e) => s + e.length, 0), cl = detour.reduce((s, e) => s + e.length, 0);
      const before = describe(out.concat(direct), start, slots, winter), after = describe(out.concat(detour), start, slots, winter);
      if (extra + cl - dl <= budget + 1e-6 && badness(after, winter) < badness(before, winter) - 1e-6) {
        out.push(...detour); extra += cl - dl;
      } else out.push(...direct);
    }
    return out;
  }

  /* Three routes: shortest, balanced (at most ~1 min extra or half the budget) and best
     (most shade in summer, most sun in winter) within the extra-time budget. */
  function routes(a, b, slots, extraMinutes, winter) {
    const start = snap(a), end = snap(b);
    if (!start || !end) throw Error('Choose points on or near a street inside the dashed boundary.');
    if (start.id === end.id) throw Error('Choose two places farther apart.');
    if (start.meters > 150 || end.meters > 150) throw Error('Choose points on or near a street inside the dashed boundary.');
    const fastSegs = path(start.id, end.id, slots, 0, winter);
    if (!fastSegs) throw Error('No connected walking route between these points.');
    const fast = describe(fastSegs, start.id, slots, winter);
    const budget = extraMinutes * WALK_M_PER_MIN;
    const midBudget = Math.min(WALK_M_PER_MIN, budget / 2);
    let best = fast, mid = fast;
    if (!slots(0).night) {
      for (const penalty of [.5, 1, 2, 4, 8, 16, 40]) {
        const cand = path(start.id, end.id, slots, penalty, winter);
        if (!cand) continue;
        for (const [limit, keep] of [[budget, 'best'], [midBudget, 'mid']]) {
          const mixed = describe(blend(fast, cand, start.id, slots, winter, limit), start.id, slots, winter);
          if (keep === 'best' && badness(mixed, winter) < badness(best, winter)) best = mixed;
          if (keep === 'mid' && badness(mixed, winter) < badness(mid, winter)) mid = mixed;
        }
      }
    }
    const strip = r => ({length: r.length, exposure: r.exposure, minutes: r.minutes, sunMinutes: r.sunMinutes, coords: r.coords, parts: r.parts});
    const same = (x, y) => x.segments.length === y.segments.length && x.segments.every((e, i) => e === y.segments[i]);
    return {fast: strip(fast), best: strip(best), mid: same(mid, best) || same(mid, fast) ? null : strip(mid),
            start, end, segmentIds: {fast: fast.segments.map(e => e.id), best: best.segments.map(e => e.id)}};
  }

  // Sun minutes along fixed routes for each slot (best departure time).
  function exposureOf(segmentIds, slot, winter) {
    let s = 0;
    for (const id of segmentIds) { const e = edges[id]; s += e.length * sideSun(slot, e, winter); }
    return s / WALK_M_PER_MIN;
  }

  return {shadeSlot, routes, snap, exposureOf, edges, componentSize: largest.size,
          treeCount: trees.length, buildingCount: buildings.length, ll, xy, setDisplayArea};
}

root.HeatEngine = {create, unpack, WALK_M_PER_MIN, SLOT_MIN, hull, Grid};
if (typeof module !== 'undefined') module.exports = root.HeatEngine;
})(typeof self !== 'undefined' ? self : (typeof window !== 'undefined' ? window : globalThis));
