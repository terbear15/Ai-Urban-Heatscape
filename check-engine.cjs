const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={window:{}};vm.runInNewContext(fs.readFileSync(__dirname+'/dist/philly-data.js','utf8'),context);
const H=require('./dist/engine.js'),Sun=require('./dist/vendor/suncalc.js'),data=context.window.PHILLY,engine=H.create(data);
const a=[-75.17175,39.9497],b=[-75.1659,39.9541];
const sun=Sun.getPosition(new Date('2026-07-15T15:00:00-04:00'),39.9515,-75.167);
const shadows=engine.updateShade(sun.azimuth,sun.altitude);assert(shadows.features.length>0);
const r=engine.routes(a,b,5);assert(r.fast.length>0);assert(r.shade.exposure<=r.fast.exposure);assert(r.fast.exposure<=r.fast.length);
for(const route of [r.fast,r.shade])for(let i=0;i<route.segments.length-1;i++){const p=route.segments[i],q=route.segments[i+1];assert([p.a,p.b].some(n=>n===q.a||n===q.b),'Disconnected route');}
const zero=engine.routes(a,b,0);assert(zero.shade.length<=zero.fast.length+.001);
assert.throws(()=>engine.routes(a,a));assert.throws(()=>engine.routes([-74,40],b));
const before=r.fast.exposure;const morning=Sun.getPosition(new Date('2026-07-15T09:00:00-04:00'),39.9515,-75.167);engine.updateShade(morning.azimuth,morning.altitude);assert(Math.abs(engine.routes(a,b,5).fast.exposure-before)>1);
const toy=H.create({edges:[{a:'a',b:'b',p:H.ll([0,10]),q:H.ll([0,20])}],buildings:{features:[{properties:{height:10},geometry:{coordinates:[[[-5,-5],[5,-5],[5,5],[-5,5],[-5,-5]].map(H.ll)]}}]}});toy.updateShade(0,Math.PI/4);assert(toy.edges[0].sun<1,'A southern sun must cast a northern shadow');toy.updateShade(Math.PI,Math.PI/4);assert.strictEqual(toy.edges[0].sun,1);
// A short shade detour should survive even when another section is too slow.
const points={a:[0,0],b:[100,0],c:[200,0],x:[50,50],y:[150,100]};
const pairs=[['a','b'],['b','c'],['a','x'],['x','b'],['b','y'],['y','c']];
const mixed=H.create({
  edges:pairs.map(([a,b])=>({a,b,p:H.ll(points[a]),q:H.ll(points[b])})),
  buildings:{features:[]},
});
for(const edge of mixed.edges.slice(2))edge.sun=0;
const local=mixed.routes(H.ll(points.a),H.ll(points.c),1);
assert.deepStrictEqual(local.shade.segments.map(edge=>edge.id),[2,3,1]);
const both=mixed.routes(H.ll(points.a),H.ll(points.c),2);
assert.deepStrictEqual(both.shade.segments.map(edge=>edge.id),[2,3,4,5]);
assert(both.shade.length-both.fast.length>2*80.4672);
console.log(JSON.stringify({passed:true,buildings:data.buildings.features.length,segments:data.edges.length,connectedNodes:engine.componentSize,shortestMiles:r.fast.length/1609.344,alternativeMiles:r.shade.length/1609.344,modeledSunMinutes:[r.fast.exposure/80.4672,r.shade.exposure/80.4672]},null,2));
