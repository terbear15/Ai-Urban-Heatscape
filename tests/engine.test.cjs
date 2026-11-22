// Engine checks on a synthetic 5x5 street grid (100 m blocks) with one tall building.
// Run: node tests/engine.test.cjs
const assert = require('assert');
const Engine = require('../dist/engine.js');

const LAT = 39.95, LON = -75.16, SX = 111320 * Math.cos(LAT * Math.PI / 180), SY = 111320;
const ll = (x, y) => [LON + x / SX, LAT + y / SY];
const id = (i, j) => `${i}-${j}`;
const edges = [];
for (let i = 0; i <= 4; i++) for (let j = 0; j <= 4; j++) {
  const [x, y] = [i * 100, j * 100];
  if (i < 4) edges.push([id(i, j), id(i + 1, j), ...ll(x, y), ...ll(x + 100, y), 6, 0]);
  if (j < 4) edges.push([id(i, j), id(i, j + 1), ...ll(x, y), ...ll(x, y + 100), 6, 0]);
}
// A 60 m tower filling the block between x 110-190, y 210-290 (north of street y=200).
const ring = [[110, 210], [190, 210], [190, 290], [110, 290], [110, 210]].map(p => ll(...p));
const data = {
  meta: {bounds: [...ll(-50, -50), ...ll(450, 450)]},
  names: ['Test St'],
  edges,
  buildings: {type: 'FeatureCollection', features: [{type: 'Feature', properties: {height: 60}, geometry: {type: 'Polygon', coordinates: [ring]}}]},
  trees: {type: 'FeatureCollection', features: []},
};
const engine = Engine.create(data);
let passed = 0;
const test = (name, fn) => { fn(); passed++; console.log('ok -', name); };

// SunCalc azimuth: 0 = south, positive toward west. A sun in the south casts shadows north.
const southSun = {altitude: 30 * Math.PI / 180, azimuth: 0};
const northSun = {altitude: 30 * Math.PI / 180, azimuth: Math.PI};

test('graph is one connected component', () => assert.strictEqual(engine.componentSize, 25));
test('night is fully dark, no sun', () => {
  const s = engine.shadeSlot({altitude: -0.1, azimuth: 0}, true, false);
  assert.ok(s.night);
});
const street = edges.findIndex(e => e[0] === id(1, 3) && e[1] === id(2, 3)); // y = 300, north of the tower
const southStreet = edges.findIndex(e => e[0] === id(1, 2) && e[1] === id(2, 2)); // y = 200, south of the tower
const sunOn = (s, i) => Math.min(s.left[i], s.right[i]);
test('a southern sun shades the street north of the tower', () => {
  const s = engine.shadeSlot(southSun, true, false);
  assert.ok(sunOn(s, street) < 0.5, 'street north of the tower should be mostly shaded: ' + sunOn(s, street));
  assert.ok(Math.max(s.left[southStreet], s.right[southStreet]) > 0.5, 'street south of the tower stays sunny');
});
test('a northern sun moves the shadow to the south side', () => {
  const s = engine.shadeSlot(northSun, true, false);
  assert.ok(sunOn(s, southStreet) < 0.5, 'street south of the tower should be shaded: ' + sunOn(s, southStreet));
});
test('far streets are sunlit', () => {
  const s = engine.shadeSlot(southSun, true, false);
  const far = edges.findIndex(e => e[0] === id(3, 0) && e[1] === id(4, 0));
  assert.ok(s.left[far] > 0.9 && s.right[far] > 0.9);
});
test('routes: shady route is never longer than budget and never sunnier than fastest', () => {
  const slot = engine.shadeSlot(southSun, true, false);
  const r = engine.routes(ll(0, 300), ll(400, 300), () => slot, 4, false);
  assert.ok(r.best.length <= r.fast.length + 4 * 80.4672 + 1);
  assert.ok(r.best.sunMinutes <= r.fast.sunMinutes + 1e-6);
  assert.ok(r.fast.length >= 399 && r.fast.length <= 401, 'straight route is 400 m: ' + r.fast.length);
});
test('winter prefers sun', () => {
  const slot = engine.shadeSlot(southSun, true, false);
  const r = engine.routes(ll(0, 300), ll(400, 300), () => slot, 4, true);
  assert.ok(r.best.sunMinutes >= r.fast.sunMinutes - 1e-6);
});
test('points far from streets are refused', () => {
  assert.throws(() => engine.routes(ll(0, 300), ll(5000, 5000), () => engine.shadeSlot(southSun, true, false), 3, false));
});
console.log(`${passed} engine checks passed`);
