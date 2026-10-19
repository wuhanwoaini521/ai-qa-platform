import test from 'node:test';
import assert from 'node:assert/strict';

const { analysisStageStatus, terminalAnalysisMessage } = await import(
  '../src/features/workspace/analysisLifecycleModel.ts'
);

const analysis = (status, events) => ({ id: 'a1', status, events, created_at: '2026-10-19T04:00:00Z' });

test('a completed analysis reports no error after a reload', () => {
  const completed = analysis('COMPLETED', [{ event_id: 'e1', type: 'run.completed' }]);
  assert.equal(terminalAnalysisMessage(completed, 'failed', 'incomplete'), '');
  assert.equal(
    analysisStageStatus({ running: false, cancelled: false, error: '', succeeded: true }),
    'SUCCEEDED',
  );
});

test('a running analysis keeps its progress instead of an error', () => {
  const running = analysis('RUNNING', [{ event_id: 'e1', type: 'model.started', message: '生成根因' }]);
  assert.equal(terminalAnalysisMessage(running, 'failed', 'incomplete'), '');
  assert.equal(analysisStageStatus({ running: true, cancelled: false, error: '', succeeded: false }), 'RUNNING');
});

test('a cancelled analysis explains itself and is not labelled as failed', () => {
  const cancelled = analysis('CANCELLED', [
    { event_id: 'e1', type: 'run.started' },
    { event_id: 'e2', type: 'run.cancelled', message: '分析已取消，未执行修复或复测' },
  ]);
  assert.equal(terminalAnalysisMessage(cancelled, 'failed', 'incomplete'), '分析已取消，未执行修复或复测');
  assert.equal(
    analysisStageStatus({ running: false, cancelled: true, error: '分析已取消，未执行修复或复测', succeeded: false }),
    'CANCELLED',
  );
  assert.equal(
    analysisStageStatus({ running: true, cancelled: false, error: '', succeeded: false }),
    'RUNNING',
  );
});

test('a timed out analysis surfaces the timeout reason and stays retryable as failed', () => {
  const timedOut = analysis('TIMEOUT', [{ event_id: 'e1', type: 'run.timeout', message: '分析超过 300 秒未完成，已终止；可以重试。' }]);
  assert.equal(terminalAnalysisMessage(timedOut, 'failed', 'incomplete'), '分析超过 300 秒未完成，已终止；可以重试。');
  assert.equal(
    analysisStageStatus({ running: false, cancelled: false, error: '分析超过 300 秒未完成，已终止；可以重试。', succeeded: false }),
    'FAILED',
  );
});

test('a failed analysis without a terminal message falls back to the generic failure text', () => {
  assert.equal(terminalAnalysisMessage(analysis('FAILED', []), '失败了吗', 'incomplete'), '失败了吗');
  assert.equal(terminalAnalysisMessage(analysis('INTERRUPTED', []), 'failed', '连接中断'), '连接中断');
  assert.equal(
    analysisStageStatus({ running: false, cancelled: false, error: '', succeeded: false }),
    'NOT_STARTED',
  );
});
