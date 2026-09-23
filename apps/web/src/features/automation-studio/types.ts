/** View-local types for the Automation Studio feature. */

export interface EditorTab {
  path: string;
  name: string;
  content: string;
  initialContent: string;
  isDirty: boolean;
}

export interface FileOpModalState {
  type: 'create_file' | 'create_folder' | 'rename' | 'delete';
  targetPath?: string;
  newName?: string;
}

export type SidebarTab = 'files' | 'tests' | 'git' | 'pr';

export interface AssistantMessage {
  role: 'user' | 'assistant';
  text: string;
  codeSnippet?: string | null;
  actions?: string[];
}

export type AssistantActionType = 'chat' | 'explain' | 'generate' | 'refactor' | 'diagnose';
