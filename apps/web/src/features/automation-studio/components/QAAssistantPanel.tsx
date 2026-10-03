import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Check, Send, Sparkles, StopCircle, User } from 'lucide-react';
import { AssistantActionType, AssistantMessage } from '../types';
import { AgentTask, AITraceEvent } from '../../../types';
import { ContextTaskProgress } from '../../../components/ContextTaskProgress';
import { AIExecutionTimeline } from '../../../components/AIExecutionTimeline';

interface QAAssistantPanelProps {
  messages: AssistantMessage[];
  input: string;
  loading: boolean;
  traceEvents: AITraceEvent[];
  onInputChange: (value: string) => void;
  onSend: (customPrompt?: string, actionType?: AssistantActionType) => void;
  onCancel: () => void;
  onInsertSnippet: (snippet: string) => void;
  onStartGenerateTask: (url: string, goal: string) => void;
  generateTask: AgentTask | null;
  generateTaskBusy: boolean;
  generateTaskError: string;
}

interface MessageSegment {
  type: 'text' | 'code';
  value: string;
}

/** ```lang\n … ``` — an unterminated fence runs to the end of the reply. */
const CODE_FENCE = /```[^\n]*\n?([\s\S]*?)(?:```|$)/g;

/** Split assistant copy so generated snippets render in their own block. */
const splitMessage = (text: string): MessageSegment[] => {
  const segments: MessageSegment[] = [];
  let cursor = 0;

  CODE_FENCE.lastIndex = 0;
  for (let match = CODE_FENCE.exec(text); match; match = CODE_FENCE.exec(text)) {
    const prose = text.slice(cursor, match.index).trim();
    if (prose) segments.push({ type: 'text', value: prose });

    const code = match[1].replace(/^\n+/, '').replace(/\s+$/, '');
    if (code) segments.push({ type: 'code', value: code });

    cursor = match.index + match[0].length;
  }

  const tail = text.slice(cursor).trim();
  if (tail) segments.push({ type: 'text', value: tail });

  return segments.length > 0 ? segments : [{ type: 'text', value: text }];
};

/** Square dot: the only pixel accent used inside the stream. */
const pixelDot = (color: string, offset = false): React.CSSProperties => ({
  width: '6px',
  height: '6px',
  borderRadius: 'var(--r-xs)',
  background: color,
  flexShrink: 0,
  boxShadow: offset ? 'var(--ui-shadow-pixel)' : undefined,
});

const QUICK_ACTIONS: ReadonlyArray<{
  labelKey: string;
  prompt: string;
  actionType: AssistantActionType;
  color: string;
  Icon: typeof Sparkles;
}> = [
  {
    labelKey: 'assistant.explainCode',
    prompt: 'Explain the currently open file and test structure.',
    actionType: 'explain',
    color: 'var(--accent-blue)',
    Icon: Sparkles,
  },
  {
    labelKey: 'assistant.generateTest',
    prompt: 'Generate a Playwright test scaffold following project standards.',
    actionType: 'generate',
    color: 'var(--accent-green)',
    Icon: Sparkles,
  },
  {
    labelKey: 'assistant.refactorPo',
    prompt: 'Suggest refactoring to Page Object pattern.',
    actionType: 'refactor',
    color: 'var(--accent-amber)',
    Icon: Sparkles,
  },
  {
    labelKey: 'assistant.diagnose',
    prompt: 'Diagnose syntax and locator stability issues.',
    actionType: 'diagnose',
    color: 'var(--accent-violet)',
    Icon: AlertTriangle,
  },
];

export const QAAssistantPanel: React.FC<QAAssistantPanelProps> = ({
  messages,
  input,
  loading,
  traceEvents,
  onInputChange,
  onSend,
  onCancel,
  onInsertSnippet,
  onStartGenerateTask,
  generateTask,
  generateTaskBusy,
  generateTaskError,
}) => {
  const { t } = useTranslation('studioPanels');
  const [showGenerate, setShowGenerate] = useState(false);
  const [targetUrl, setTargetUrl] = useState('');
  const [testGoal, setTestGoal] = useState('');
  const streamRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  // Follow new tokens only while the user is already reading the bottom of the transcript.
  useEffect(() => {
    const stream = streamRef.current;
    if (stream && autoScrollRef.current) stream.scrollTop = stream.scrollHeight;
  }, [messages.length, messages[messages.length - 1]?.text, loading, traceEvents.length]);

  const handleStreamScroll = () => {
    const stream = streamRef.current;
    if (stream) autoScrollRef.current = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 72;
  };

  const renderedMessages = useMemo(
    () =>
      messages.map((msg) => {
        const segments = msg.role === 'assistant' ? splitMessage(msg.text) : [];
        const fencedCode = segments.filter((segment) => segment.type === 'code').map((segment) => segment.value);
        // A structured snippet the backend returned alongside the reply.
        const trailingSnippet =
          msg.codeSnippet && !fencedCode.some((code) => code.trim() === msg.codeSnippet?.trim())
            ? msg.codeSnippet
            : null;
        return { msg, segments, trailingSnippet };
      }),
    [messages],
  );

  const canSend = Boolean(input.trim()) && !loading;

  return (
    <div className="studio-assistant-pane">
      <header className="ai-header">
        <span className="ai-mark" aria-hidden="true">
          <Sparkles size={15} />
        </span>
        <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <span className="ai-title">{t('assistant.title')}</span>
          <span className="ai-subtitle">{t('assistant.subtitle')}</span>
        </span>
        <span className="ai-status-pill">
          <span aria-hidden="true" style={pixelDot('var(--ui-mint-strong)')} />
          {t('assistant.groundingActive')}
        </span>
      </header>

      <div className="ai-chips" role="group" aria-label={t('assistant.quickActionsLabel')}>
        {QUICK_ACTIONS.map(({ labelKey, prompt, actionType, color, Icon }) => (
          <button
            key={actionType}
            type="button"
            className="ai-chip"
            disabled={loading}
            onClick={() => actionType === 'generate' ? setShowGenerate(true) : onSend(prompt, actionType)}
          >
            <Icon size={12} color={color} />
            {t(labelKey)}
          </button>
        ))}
      </div>

      {showGenerate && <form onSubmit={(event) => {
        event.preventDefault();
        onStartGenerateTask(targetUrl.trim(), testGoal.trim());
        setShowGenerate(false);
      }} style={{ display: 'grid', gap: 8, padding: 12 }}>
        <label>{t('tasks:studioUrl')}<input type="url" value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} placeholder="https://example.com" style={{ width: '100%' }} /></label>
        <label>{t('tasks:studioGoal')}<textarea required minLength={3} value={testGoal} onChange={(event) => setTestGoal(event.target.value)} rows={3} style={{ width: '100%' }} /></label>
        <div style={{ display: 'flex', gap: 8 }}><button type="submit" className="btn btn-primary btn-sm" disabled={generateTaskBusy}>{t('tasks:studioCreate')}</button><button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowGenerate(false)}>{t('tasks:studioCancel')}</button></div>
      </form>}
      <ContextTaskProgress task={generateTask} error={generateTaskError} />

      <div className="ai-stream" ref={streamRef} onScroll={handleStreamScroll}>
        <AIExecutionTimeline events={traceEvents} running={loading} onCancel={onCancel} debugMode={import.meta.env.DEV} />
        {messages.length === 0 ? (
          <div className="ai-welcome">
            <div className="ai-welcome-mark" aria-hidden="true">
              <Sparkles size={20} />
            </div>
            <div className="ai-welcome-title">{t('assistant.welcomeTitle')}</div>
            <p className="ai-welcome-hint">{t('assistant.welcomeHintLine1')}</p>
            <p className="ai-welcome-hint">{t('assistant.welcomeHintLine2')}</p>
            <div
              aria-hidden="true"
              style={{ display: 'flex', gap: '5px', justifyContent: 'center', marginTop: 'var(--sp-4)' }}
            >
              <span style={{ ...pixelDot('var(--ui-primary)'), opacity: 0.35 }} />
              <span style={{ ...pixelDot('var(--ui-primary)'), opacity: 0.6 }} />
              <span style={pixelDot('var(--ui-primary)')} />
            </div>
          </div>
        ) : (
          renderedMessages.map(({ msg, segments, trailingSnippet }, index) => (
            <div
              key={index}
              className={`ai-message${msg.role === 'user' ? ' is-user' : ''}`}
              style={msg.role === 'user' ? { alignSelf: 'flex-end', maxWidth: '92%' } : undefined}
            >
              <div className="ai-message-role">
                {msg.role === 'user' ? <User size={11} /> : <Sparkles size={11} />}
                {msg.role === 'user' ? t('assistant.roleYou') : t('assistant.answer')}
              </div>

              {msg.role === 'user'
                ? msg.text
                : segments.map((segment, segmentIndex) =>
                    segment.type === 'code' ? (
                      <React.Fragment key={segmentIndex}>
                        <pre className="ai-code">{segment.value}</pre>
                        <button
                          type="button"
                          className="ai-snippet-action"
                          onClick={() => onInsertSnippet(segment.value)}
                        >
                          <Check size={12} /> {t('assistant.insertCode')}
                        </button>
                      </React.Fragment>
                    ) : (
                      <div key={segmentIndex}>{segment.value}</div>
                    ),
                  )}

              {trailingSnippet && (
                <>
                  <pre className="ai-code">{trailingSnippet}</pre>
                  <button
                    type="button"
                    className="ai-snippet-action"
                    onClick={() => onInsertSnippet(trailingSnippet)}
                  >
                    <Check size={12} /> {t('assistant.insertCode')}
                  </button>
                </>
              )}
            </div>
          ))
        )}

      </div>

      <div className="ai-composer">
        <form
          className="ai-composer-box"
          onSubmit={(event) => {
            event.preventDefault();
            if (canSend) onSend();
          }}
        >
          <textarea
            className="ai-input"
            rows={Math.min(4, Math.max(1, input.split('\n').length))}
            placeholder={t('assistant.placeholder')}
            aria-label={t('assistant.placeholder')}
            value={input}
            disabled={loading}
            onChange={(event) => onInputChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (canSend) onSend();
              }
            }}
          />
          <button
            type="submit"
            className="ai-send"
            disabled={!canSend}
            aria-label={t('assistant.send')}
            title={t('assistant.send')}
          >
            <Send size={14} />
          </button>
          {loading && <button type="button" className="ai-send ai-stop" onClick={onCancel} aria-label={t('assistant.cancel')} title={t('assistant.cancel')}><StopCircle size={14} /></button>}
        </form>
        <div style={{ marginTop: '6px', fontSize: '10px', color: 'var(--ui-ink-muted)' }}>
          {t('assistant.composerHint')}
        </div>
      </div>
    </div>
  );
};
