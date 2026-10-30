const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup(multiplier=1){
 const nodes={},handlers={},frames=[],calls=[],characters=[];const noop=()=>{},gradient={addColorStop:noop};
 const ctx=new Proxy({measureText:text=>({width:String(text).length*8}),createRadialGradient:()=>gradient},{get:(obj,key)=>obj[key]||noop,set:(obj,key,value)=>(obj[key]=value,true)});
 class Element{
  constructor(tag='div'){this.tagName=tag.toUpperCase();this.hidden=false;this.children=[];this.dataset={};this.style={};this.clientWidth=1280;this.clientHeight=800;this.value='';this.handlers={};}
  set id(value){this.name=value;nodes[value]=this;}get id(){return this.name;}
  set innerHTML(value){for(const match of value.matchAll(/id="([^"]+)"/g))get(match[1]);}
  getContext(){return ctx;}setAttribute(){}appendChild(child){this.children.push(child);}replaceChildren(){this.children=[];}focus(){}
  addEventListener(event,callback){this.handlers[event]=callback;}getBoundingClientRect(){return {left:0,top:0};}
 }
 function get(id){if(!nodes[id]){const value=new Element();value.id=id;}return nodes[id];}
 const map={width:4200,height:3200,roads:[],parks:[],water:[[3750,2450,420,410]],districts:[],buildings:[{id:'office',name:'EscritorIA',kind:'office',x:900,y:1700,w:360,d:240,h:180,color:'#91aebd',door:[1080,1985]}]};
 const state={employees:[],world:{player:{name:'Lucas',skin:{}}},town:{resting:0,npc_social:1,usage:{calls:0,ambient:0},dailyLimit:40,ambientLimit:12,staff:[],npcs:[{id:1,name:'Maya',role:'artista',scene:'city',x:1100,y:2020}],chats:[]}};
 get('dialog').hidden=true;
 const window={devicePixelRatio:1,officeMovementMultiplier:multiplier,officeDrawCharacter:(g,x,y,skin)=>characters.push(skin),addEventListener:(name,callback)=>(handlers[name]??=[]).push(callback),dispatchEvent:event=>(handlers[event.type]||[]).forEach(fn=>fn(event))};
 let clock=0;const scope={Date:{now:()=>clock},window,state,console,document:{getElementById:get,createElement:tag=>new Element(tag),activeElement:{tagName:'BODY'}},post:async(endpoint,body)=>{calls.push([endpoint,body]);if(endpoint==='town/map')return map;if(endpoint==='town/decorate')return {ok:true,layout:{...body.layout,revision:1}};if(endpoint==='town/interact')return {ok:true,message:'Banco da praça',actions:[{id:'sit',name:'Sentar'}],pose:body.action==='sit'?'sit':null};return {ok:true};},requestAnimationFrame:callback=>frames.push(callback),Event:class{constructor(type){this.type=type;}},closeDialog:noop,report:noop};
 vm.createContext(scope);vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/web/town.js'),'utf8'),scope);
 function step(n=1){for(let i=0;i<n;i++){clock+=40;for(const callback of frames.splice(0))callback(clock);}}
 return {view:window.townView,nodes,calls,state,map,characters,step,key:(key)=>window.dispatchEvent({type:'keydown',key,preventDefault:noop})};
}
test('city opens, projects coordinates and returns to the office',async()=>{
 const app=setup();await app.view.open();app.step();assert.equal(app.calls[0][0],'town/map');assert.equal(app.nodes.townCanvas.hidden,false);
 const p=app.view.worldToScreen(1200,2100),back=app.view.unproject(p.x,p.y);assert.ok(Math.abs(back.x-1200)<.001);assert.ok(Math.abs(back.y-2100)<.001);
 assert.equal(app.view.blocked(1000,1800),true);assert.equal(app.view.blocked(3800,2600),true);assert.equal(app.view.blocked(1200,2100),false);
 app.view.close();assert.equal(app.nodes.townCanvas.hidden,true);
});
test('E opens casual NPC conversation and sends only a bounded chat request',async()=>{
 const app=setup();await app.view.open();app.step();app.key('e');assert.equal(app.nodes.npcPanel.hidden,false);assert.equal(app.nodes.npcName.textContent,'Maya · artista');
 app.nodes.npcText.value='Olá, como está o bairro?';await app.nodes.npcCompose.onsubmit({preventDefault(){}});
 assert.equal(app.calls.at(-1)[0],'town/chat');assert.equal(app.calls.at(-1)[1].npc,1);assert.equal(app.calls.at(-1)[1].message,'Olá, como está o bairro?');
 app.state.town.chats=[{npc:1,partner:null,message:'Olá',reply:'<script>nada</script>',status:'done'}];app.step(15);
 assert.equal(app.nodes.npcMessages.children.at(-1).textContent,'<script>nada</script>');
});
test('shared movement speed also increases city walking',async()=>{
 const distances=[];for(const speed of [1,2]){const app=setup(speed);await app.view.open();app.step();const start={...app.view.position};app.key('s');app.step(10);distances.push(Math.hypot(app.view.position.x-start.x,app.view.position.y-start.y));}
 assert.ok(Math.abs(distances[1]-distances[0]*2)<.001);
});
test('bedtime and wake controls use explicit owner commands',async()=>{
 const app=setup();await app.nodes.townNight.onclick();assert.equal(app.calls.at(-1)[1].command,'boa noite');await app.nodes.townWake.onclick();assert.equal(app.calls.at(-1)[1].command,'retomar');
});
test('city furniture opens contextual actions, seats the player and releases on movement',async()=>{
 const app=setup();app.state.town.npcs=[];app.map.objects=[{id:'bench',kind:'bench',label:'Banco',x:1095,y:2050,w:100,d:40,h:58,color:'#aabbcc',solid:true}];await app.view.open();app.step();app.key('e');await new Promise(resolve=>setImmediate(resolve));assert.equal(app.calls.at(-1)[0],'town/interact');assert.equal(app.nodes.townObjectPanel.hidden,false);assert.equal(app.nodes.townObjectActions.children[0].textContent,'Sentar');await app.nodes.townObjectActions.children[0].onclick();app.step();assert.equal(app.characters.at(-1).seated,true);assert.equal(app.nodes.townObjectPanel.hidden,true);app.key('s');app.step();assert.equal(app.characters.at(-1).seated,false);
});
test('world travel has no explore-city button',()=>{const app=setup();assert.equal(app.nodes.visitTown,undefined);});
test('building and interior doors support walking through by click',async()=>{
 const app=setup();app.state.town.npcs=[];app.map.buildings.push({id:'shop',kind:'books',name:'Livraria',x:1400,y:1700,w:250,d:210,h:150,color:'#aabbcc',door:[1525,1955]});app.map.interiors={shop:{objects:[]}};await app.view.open();app.step();let p=app.view.worldToScreen(1525,1910,65);app.nodes.townCanvas.handlers.click({clientX:p.x,clientY:p.y});app.step(250);assert.equal(app.view.scene,'shop');p=app.view.worldToScreen(550,815,60);app.nodes.townCanvas.handlers.click({clientX:p.x,clientY:p.y});app.step(80);assert.equal(app.view.scene,'city');
});

test('walking to a threshold enters without clicking the building and does not bounce back',async()=>{
 const app=setup(2);app.state.town.npcs=[];app.map.buildings.push({id:'home',kind:'house',name:'Casa',x:1400,y:1700,w:250,d:210,h:150,color:'#aabbcc',door:[1525,1955]});app.map.interiors={home:{objects:[]}};
 await app.view.open();app.step(30);assert.equal(app.view.route(1525,1955),true);app.step(350);assert.equal(app.view.scene,'home');app.step(60);assert.equal(app.view.scene,'home');
 app.view.route(550,780);app.step(100);assert.equal(app.view.scene,'city');app.step(60);assert.equal(app.view.scene,'city');
});
test('NPC renderer uses the persisted full skin',async()=>{
 const app=setup();app.state.town.npcs[0].skin={skin:'#986544',outfit:'blazer',hairStyle:'afro',shirt:'#719cad'};await app.view.open();app.step();assert.ok(app.characters.some(s=>s.skin==='#986544'&&s.outfit==='blazer'&&s.hairStyle==='afro'));
});

test('interior decoration edits a draft, cancels cleanly and saves scoped colors',async()=>{
 const app=setup();app.state.town.npcs=[];app.map.buildings.push({id:'home',kind:'house',name:'Casa',x:1400,y:1700,w:250,d:210,h:150,color:'#aabbcc',door:[1525,1955]});app.map.interiors={home:{theme:'house',wall:'#aabbcc',floor:'#ccbbaa',objects:[]}};
 await app.view.open();app.step(30);app.view.route(1525,1955);app.step(350);assert.equal(app.view.scene,'home');
 app.nodes.townDecorate.onclick();app.nodes.roomWall.oninput({target:{value:'#112233'}});const before={...app.view.position};app.key('s');app.step(20);assert.equal(app.view.position.x,before.x);app.nodes.roomCancel.onclick();assert.equal(app.map.interiors.home.wall,'#aabbcc');
 app.nodes.townDecorate.onclick();app.nodes.roomWall.oninput({target:{value:'#334455'}});await app.nodes.roomSave.onclick();assert.equal(app.calls.at(-1)[0],'town/decorate');assert.equal(app.calls.at(-1)[1].scene,'home');assert.equal(app.map.interiors.home.wall,'#334455');assert.equal(app.nodes.townEditor.hidden,true);
});
