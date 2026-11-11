/* Center City planar analysis. Internal distances are meters. */
(function(root){
const origin=[-75.167,39.9515],sx=111320*Math.cos(origin[1]*Math.PI/180),sy=111320;
const xy=p=>[(p[0]-origin[0])*sx,(p[1]-origin[1])*sy],ll=p=>[p[0]/sx+origin[0],p[1]/sy+origin[1]],distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
function contains(p,r){let yes=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const a=r[i],b=r[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes;}return yes;}
function create(data){
const nodes=new Map(),edges=data.edges.map((e,id)=>{for(const [k,p] of [[e.a,e.p],[e.b,e.q]])if(!nodes.has(k))nodes.set(k,{p:xy(p),links:[]});const edge={...e,id,length:distance(xy(e.p),xy(e.q)),sun:1};nodes.get(e.a).links.push(edge);nodes.get(e.b).links.push(edge);return edge;});
let largest=new Set(),visited=new Set();for(const key of nodes.keys()){if(visited.has(key))continue;const component=new Set([key]),queue=[key];visited.add(key);while(queue.length){const k=queue.pop();for(const e of nodes.get(k).links){const other=e.a===k?e.b:e.a;if(!visited.has(other)){visited.add(other);component.add(other);queue.push(other);}}}if(component.size>largest.size)largest=component;}
function updateShade(azimuth,altitude){
const bins=new Map(),polys=[],features=[];
function add(r){const idx=polys.length;polys.push(r);const xs=r.map(p=>p[0]),ys=r.map(p=>p[1]);for(let x=Math.floor(Math.min(...xs)/50);x<=Math.floor(Math.max(...xs)/50);x++)for(let y=Math.floor(Math.min(...ys)/50);y<=Math.floor(Math.max(...ys)/50);y++){const k=x+','+y;if(!bins.has(k))bins.set(k,[]);bins.get(k).push(idx);}features.push({type:'Feature',properties:{},geometry:{type:'Polygon',coordinates:[r.map(ll)]}});}
if(altitude>.04)for(const b of data.buildings.features){const r=b.geometry.coordinates[0].map(xy),len=b.properties.height/Math.tan(altitude),dx=Math.sin(azimuth)*len,dy=Math.cos(azimuth)*len;add(r);for(let i=0;i<r.length-1;i++){const p=r[i],q=r[i+1];add([p,q,[q[0]+dx,q[1]+dy],[p[0]+dx,p[1]+dy],p]);}}
function shaded(p){return (bins.get(Math.floor(p[0]/50)+','+Math.floor(p[1]/50))||[]).some(i=>contains(p,polys[i]));}
for(const e of edges){const p=xy(e.p),q=xy(e.q),n=Math.max(1,Math.ceil(e.length/10));let count=0;for(let i=0;i<n;i++){const t=(i+.5)/n;if(shaded([p[0]+t*(q[0]-p[0]),p[1]+t*(q[1]-p[1])]))count++;}e.sun=1-count/n;}
return {type:'FeatureCollection',features};}
function snap(coord){const p=xy(coord);let best=null,d=Infinity;for(const k of largest){const dd=distance(p,nodes.get(k).p);if(dd<d){d=dd;best=k;}}return {id:best,meters:d,coord:ll(nodes.get(best).p)};}
function path(start,end,penalty){
const costs=new Map([[start,0]]),previous=new Map(),heap=[];
function push(item){heap.push(item);let i=heap.length-1;while(i){const p=(i-1)>>1;if(heap[p][0]<=item[0])break;heap[i]=heap[p];i=p;}heap[i]=item;}
function pop(){const first=heap[0],last=heap.pop();if(heap.length){let i=0;while(i*2+1<heap.length){let c=i*2+1;if(c+1<heap.length&&heap[c+1][0]<heap[c][0])c++;if(heap[c][0]>=last[0])break;heap[i]=heap[c];i=c;}heap[i]=last;}return first;}
push([0,start]);while(heap.length){const [cost,k]=pop();if(cost!==costs.get(k))continue;if(k===end)break;for(const e of nodes.get(k).links){const next=e.a===k?e.b:e.a,value=cost+e.length*(1+penalty*e.sun);if(value<(costs.get(next)??Infinity)){costs.set(next,value);previous.set(next,{k,e});push([value,next]);}}}
if(!costs.has(end))return null;let k=end,segments=[],coords=[ll(nodes.get(end).p)];while(k!==start){const prev=previous.get(k);segments.push(prev.e);k=prev.k;coords.push(ll(nodes.get(k).p));}segments.reverse();coords.reverse();return {segments,coords,length:segments.reduce((s,e)=>s+e.length,0),exposure:segments.reduce((s,e)=>s+e.length*e.sun,0)};}
function routeNodes(route,start){
  const keys=[start];
  for(const edge of route.segments)keys.push(edge.a===keys.at(-1)?edge.b:edge.a);
  return keys;
}
function metrics(segments){
  return {
    length:segments.reduce((sum,edge)=>sum+edge.length,0),
    exposure:segments.reduce((sum,edge)=>sum+edge.length*edge.sun,0),
  };
}
function localDetours(fast,candidate,start,maxExtra){
  const fastKeys=routeNodes(fast,start);
  const positions=new Map(fastKeys.map((key,index)=>[key,index]));
  const joins=routeNodes(candidate,start).flatMap((key,index)=>
    positions.has(key)?[[positions.get(key),index]]:[]);
  const segments=[];
  for(let i=1;i<joins.length;i++){
    const [from,altFrom]=joins[i-1];
    const [to,altTo]=joins[i];
    if(to<=from)return fast;
    const direct=fast.segments.slice(from,to);
    const detour=candidate.segments.slice(altFrom,altTo);
    const base=metrics(direct), alt=metrics(detour);
    segments.push(...(alt.length<=base.length+maxExtra+1e-6 &&
      alt.exposure<base.exposure-1e-6?detour:direct));
  }
  const summary=metrics(segments);
  if(summary.exposure>=fast.exposure-1e-6)return fast;
  return {...summary,segments,coords:routeNodes({segments},start).map(key=>ll(nodes.get(key).p))};
}
function routes(a,b,extra){
  const start=snap(a),end=snap(b);
  if(start.id===end.id)throw Error('Choose two places farther apart.');
  if(start.meters>150||end.meters>150)throw Error('Choose points closer to the network inside the study boundary.');
  const fast=path(start.id,end.id,0);
  if(!fast)throw Error('No connected route in this extract.');
  let shade=fast;
  for(const penalty of [.5,1,2,4,8,16,40]){
    const candidate=path(start.id,end.id,penalty);
    if(!candidate)continue;
    const mixed=localDetours(fast,candidate,start.id,extra*80.4672);
    if(mixed.exposure<shade.exposure)shade=mixed;
  }
  return {fast,shade,start,end};
}
return {nodes,edges,updateShade,routes,snap,componentSize:largest.size};}
root.HeatEngine={create,xy,ll,contains,distance};if(typeof module!=='undefined')module.exports=root.HeatEngine;
})(typeof window!=='undefined'?window:globalThis);
