import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

// Exercise the real engine's geometry and async gates without a browser or LLM.
const window = {innerWidth:1000, innerHeight:800};
vm.runInNewContext(readFileSync(new URL('../web/guided-tour.js',import.meta.url),'utf8'),
  {window, document:{}, setInterval, clearInterval});
const Guide = window.GuidedTour;
const guide = new Guide();
const frame = {getBoundingClientRect:()=>({left:100,top:70}), ownerDocument:{defaultView:window}};
const child = {innerWidth:800,innerHeight:600,frameElement:frame};
const rect = guide.rectangle({ownerDocument:{defaultView:child},getBoundingClientRect:()=>({left:20,top:30,right:220,bottom:130})});
assert.deepEqual({...rect},{left:120,top:100,right:320,bottom:200,width:200,height:100});
const clipped = guide.rectangle({ownerDocument:{defaultView:child},getBoundingClientRect:()=>({left:-30,top:-20,right:900,bottom:650})});
assert.equal(clipped.left,100); assert.equal(clipped.top,70); assert.equal(clipped.right,900); assert.equal(clipped.bottom,670);
let ready=false, busy=false;
const hint={}, next={}, visited=[];
Object.assign(guide,{active:true,index:0,wasReady:false,steps:[{ready:()=>ready,busy:()=>busy,auto:true,wait:'Espera una fuente',target:()=>null},{}],
  layer:{querySelector:()=>hint,style:{}}, next, ring:{style:{}},card:{style:{},offsetWidth:350,offsetHeight:300}});
guide.show = index => visited.push(index);
guide.tick(); assert.equal(next.disabled,true); assert.equal(hint.textContent,'Espera una fuente'); assert.equal(visited.length,0);
ready=true; busy=true;
guide.tick(); assert.equal(next.disabled,true); assert.equal(visited.length,0);
busy=false;
guide.tick(); assert.deepEqual(visited,[1]);
visited.length=0; guide.wasReady=true;
guide.tick(); assert.equal(next.disabled,false); assert.equal(visited.length,0);
ready=false;
guide.tick(); assert.equal(next.disabled,true); assert.equal(visited.length,0);
console.log('PASS: iframe coordinates, viewport clipping, prerequisites, busy waits and successful auto-advance');
let modalOpen=true;
const sourceDoc={defaultView:window,querySelector:()=>modalOpen ? {} : null};
guide.steps[0].target=()=>({ownerDocument:sourceDoc,getBoundingClientRect:()=>({left:50,top:100,right:200,bottom:150})});
guide.tick(); assert.equal(guide.layer.style.visibility,'hidden');
modalOpen=false;
guide.tick(); assert.equal(guide.layer.style.visibility,'');
let closed=0;
guide.close=()=>closed++;
const escape={key:'Escape',target:{ownerDocument:sourceDoc},preventDefault(){}};
modalOpen=true; guide.keyHandler(escape); assert.equal(closed,0);
modalOpen=false; guide.keyHandler(escape); assert.equal(closed,1);
console.log('PASS: source dialog pauses the guide; Escape closes the source before the walkthrough');
