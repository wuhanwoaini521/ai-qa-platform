import React from 'react';
import { AlertTriangle, Bot, Check, Send, Sparkles } from 'lucide-react';
import { AssistantActionType, AssistantMessage } from '../types';

interface QAAssistantPanelProps {
  messages: AssistantMessage[];
  input: string;
  loading: boolean;
  onInputChange: (value: string) => void;
  onSend: (customPrompt?: string, actionType?: AssistantActionType) => void;
  onInsertSnippet: (snippet: string) => void;
}

export const QAAssistantPanel: React.FC<QAAssistantPanelProps> = ({
  messages,
  input,
  loading,
  onInputChange,
  onSend,
  onInsertSnippet,
}) => (
  <div className="studio-assistant-pane">
    <div className="studio-sidebar-header">
      <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <Bot size={14} color="#9333ea" /> QA Assistant
      </span>
      <span className="badge badge-ready" style={{ fontSize: '10px' }}>
        Grounding Active
      </span>
    </div>

    {/* Assistant Quick Actions */}
    <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-color)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
      <button
        className="btn btn-secondary btn-sm"
        style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
        disabled={loading}
        onClick={() => onSend('Explain the currently open file and test structure.', 'explain')}
      >
        <Sparkles size={12} color="#2563eb" /> Explain Code
      </button>
      <button
        className="btn btn-secondary btn-sm"
        style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
        disabled={loading}
        onClick={() => onSend('Generate a Playwright test scaffold following project standards.', 'generate')}
      >
        <Sparkles size={12} color="#16a34a" /> Generate Test
      </button>
      <button
        className="btn btn-secondary btn-sm"
        style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
        disabled={loading}
        onClick={() => onSend('Suggest refactoring to Page Object pattern.', 'refactor')}
      >
        <Sparkles size={12} color="#d97706" /> Refactor PO
      </button>
      <button
        className="btn btn-secondary btn-sm"
        style={{ fontSize: '11px', padding: '4px 6px', justifyContent: 'center' }}
        disabled={loading}
        onClick={() => onSend('Diagnose syntax and locator stability issues.', 'diagnose')}
      >
        <AlertTriangle size={12} color="#9333ea" /> Diagnose
      </button>
    </div>

    {/* Message Stream */}
    <div style={{ padding: '12px', flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {messages.map((msg, i) => (
        <div
          key={i}
          style={{
            alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '90%',
            background: msg.role === 'user' ? '#2563eb' : '#f8fafc',
            color: msg.role === 'user' ? '#ffffff' : '#1e293b',
            padding: '8px 12px',
            borderRadius: '6px',
            border: msg.role === 'user' ? 'none' : '1px solid var(--border-color)',
            fontSize: '12px',
          }}
        >
          <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{msg.text}</div>
          {msg.codeSnippet && (
            <div style={{ marginTop: '8px' }}>
              <div
                style={{
                  background: '#0f172a',
                  color: '#f8fafc',
                  padding: '8px',
                  borderRadius: '4px',
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  overflowX: 'auto',
                  maxHeight: '180px',
                }}
              >
                <pre>{msg.codeSnippet}</pre>
              </div>
              <button
                className="btn btn-secondary btn-sm"
                style={{ marginTop: '6px', width: '100%', fontSize: '11px', justifyContent: 'center' }}
                onClick={() => onInsertSnippet(msg.codeSnippet!)}
              >
                <Check size={12} /> Insert Code into Editor
              </button>
            </div>
          )}
        </div>
      ))}
      {loading && (
        <div style={{ alignSelf: 'flex-start', fontSize: '12px', color: 'var(--text-muted)', padding: '6px' }}>
          QA Assistant is reasoning...
        </div>
      )}
    </div>

    {/* Assistant Input Form */}
    <div style={{ padding: '10px', borderTop: '1px solid var(--border-color)', background: '#ffffff' }}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSend();
        }}
        style={{ display: 'flex', gap: '6px' }}
      >
        <input
          type="text"
          className="form-control"
          style={{ fontSize: '12px', padding: '6px 8px' }}
          placeholder="Ask QA assistant..."
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          disabled={loading}
        />
        <button
          type="submit"
          className="btn btn-primary btn-sm"
          disabled={!input.trim() || loading}
        >
          <Send size={13} />
        </button>
      </form>
    </div>
  </div>
);
