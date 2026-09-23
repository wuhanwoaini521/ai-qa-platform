import React, { useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Check, Send, Sparkles, User } from 'lucide-react';
import { AssistantActionType, AssistantMessage } from '../types';

interface QAAssistantPanelProps {
  messages: AssistantMessage[];
  input: string;
  loading: boolean;
  onInputChange: (value: string) => void;
  onSend: (customPrompt?: string, actionType?: AssistantActionType) => void;
  onInsertSnippet: (snippet: string) => void;
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
  borderRadius: '2px',
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
    color: '#2563eb',
    Icon: Sparkles,
  },
  {
    labelKey: 'assistant.generateTest',
    prompt: 'Generate a Playwright test scaffold following project standards.',
    actionType: 'generate',
    color: '#16a34a',
    Icon: Sparkles,
  },
  {
    labelKey: 'assistant.refactorPo',
    prompt: 'Suggest refactoring to Page Object pattern.',
    actionType: 'refactor',
    color: '#d97706',
    Icon: Sparkles,
  },
  {
    labelKey: 'assistant.diagnose',
    prompt: 'Diagnose syntax and locator stability issues.',
    actionType: 'diagnose',
    color: '#9333ea',
    Icon: AlertTriangle,
  },
];

export const QAAssistantPanel: React.FC<QAAssistantPanelProps> = ({
  messages,
  input,
  loading,
  onInputChange,
  onSend,
  onInsertSnippet,
}) => {
  const { t } = useTranslation('studioPanels');
  const streamRef = useRef<HTMLDivElement>(null);

  // Keep the newest turn in view; only the stream scrolls.
  useEffect(() => {
    const stream = streamRef.current;
    if (stream) stream.scrollTop = stream.scrollHeight;
  }, [messages.length, loading]);

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
            onClick={() => onSend(prompt, actionType)}
          >
            <Icon size={12} color={color} />
            {t(labelKey)}
          </button>
        ))}
      </div>

      <div className="ai-stream" ref={streamRef}>
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
                {msg.role === 'user' ? t('assistant.roleYou') : t('assistant.title')}
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

        {loading && (
          <div className="ai-thinking" style={{ alignSelf: 'flex-start' }}>
            <span aria-hidden="true" style={pixelDot('var(--ui-primary)', true)} />
            {t('assistant.reasoning')}
          </div>
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
        </form>
        <div style={{ marginTop: '6px', fontSize: '10px', color: 'var(--ui-ink-muted)' }}>
          {t('assistant.composerHint')}
        </div>
      </div>
    </div>
  );
};
