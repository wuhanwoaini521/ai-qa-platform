import { RefObject, useRef, useState } from 'react';
import { AITraceEvent, QAChatAction } from '../../../types';
import { api } from '../../../api/client';
import { MonacoEditorInstance } from '../components/MonacoEditorPane';
import { errorText } from '../errorText';
import { AssistantActionType, AssistantMessage, EditorTab } from '../types';

interface UseQAAssistantOptions {
  projectId: string | null;
  /** Currently open file, used as grounding context and as the insertion target. */
  activeTab: EditorTab | undefined;
  /** Imperative handle used to insert a snippet at the caret. */
  editorRef: RefObject<MonacoEditorInstance | null>;
  /** Used when the editor has no selection and no imperative handle is available. */
  onInsertFallback: (content: string) => void;
}

export const useQAAssistant = ({
  projectId,
  activeTab,
  editorRef,
  onInsertFallback,
}: UseQAAssistantOptions) => {
  const actionMap: Record<AssistantActionType, QAChatAction> = {
    chat: 'chat',
    explain: 'explain',
    generate: 'generate_draft',
    refactor: 'suggest_refactor',
    diagnose: 'analyze_error',
  };
  // QA Assistant Sidecar State
  const [assistantMessages, setAssistantMessages] = useState<AssistantMessage[]>([]);
  const [assistantInput, setAssistantInput] = useState<string>('');
  const [assistantLoading, setAssistantLoading] = useState<boolean>(false);
  const [assistantTraceEvents, setAssistantTraceEvents] = useState<AITraceEvent[]>([]);
  const controllerRef = useRef<AbortController | null>(null);

  // QA Assistant message handling
  const sendMessage = async (customPrompt?: string, actionType?: AssistantActionType) => {
    const text = customPrompt || assistantInput.trim();
    if (!text || assistantLoading) return;

    const userMsg = { role: 'user' as const, text };
    setAssistantMessages((prev) => [...prev, userMsg, { role: 'assistant', text: '' }]);
    if (!customPrompt) setAssistantInput('');
    setAssistantLoading(true);
    setAssistantTraceEvents([]);
    const controller = new AbortController();
    controllerRef.current = controller;
    let terminalEventSeen = false;
    let partialText = '';
    const selection = editorRef.current?.getSelection();
    const selectedCode = selection && !selection.isEmpty() ? editorRef.current?.getModel()?.getValueInRange(selection) : activeTab?.content;

    try {
      await api.streamQAAssistant({
        action: actionMap[actionType || 'chat'],
        message: text,
        context: {
          project_id: projectId || '',
          current_file: activeTab?.path,
          selected_code: selectedCode,
        },
      }, (event) => {
        setAssistantTraceEvents((prev) => [...prev, event]);
        if (event.type === 'run.completed' || event.type === 'run.failed' || event.type === 'run.cancelled') terminalEventSeen = true;
        if (event.type === 'model.delta' && event.content) {
          partialText += event.content;
          setAssistantMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === 'assistant') next[next.length - 1] = { ...last, text: partialText };
            return next;
          });
        }
      }, controller.signal);
      if (!terminalEventSeen && !controller.signal.aborted) {
        setAssistantTraceEvents((prev) => [...prev, interruptedEvent(prev, 'connection_interrupted')]);
      }
    } catch (err) {
      if (controller.signal.aborted) {
        setAssistantTraceEvents((prev) => [...prev, interruptedEvent(prev, 'run.cancelled')]);
      } else if (!terminalEventSeen) {
        setAssistantTraceEvents((prev) => [...prev, interruptedEvent(prev, `Connection interrupted: ${errorText(err)}`)]);
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      setAssistantLoading(false);
    }
  };

  const cancelStream = () => controllerRef.current?.abort();

  const insertSnippet = (snippet: string) => {
    if (!activeTab || !editorRef.current) return;
    const selection = editorRef.current.getSelection();
    if (selection) {
      editorRef.current.executeEdits('assistant', [
        {
          range: selection,
          text: snippet,
          forceMoveMarkers: true,
        },
      ]);
    } else {
      onInsertFallback(activeTab.content + '\n' + snippet);
    }
  };

  return {
    assistantMessages,
    assistantInput,
    setAssistantInput,
    assistantLoading,
    assistantTraceEvents,
    sendMessage,
    cancelStream,
    insertSnippet,
  };
};

function interruptedEvent(events: AITraceEvent[], message: string): AITraceEvent {
  const runId = events[0]?.run_id ?? 'local-cancelled-run';
  return {
    run_id: runId,
    event_id: `local-${Date.now()}`,
    type: message === 'run.cancelled' ? 'run.cancelled' : 'run.failed',
    timestamp: new Date().toISOString(),
    stage: 'run',
    title: message === 'run.cancelled' ? '已取消' : '连接中断，已保留部分回答',
    message: message === 'run.cancelled' ? '' : message,
    metadata: {},
  };
}
