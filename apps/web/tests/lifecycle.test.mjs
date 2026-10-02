import test from 'node:test';
import assert from 'node:assert/strict';
import {visibleGraph,layoutGraph} from '../src/features/lifecycle/graphModel.ts';
import {rememberEntity,recallEntity} from '../src/features/lifecycle/contextMemory.ts';

const nodes=[{id:'req',kind:'requirement',label:'REQ-001',summary:'Purchase',status:'READY'},
  {id:'ac',kind:'criteria',label:'AC-004',summary:'Cart amount',status:''},
  {id:'case',kind:'case',label:'TC-004',summary:'Add to cart',status:'PASSED'}];
const graph={nodes,edges:[{source:'req',target:'ac',relation:'contains'},{source:'ac',target:'case',relation:'covered_by'}]};

test('search and kind filtering retain only edges between visible nodes',()=>{
  const value=visibleGraph(graph,'cart','',new Set());
  assert.deepEqual(value.nodes.map(n=>n.id),['ac','case']);
  assert.equal(value.edges.length,1);
  assert.equal(visibleGraph(graph,'','case',new Set()).edges.length,0);
});
test('branch collapsing hides owned children without hiding shared case references',()=>{
  const value=visibleGraph(graph,'','',new Set(['req']));
  assert.deepEqual(value.nodes.map(n=>n.id),['req','case']);
  assert.equal(value.edges.length,0);
});
test('layout gives visible nodes distinct positions',()=>{
  const layout=layoutGraph(nodes);
  assert.equal(new Set([...layout.positions.values()].map(p=>`${p.x},${p.y}`)).size,3);
});
test('remembered entities are scoped by project and unavailable storage is safe',()=>{
  const values=new Map();globalThis.sessionStorage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v)};
  rememberEntity('one','case','TC-004');rememberEntity('two','case','TC-009');
  assert.equal(recallEntity('one','case'),'TC-004');assert.equal(recallEntity('two','case'),'TC-009');
  delete globalThis.sessionStorage;assert.equal(recallEntity('one','case'),null);
});
