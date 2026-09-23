import { RefObject, useState } from 'react';
import { QAChatResponse } from '../../../types';
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
  // QA Assistant Sidecar State
  const [assistantMessages, setAssistantMessages] = useState<AssistantMessage[]>([
    {
      role: 'assistant',
      text: 'Hello! I am your AI QA Assistant. I can help you write Playwright & Pytest tests, explain code, diagnose test failures, or suggest locator refactorings.',
      actions: ['Explain Code', 'Generate Test', 'Suggest Refactor', 'Diagnose Errors'],
    },
  ]);
  const [assistantInput, setAssistantInput] = useState<string>('');
  const [assistantLoading, setAssistantLoading] = useState<boolean>(false);

  // QA Assistant message handling
  const sendMessage = async (customPrompt?: string, actionType?: AssistantActionType) => {
    const text = customPrompt || assistantInput.trim();
    if (!text || assistantLoading) return;

    const userMsg = { role: 'user' as const, text };
    setAssistantMessages((prev) => [...prev, userMsg]);
    if (!customPrompt) setAssistantInput('');
    setAssistantLoading(true);

    try {
      const resp: QAChatResponse = await api.askQAAssistant({
        message: text,
        project_id: projectId || undefined,
        current_file: activeTab?.path,
        selected_code: activeTab?.content,
        context_type: actionType || 'chat',
      });

      setAssistantMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: resp.reply || resp.response || '',
          codeSnippet: resp.code_snippet || resp.suggested_code,
          actions: resp.suggested_actions,
        },
      ]);
    } catch (err) {
      setAssistantMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `Error contacting QA Assistant: ${errorText(err)}`,
        },
      ]);
    } finally {
      setAssistantLoading(false);
    }
  };

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
    sendMessage,
    insertSnippet,
  };
};
