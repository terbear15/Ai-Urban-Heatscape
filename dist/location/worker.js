importScripts('https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.js');
async function initialize(){
  const python=await loadPyodide();
  await Promise.all(['search.py','lookup.py','places.json'].map(async name=>{
    const response=await fetch(name+self.location.search);
    if(!response.ok)throw new Error('Location data could not load.');
    python.FS.writeFile(name,await response.text());
  }));
  await python.runPythonAsync(python.FS.readFile('lookup.py', {encoding:'utf8'}));
  return python.globals.get('lookup');
}
let runtime;
self.onmessage=async ({data:{id,query,address,suggest}})=>{
  try{
    runtime ??= initialize().catch(error=>{runtime=null;throw error;});
    const lookup=await runtime;
    const matches=JSON.parse(await lookup(query,address,suggest));
    self.postMessage({id,matches});
  }catch(error){
    self.postMessage({id,error:String(error.message).trim().split('\n').at(-1)});
  }
};
