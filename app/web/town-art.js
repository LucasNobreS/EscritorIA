(()=>{'use strict';
function drawObject(o,a){const {g,box,polygon,tile,project,frontRect,shade,label}=a,{x,y,w,d,h,color:c}=o,s=a.state||{},on=s.on!==false;
 const ellipse=(xx,yy,z,rx,ry,col)=>{const p=project(xx,yy,z);g.fillStyle=col;g.beginPath();g.ellipse(p.x,p.y,rx,ry,0,0,Math.PI*2);g.fill();};
 const disk=(xx,yy,z,r,col)=>polygon(Array.from({length:28},(_,n)=>{const t=n*Math.PI/14;return project(xx+Math.cos(t)*r,yy+Math.sin(t)*r,z);}),col);
 if(o.solid){polygon(tile(x+7,y+9,w+6,d+6),'#1f3c4217');polygon(tile(x+2,y+3,w,d),'#203a4b14');}
 switch(o.kind){
 case 'rug':polygon(tile(x,y,w,d),c,'#4e777044');polygon(tile(x+7,y+7,w-14,d-14),shade(c,12));for(let n=15;n<w-12;n+=18){polygon(tile(x+n,y+2,6,3),'#f1e1bc');polygon(tile(x+n,y+d-5,6,3),'#f1e1bc');}break;
 case 'bed':box(x,y,w,d,29,'#8c7866');box(x-6,y-7,w+12,19,90,'#9d8f80');box(x+5,y+9,w-10,d-17,20,'#f1e8d8',29);box(x+6,y+d*.29,w-12,d*.68,13,a.accent||'#8ba9a8',49);box(x+6,y+d*.27,w-12,16,7,'#f5e9d4',61);for(let n=0;n<2;n++){box(x+17+n*(w/2),y+25,w/2-29,46,12,'#fbf4e8',48);box(x+20+n*w/2,y+29,w/2-35,3,2,'#d6cdbd',60);}for(let yy=y+d*.42;yy<y+d;yy+=32)polygon(tile(x+11,yy,w-22,1,63),'#4a777426');break;
 case 'sofa':box(x+10,y+8,w-20,d-10,13,'#685f55');box(x,y,w,d,20,shade(c,-10),13);box(x,y,w,14,52,c,20);for(let i=0;i<3;i++){box(x+15+i*(w-30)/3,y+17,(w-39)/3,d-25,12,shade(c,17),31);box(x+16+i*(w-30)/3,y+14,(w-41)/3,8,30,shade(c,8),35);}box(x,y+8,14,d-8,45,c,17);box(x+w-14,y+8,14,d-8,45,c,17);box(x+w-60,y+20,32,30,10,'#e5c591',43);break;
 case 'chair':if(window.officeDrawFurniture)window.officeDrawFurniture(g,{...o,label:'',kind:'chair',rotation:0});break;
 case 'table':case 'coffee':for(const [xx,yy]of [[x+9,y+8],[x+w-16,y+8],[x+9,y+d-16],[x+w-16,y+d-16]])box(xx,yy,7,7,h-8,'#8c8073');box(x,y,w,d,8,c,h-8);polygon(tile(x+4,y+4,w-8,d-8,h+.2),shade(c,7));disk(x+w*.6,y+d*.45,h+2,13,'#ede5d2');box(x+w*.6-6,y+d*.45-6,12,12,12,'#eee9db',h+3);box(x+13,y+12,28,37,2,'#8caaa5',h+1);break;
 case 'bench':for(const xx of [x+12,x+w-20]){box(xx,y+4,8,d-8,26,'#536c73');box(xx,y,8,5,54,'#536c73');}for(let i=0;i<4;i++)box(x,y+i*d/4,w,d/4-2,6,c,27);for(let i=0;i<3;i++)box(x,y,w,5,7,c,35+i*9);break;
 case 'wardrobe':box(x,y,w,d,h,c);for(let i=0;i<3;i++){frontRect(x+5+i*w/3,y+d+.5,5,w/3-9,h-11,shade(c,i%2?8:-3));frontRect(x+17+i*w/3,y+d+1,h/2,3,17,'#e7d2a1');}box(x-3,y-2,w+6,d+4,6,'#d5b996',h);break;
 case 'shelf':box(x,y,w,d,h,'#ac9274');box(x+5,y+5,w-10,d-8,h-9,'#776d60');for(let level=0;level<4;level++){const z=6+level*(h-12)/4;box(x+3,y+3,w-6,d-5,5,'#ceb38e',z);if(d>w){for(let j=0;j<Math.floor((d-16)/17);j++)box(x+w-15,y+12+j*17,16,12,23,['#8fa8b7','#c98e7c','#b5bb91','#c6ad7f'][j%4],z+5);}else for(let j=0;j<Math.floor((w-16)/17);j++)box(x+12+j*17,y+d-15,12,16,23,['#8fa8b7','#c98e7c','#b5bb91','#c6ad7f'][j%4],z+5);}break;
 case 'kitchen':box(x,y,w,d,65,c);box(x-3,y-3,w+6,d+6,7,'#ebe3d4',65);box(x+w-80,y+8,60,d-18,2,'#a0b5b6',72);box(x+14,y+11,38,30,33,'#4b666c',72);for(let n=1;n<4;n++)frontRect(x+n*w/4,y+d+1,5,2,55,'#829c93');break;
 case 'counter':box(x+6,y+3,w-12,d-6,h-10,c);for(let n=0;n<w;n+=28)frontRect(x+n+4,y+d,8,2,h-20,shade(c,-12));box(x-4,y-4,w+8,d+8,10,'#e8ddc9',h-10);box(x+20,y+9,57,40,35,'#405c65',h);box(x+29,y+44,18,3,15,'#d2b28b',h+3);for(let n=0;n<Math.floor((w-110)/62);n++){const xx=x+105+n*62;disk(xx,y+d*.54,h+2,18,'#f2e7d5');if(o.theme==='bakery'){ellipse(xx,y+d*.54,h+8,13,7,'#c38e5b');const p=project(xx,y+d*.54,h+11);g.strokeStyle='#e0ba7c';g.beginPath();g.moveTo(p.x-5,p.y-4);g.lineTo(p.x+4,p.y+3);g.stroke();}else if(o.theme==='market'){for(let k=0;k<3;k++)disk(xx-7+k*7,y+d*.54,h+5,6,['#bb7f6a','#b3be7e','#e1bd75'][k]);}else box(xx-6,y+d*.54-6,12,12,14,n%2?'#c2947f':'#e9e4d3',h+2);}break;
 case 'rack':for(const xx of [x+8,x+w-12]){box(xx,y+d/2,4,4,h,'#6c8590');box(xx-10,y+d/2-13,24,30,4,'#7a9299');}box(x+8,y+d/2,w-16,4,4,'#adc0c0',h-5);for(let n=0;n<5;n++){const xx=x+25+n*(w-45)/5;box(xx,y+d/2-5,5,11,11,'#dbcaac',h-20);frontRect(xx-4,y+d/2+6,25,23,h-52,['#c79598','#8faebd','#b8bd91','#e0c590','#a99aba'][n]);frontRect(xx+6,y+d/2+7,28,2,h-64,'#ffffff45');}break;
 case 'mirror':box(x,y,w,d,h,'#c2ab87');frontRect(x+8,y+d+1,10,w-16,h-20,'#9dbbc4');polygon([project(x+12,y+d+2,18),project(x+w-20,y+d+2,40),project(x+w-12,y+d+2,h-20),project(x+18,y+d+2,h-48)],'#e6f0ed55');break;
 case 'arcade':box(x,y,w,d,38,'#4d586b');box(x+4,y+14,w-8,d-16,h-40,c,38);frontRect(x+11,y+d+1,61,w-22,46,'#293b56');frontRect(x+15,y+d+2,65,w-30,38,'#648b9d');for(let i=0;i<3;i++)frontRect(x+20+i*12,y+d+3,73+i*5,7,9,['#efcf7c','#bb9cce','#9cd1b0'][i]);box(x-5,y+d-18,w+10,22,8,shade(c,12),43);box(x+10,y+d-10,4,4,10,'#dcb586',51);disk(x+w-15,y+d-8,53,4,'#e0a0a0');frontRect(x+6,y+d+1,h-15,w-12,13,'#ead7a6');break;
 case 'display':box(x,y,w,d,55,c);for(let j=0;j<3;j++){box(x+4,y+8+j*d/3,w-8,d/3-8,8,'#d5b88d',55+j*6);for(let n=0;n<6;n++)disk(x+15+n*(w-28)/6,y+23+j*d/3,66+j*6,7,['#b8be80','#c88e6d','#dfbb72'][j]);}break;
 case 'partition':box(x,y,w,d,h,c);box(x-2,y,w+4,d,5,'#eee2cd',h);break;
 case 'plant':case 'planter':case 'tree':{
  const tree=o.kind==='tree',cx=x+w/2,cy=y+d/2,z=tree?75:35;
  if(!tree){box(x+3,y+3,w-6,d-6,28,c);box(x,y,w,d,6,shade(c,14),28);polygon(tile(x+5,y+5,w-10,d-10,35),'#6c6b50');}
  box(cx-4,cy-4,8,8,tree?70:24,'#8b755c',tree?0:30);
  const p=project(cx,cy,tree?87:58),size=tree?1:.46;
  for(const [dx,dy,r,cc]of [[-17,5,30,'#568970'],[20,1,32,'#689c78'],[-1,-25,33,'#82af86'],[-22,-16,19,'#749f79'],[20,-28,20,'#91b88c']]){const cx=p.x+dx*size,cy=p.y+dy*size,R=r*size;polygon([[-.6,-1],[.5,-1],[.5,-.8],[.85,-.8],[.85,-.4],[1,-.4],[1,.5],[.65,.5],[.65,.85],[-.55,.85],[-.55,.65],[-1,.65],[-1,-.5],[-.6,-.5]].map(([xx,yy])=>({x:Math.round(cx+xx*R),y:Math.round(cy+yy*R)})),cc,'#3f674b');}
  if(o.kind==='planter')for(let n=0;n<5;n++){const f=project(x+10+n*(w-20)/5,cy,65);g.fillStyle=['#e7ba8f','#c59ab4','#f0d79c'][n%3];g.beginPath();g.arc(f.x,f.y,4,0,7);g.fill();}
  if(s.watered)label('✓',cx,cy,tree?150:90,16,'#547f9b');break;}
 case 'lamp':box(x,y,w,d,7,'#72858b');box(x+w/2-3,y+d/2-3,6,6,h-20,'#647d85');box(x+w/2-16,y+d/2-16,32,32,14,on&&a.night?'#ffe4a7':'#d3c8a8',h-19);box(x+w/2-18,y+d/2-18,36,36,4,'#8c9c98',h-5);if(a.night&&on){const p=project(x+w/2,y+d/2);const glow=g.createRadialGradient(p.x,p.y,1,p.x,p.y,85);glow.addColorStop(0,'#f7da9a50');glow.addColorStop(1,'#f7da9a00');g.fillStyle=glow;g.beginPath();g.ellipse(p.x,p.y,86,40,0,0,7);g.fill();}break;
 case 'notice':box(x+12,y+10,6,6,h-12,'#7e7c6b');box(x+w-18,y+10,6,6,h-12,'#7e7c6b');box(x,y,w,d,78,c,h-78);frontRect(x+7,y+d+.5,h-70,w-14,62,'#e8d7b2');for(let n=0;n<3;n++)frontRect(x+14+n*(w-24)/3,y+d+1,h-55,(w-35)/3,35,['#f5edda','#bad0c5','#dbc3bb'][n]);break;
 case 'fountain':{
  const cx=x+w/2,cy=y+d/2;disk(cx,cy,0,w/2,'#90a5a1');disk(cx,cy,8,w/2-5,'#c1cebf');disk(cx,cy,13,w/2-13,on?'#7db8c1':'#a5b5af');box(cx-9,cy-9,18,18,50,'#b5c8bf',12);disk(cx,cy,64,25,'#d5dfd0');if(on){g.strokeStyle='#d0eef0bb';g.lineWidth=2;for(let n=0;n<6;n++){const t=n*Math.PI/3,p=project(cx,cy,72),end=project(cx+Math.cos(t)*43,cy+Math.sin(t)*43,16);g.beginPath();g.moveTo(p.x,p.y);g.quadraticCurveTo((p.x+end.x)/2,p.y-25,end.x,end.y);g.stroke();}}break;}
 case 'bin':box(x,y,w,d,h,'#768e87');box(x-3,y-3,w+6,d+6,6,c,h);frontRect(x+8,y+d+1,22,w-16,25,'#b3c6aa');break;
 case 'tv':box(x+12,y+6,w-24,d-8,24,'#ac9479');box(x+w/2-4,y+10,8,8,24,'#536b78',24);box(x,y,w,12,72,c,45);frontRect(x+6,y+13,51,w-12,60,'#20384b');frontRect(x+14,y+14,59,w-28,43,'#7598ab');for(let i=0;i<3;i++)frontRect(x+20+i*32,y+15,64,23,28,['#d8bd8b','#9bbca8','#af9dbd'][i]);break;
 case 'car':{
 // Separate tires on vertical side planes, rather than axles across the body.
 const wheel=(xx,yy)=>{const ring=(radius,color)=>polygon(Array.from({length:24},(_,i)=>{const t=i*Math.PI/12;return project(xx+Math.cos(t)*radius,yy,10+Math.sin(t)*radius);}),color);ring(10,'#303a45');ring(5,'#aebbc0');ring(2,'#536672');};
 wheel(x+w*.23,y+2);wheel(x+w*.77,y+2);
 box(x+2,y+2,w-4,d-4,15,c,12);box(x+3,y+3,w-6,d-6,5,shade(c,12),27);
 box(x+w*.27,y+5,w*.43,d-10,17,c,32);
 frontRect(x+w*.30,y+d-4,35,w*.16,11,'#658c9c');frontRect(x+w*.49,y+d-4,35,w*.17,11,'#658c9c');
 polygon([project(x+w*.70,y+6,33),project(x+w*.70,y+d-6,33),project(x+w*.70,y+d-6,46),project(x+w*.70,y+6,46)],'#90b7c4');
 wheel(x+w*.23,y+d);wheel(x+w*.77,y+d);
 box(x+1,y+5,3,d-10,5,'#c3c9c4',14);box(x+w-4,y+5,3,d-10,5,'#c3c9c4',14);
 frontRect(x+5,y+d+1,22,8,4,'#bf776e');frontRect(x+w-13,y+d+1,22,8,4,'#f0deb0');break;}

 case 'bus_stop':box(x,y,w,d,6,'#c4cbbd');for(const xx of [x+8,x+w-16])box(xx,y+8,7,7,h-10,'#657e86');box(x-8,y-10,w+16,d+20,9,c,h-10);box(x+10,y+10,w-25,5,h-18,'#aecbd166');box(x+w-58,y+14,44,6,75,'#eee2c5',35);for(let n=0;n<4;n++)frontRect(x+w-53,y+21,43+n*12,33,2,'#9bb4a7');box(x+24,y+32,w-95,20,6,'#ba9c7c',26);break;
 default:box(x,y,w,d,h,c);
 }
}

function interiorBase(layout,b,a){const {g,box,polygon,tile,frontRect,project}=a,home=['house','apartments','hotel'].includes(b.kind),floor=layout.floor||'#d4c5ae';
 polygon(tile(40,40,1020,780,-14),'#718d8b');polygon(tile(50,50,1000,760),floor);
 const floorPoints=tile(50,50,1000,760);g.save();g.beginPath();floorPoints.forEach((p,n)=>n?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.closePath();g.clip();
 if((layout.pattern|| (home?'wood':'tiles'))==='wood'){for(let y=50;y<810;y+=35)for(let x=50-(Math.round(y/35)%2)*90;x<1050;x+=180)polygon(tile(x,y,178,34),a.shade(floor,((Math.round(x/180)+Math.round(y/35))%3)*4),'#8c76572b');}
 else if(layout.pattern!=='plain')for(let y=50;y<810;y+=65)for(let x=50;x<1050;x+=100)polygon(tile(x,y,99,64),a.shade(floor,(Math.round(x/100)+Math.round(y/65))%2?(layout.pattern==='checker'?-24:7):0),'#a29e8b33');
 g.restore();box(45,45,1010,12,156,layout.wall||'#ece7d9');box(45,45,12,770,156,layout.accent||b.color);box(57,57,995,5,9,'#a5aca0');box(57,57,5,748,9,'#8ca096');
 for(let x=150;x<900;x+=270){frontRect(x-6,59,42,166,103,'#d6d7c8');frontRect(x,61,48,154,90,a.night?'#597c95':'#a6c9cf');frontRect(x+74,62,48,5,90,'#f5eddd');frontRect(x,62,87,154,4,'#f5eddd');box(x-12,55,177,20,7,'#eee2cc',40);}
 const picture=project(70,370,109);g.fillStyle='#c6ac82';g.fillRect(picture.x-29,picture.y-42,58,49);g.fillStyle='#e6d6b7';g.fillRect(picture.x-24,picture.y-37,48,39);g.fillStyle=b.color;g.fillRect(picture.x-18,picture.y-30,18,25);g.fillStyle='#8daca1';g.beginPath();g.arc(picture.x+10,picture.y-18,11,0,7);g.fill();
 polygon(tile(450,720,200,66),'#a4bcb1');polygon(tile(457,727,186,52),'#c5d0b9');
 box(470,804,10,10,103,'#7b9890');box(620,804,10,10,103,'#7b9890');box(470,804,160,10,10,'#b8cabc',103);if(a.doorOpen){box(480,735,8,70,95,'#8eaeab',8);}else{frontRect(486,815,8,128,87,'#7fa6ac');frontRect(493,816,16,113,70,a.night?'#718fa3':'#a9c9cc');frontRect(599,817,38,4,12,'#edd39c');}
 a.label('SAÍDA',550,813,130,13,'#dce8db');
}
window.townArt={drawObject,interiorBase};
})();
