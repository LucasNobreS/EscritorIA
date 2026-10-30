(function(){
const errors=[];
function show(message){errors.push(message);let box=document.getElementById('startupError');if(!box){box=document.createElement('div');box.id='startupError';box.setAttribute('role','alert');box.style.cssText='position:fixed;z-index:99999;left:16px;right:16px;top:16px;padding:18px;background:#532e26;color:white;font:14px/1.6 system-ui;border:2px solid #ffc1a8;border-radius:10px;white-space:pre-wrap;max-height:70vh;overflow:auto';document.body.appendChild(box);}box.textContent='Falha ao iniciar o EscritorIA v0.45.0\n'+errors.join('\n')+'\nEndereço: '+location.href+'\nEnvie uma captura desta mensagem.';}
window.addEventListener('error',function(e){const message=e.target!==window&&e.target&&(e.target.src||e.target.href)?'Arquivo não carregado: '+(e.target.src||e.target.href):(e.message||'Erro de execução')+' — '+(e.filename||'')+':'+(e.lineno||'');if(document.body)show(message);else window.addEventListener('DOMContentLoaded',()=>show(message),{once:true});},true);
window.addEventListener('unhandledrejection',e=>show('Erro: '+(e.reason?.message||e.reason)));
window.addEventListener('load',async()=>{
if(location.protocol==='file:'){show('Abra pelo Iniciar.bat e pelo endereço HTTP mostrado no terminal.');return;}
try{const r=await fetch('/api/health',{cache:'no-store'}),h=await r.json();if(!r.ok||h.version!=='0.45.0')show('Esta aba está conectada a uma versão antiga. Use o endereço exibido no terminal da v0.45.0.');}catch(e){show('Não foi possível identificar o servidor: '+e.message);}
if(getComputedStyle(document.getElementById('game')).position!=='relative')show('O CSS não foi aplicado. Confira web/style.css.');
if(typeof document.getElementById('enter').onclick!=='function')show('O script /world.js não iniciou.');
});
})();
