importScripts('https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.js');
async function initialize(){
  const python=await loadPyodide();
  await Promise.all(['search.py','lookup.py','places.json','city_buildings.py'].map(async name=>{
    const response=await fetch(name+self.location.search);
    if(!response.ok)throw new Error('Location data could not load.');
    python.FS.writeFile(name,await response.text());
  }));
  await python.runPythonAsync(python.FS.readFile('lookup.py', {encoding:'utf8'}));
  await python.runPythonAsync('from city_buildings import city_scene');
  return python;
}
let runtime, city;
async function loadCity(python){
  const response=await fetch('../explorer/app.resources.zip');
  if(!response.ok)throw new Error('The Philadelphia walking network could not load.');
  python.unpackArchive(await response.arrayBuffer(),'zip');
  await python.loadPackage('numpy');
  const bridge=await fetch('city_route.py'+self.location.search);
  if(!bridge.ok)throw new Error('City routing could not start.');
  await python.runPythonAsync(await bridge.text());
  return python.globals.get('city_route');
}
self.onmessage=async ({data:{id,query,address,suggest,trip,scene}})=>{
  try{
    runtime ??= initialize().catch(error=>{runtime=null;throw error;});
    const python=await runtime;
    let matches;
    if(scene){
      const render=python.globals.get('city_scene');
      try{matches=JSON.parse(await render(JSON.stringify(scene)));}
      finally{render.destroy();}
    }else if(trip){
      city ??= loadCity(python).catch(error=>{city=null;throw error;});
      const route=await city;
      matches=JSON.parse(await route(JSON.stringify(trip)));
    }else{
      const lookup=python.globals.get('lookup');
      try{matches=JSON.parse(await lookup(query,address,suggest));}
      finally{lookup.destroy();}
    }
    self.postMessage({id,matches});
  }catch(error){
    self.postMessage({id,error:String(error.message).trim().split('\n').at(-1)});
  }
};
