import test from 'node:test';
import assert from 'node:assert/strict';
import { createDocument, workspaceReducer, EMPTY_WORKSPACE } from '../src/workspace.js';
const doc = id => createDocument({id,src:`${id}-original`,name:`${id}.png`,width:500,height:100});
const set = (s,id,key,value) => workspaceReducer(s,{type:'set',id,key,value});
const current = s => s.tabs.find(t => t.id===s.activeId);
const open = (...ids) => workspaceReducer(EMPTY_WORKSPACE,{type:'open',documents:ids.map(doc)});
const act = (s,type,id=s.activeId) => workspaceReducer(s,{type,id});

 test('opening and switching images preserves independent editor state',()=>{
  let s=open('a','b');
  s=set(s,'a','replacement','2026'); s=set(s,'a','selection',{x:1,y:2,w:3,h:4});
  s=set(s,'a','zoom',3); s=set(s,'a','candidate',{image:'preview-a'});
  s=act(s,'activate','a'); assert.equal(current(s).replacement,'2026'); assert.equal(current(s).zoom,3);
  s=act(s,'activate','b'); assert.equal(current(s).selection,null); assert.equal(current(s).candidate,null);
  s=act(s,'activate','a'); assert.equal(current(s).candidate.image,'preview-a');
 });
 test('cancel selection discards pending preview but retains adopted image and image history',()=>{
  let s=open('a'); s=set(s,'a','candidate',{image:'adopted'}); s=act(s,'adopt');
  s=set(s,'a','selection',{x:1}); s=set(s,'a','candidate',{image:'pending'}); s=act(s,'cancelSelection');
  assert.equal(current(s).selection,null); assert.equal(current(s).candidate,null);
  assert.equal(current(s).doc.base,'adopted'); assert.deepEqual(current(s).history,['a-original']);
 });
 test('adopted modifications can be undone and redone multiple times without changing other tabs',()=>{
  let s=open('a','b'); s=act(s,'activate','a');
  for(const image of ['edit1','edit2']){s=set(s,'a','candidate',{image});s=act(s,'adopt');}
  s=act(s,'undo'); assert.equal(current(s).doc.base,'edit1');
  s=act(s,'undo'); assert.equal(current(s).doc.base,'a-original');
  s=act(s,'redo'); assert.equal(current(s).doc.base,'edit1');
  s=act(s,'redo'); assert.equal(current(s).doc.base,'edit2');
  assert.equal(s.tabs[1].doc.base,'b-original'); assert.deepEqual(s.tabs[1].history,[]);
 });
 test('undoing a preview can be redone, including its input and original OCR cache',()=>{
  let s=open('a'); s=set(s,'a','candidate',{image:'preview'}); s=set(s,'a','originalText','2025');
  s=set(s,'a','selection',{x:1,y:2,w:40,h:30}); s=set(s,'a','ocr',{status:'done'});
  s=act(s,'undo'); assert.equal(current(s).candidate,null);
  s=act(s,'redo'); assert.equal(current(s).candidate.image,'preview');
  assert.equal(current(s).originalText,'2025'); assert.equal(current(s).selection.w,40);
  assert.equal(current(s).ocr.status,'done');
 });
 test('new editing branch clears redo',()=>{
  let s=open('a'); s=set(s,'a','candidate',{image:'edit1'}); s=act(s,'adopt'); s=act(s,'undo');
  assert.equal(current(s).future.length,1);
  s=act(s,'invalidate'); assert.equal(current(s).future.length,0);
  s=set(s,'a','candidate',{image:'edit2'}); s=act(s,'adopt'); s=act(s,'redo');
  assert.equal(current(s).doc.base,'edit2');
 });
 test('closing tabs selects a neighbour and handles the last tab',()=>{
  let s=open('a','b','c');s=act(s,'activate','b');s=act(s,'close','b');
  assert.equal(s.activeId,'c');s=act(s,'close','a');assert.equal(s.activeId,'c');
  s=act(s,'close','c');assert.equal(s.activeId,null);assert.equal(s.tabs.length,0);
 });
 test('late asynchronous results cannot recreate a closed tab or update another one',()=>{
  let s=open('a','b');s=act(s,'close','a');s=set(s,'a','candidate',{image:'late'});
  assert.equal(s.tabs.length,1);assert.equal(current(s).candidate,null);
 });
