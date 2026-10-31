import test from 'node:test';
import assert from 'node:assert/strict';
import { browserFramePresentation } from '../src/features/runs/browserFrameModel.ts';

test('a browser frame is live only while its session runs and its stream is connected', () => {
  assert.equal(browserFramePresentation({
    hasStreamFrame: true,
    hasCapturedFrame: false,
    sessionStatus: 'running',
    streamStatus: 'connected',
  }), 'live');
  assert.equal(browserFramePresentation({
    hasStreamFrame: true,
    hasCapturedFrame: false,
    sessionStatus: 'running',
    streamStatus: 'reconnecting',
  }), 'lastReceived');
  assert.equal(browserFramePresentation({
    hasStreamFrame: true,
    hasCapturedFrame: false,
    sessionStatus: 'passed',
    streamStatus: 'connected',
  }), 'lastReceived');
});

test('a captured artifact is labeled as captured when no stream frame exists', () => {
  assert.equal(browserFramePresentation({
    hasStreamFrame: false,
    hasCapturedFrame: true,
    sessionStatus: 'passed',
    streamStatus: 'idle',
  }), 'lastCaptured');
  assert.equal(browserFramePresentation({
    hasStreamFrame: false,
    hasCapturedFrame: false,
    sessionStatus: 'running',
    streamStatus: 'connected',
  }), null);
});
