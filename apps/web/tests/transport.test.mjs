import test from 'node:test';
import assert from 'node:assert/strict';
import { APIError, responseError } from '../src/api/errors.ts';
import { parseEventFrame } from '../src/api/eventStream.ts';

test('structured API failures retain actionable code and request correlation', () => {
  const error = new APIError(503, {code:'AI_PROVIDER_UNAVAILABLE',message:'Unavailable',details:{retry:false},request_id:'request-123'},'Service error');
  assert.equal(error.code,'AI_PROVIDER_UNAVAILABLE'); assert.equal(error.message,'Unavailable'); assert.equal(error.requestId,'request-123'); assert.deepEqual(error.details,{retry:false});
});
test('legacy and non-JSON API errors have a safe status-based fallback', async () => {
  assert.equal(new APIError(404,{detail:'Not found'},'fallback').message,'Not found');
  const error=await responseError(new Response('proxy HTML',{status:502,statusText:'Bad Gateway'}));
  assert.equal(error.code,'HTTP_502'); assert.equal(error.message,'Bad Gateway');
});
test('SSE parser preserves multiline data, CRLF and resumable event identifiers', () => {
  assert.deepEqual(parseEventFrame(': heartbeat\r\nevent: run.progress\r\nid: 42\r\ndata: first\r\ndata: second'),{type:'run.progress',id:'42',data:'first\nsecond'});
});
test('SSE comments do not emit messages and invalid IDs cannot replace the cursor', () => {
  assert.equal(parseEventFrame(': keepalive\nretry: 1000'),null);
  assert.deepEqual(parseEventFrame('id: bad\0value\ndata: {}'),{type:'message',id:undefined,data:'{}'});
  assert.deepEqual(parseEventFrame('id:\ndata:'),{type:'message',id:'',data:''});
});
