import React from 'react';
import {
  ChevronDown,
  ChevronRight,
  Edit2,
  FileCode,
  FileText,
  Folder,
  FolderOpen,
  Plus,
  Trash2,
} from 'lucide-react';
import { FileNode } from '../../../types';

interface FileTreeProps {
  files: FileNode[];
  expandedFolders: Record<string, boolean>;
  activeTabPath: string | null;
  onToggleFolder: (path: string) => void;
  onOpenFile: (path: string) => void;
  onCreateFileInside: (dirPath: string) => void;
  onRename: (path: string) => void;
  onDelete: (path: string) => void;
  onBootstrapWorkspace: () => void;
}

export const FileTree: React.FC<FileTreeProps> = ({
  files,
  expandedFolders,
  activeTabPath,
  onToggleFolder,
  onOpenFile,
  onCreateFileInside,
  onRename,
  onDelete,
  onBootstrapWorkspace,
}) => {
  // Render file tree recursively
  const renderFileTree = (nodes: FileNode[], depth = 0): React.ReactNode => {
    return nodes.map((node) => {
      const isDir = node.type === 'directory';
      const isExpanded = !!expandedFolders[node.path];
      const isSelected = activeTabPath === node.path;

      if (isDir) {
        return (
          <div key={node.path}>
            <div
              className="tree-node"
              style={{ paddingLeft: `${8 + depth * 14}px`, justifyContent: 'space-between' }}
              onClick={() => onToggleFolder(node.path)}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                {isExpanded ? <FolderOpen size={14} color="#3b82f6" /> : <Folder size={14} color="#3b82f6" />}
                <span style={{ fontSize: '12px' }}>{node.name}</span>
              </div>
              <div className="tree-actions" onClick={(e) => e.stopPropagation()}>
                <button
                  className="icon-btn"
                  title="New File Inside"
                  onClick={() => onCreateFileInside(node.path)}
                >
                  <Plus size={11} />
                </button>
              </div>
            </div>
            {isExpanded && node.children && <div>{renderFileTree(node.children, depth + 1)}</div>}
          </div>
        );
      }

      return (
        <div
          key={node.path}
          className={`tree-node ${isSelected ? 'active' : ''}`}
          style={{ paddingLeft: `${22 + depth * 14}px`, justifyContent: 'space-between' }}
          onClick={() => onOpenFile(node.path)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden' }}>
            {node.name.endsWith('.py') ? (
              <FileCode size={14} color="#10b981" />
            ) : (
              <FileText size={14} color="#64748b" />
            )}
            <span style={{ fontSize: '12px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {node.name}
            </span>
          </div>
          <div className="tree-actions" onClick={(e) => e.stopPropagation()}>
            <button className="icon-btn" title="Rename" onClick={() => onRename(node.path)}>
              <Edit2 size={11} />
            </button>
            <button className="icon-btn" title="Delete" onClick={() => onDelete(node.path)}>
              <Trash2 size={11} color="#ef4444" />
            </button>
          </div>
        </div>
      );
    });
  };

  if (files.length === 0) {
    return (
      <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
        <p style={{ marginBottom: '10px' }}>Workspace is uninitialized.</p>
        <button className="btn btn-primary btn-sm" onClick={onBootstrapWorkspace}>
          Initialize Workspace
        </button>
      </div>
    );
  }

  return <>{renderFileTree(files)}</>;
};
