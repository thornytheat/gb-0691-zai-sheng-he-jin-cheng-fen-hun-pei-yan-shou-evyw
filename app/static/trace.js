const meta=JSON.parse(document.querySelector('#trace-meta').textContent);
const demoOps=JSON.parse(document.querySelector('#demo-ops').textContent);
const feedback=document.querySelector('#feedback');
let busy=false;
async function postTrace(url,payload){
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok)throw Error(data.message||'请求失败，请重试');
  return data;
}
function openTrace(trace){location.href='/work/8?run_id='+encodeURIComponent(trace.run_id)+'&trace_id='+encodeURIComponent(trace.trace_id)}
function stepLimit(){const v=document.querySelector('#max-steps').value.trim();return v?parseInt(v,10):null}
async function act(fn){
  if(busy)return;busy=true;feedback.textContent='正在追溯…';
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{await fn()}catch(error){feedback.textContent=error.message}
  finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false)}
}
document.querySelector('#start').addEventListener('click',()=>act(async()=>{
  const trace=await postTrace('/api/trace',{run_id:meta.run_id,lot:document.querySelector('#lot').value,transfers_csv:document.querySelector('#transfers').value,max_steps:stepLimit()});
  openTrace(trace);
}));
const resumeButton=document.querySelector('#resume');
if(resumeButton)resumeButton.addEventListener('click',()=>act(async()=>{
  const trace=await postTrace('/api/trace/'+meta.trace_id+'/resume',{max_steps:stepLimit()});
  openTrace(trace);
}));
document.querySelector('#demo').addEventListener('click',()=>act(async()=>{
  const run=await postTrace('/api/run',{csv:demoOps});
  const trace=await postTrace('/api/trace',{run_id:run.manifest.run_id,lot:document.querySelector('#lot').value||'00001',transfers_csv:document.querySelector('#transfers').value,max_steps:stepLimit()});
  openTrace(trace);
}));
