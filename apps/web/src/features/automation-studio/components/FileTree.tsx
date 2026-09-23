import React from 'react';
import { useTranslation } from 'react-i18next';
import {
  Braces,
  ChevronDown,
  ChevronRight,
  Edit2,
  File,
  FileCode2,
  FileText,
  FlaskConical,
  Folder,
  FolderOpen,
  Plus,
  SlidersHorizontal,
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

/** Visual vocabulary of the tree; drives both the icon chip and the depth guides. */
type TreeKind = 'folder' | 'test' | 'config' | 'python' | 'markdown' | 'json' | 'asset';

const BASE_INDENT = 8;
const INDENT_STEP = 12;
/** Reserves the chevron column so a file icon lines up with a sibling folder icon. */
const CHEVRON_GUTTER = 14;

const CONFIG_FILES: Record<string, true> = {
  'pyproject.toml': true,
  'pytest.ini': true,
  'setup.cfg': true,
  '.qa-platform.yaml': true,
  '.gitignore': true,
};
const CONFIG_EXTENSIONS: Record<string, true> = { cfg: true, toml: true };
const TEST_DIRECTORIES: Record<string, true> = { tests: true, test: true };

const fileKind = (name: string, path: string): Exclude<TreeKind, 'folder'> => {
  if (CONFIG_FILES[name]) return 'config';
  const extension = name.slice(name.lastIndexOf('.') + 1).toLowerCase();
  if (CONFIG_EXTENSIONS[extension]) return 'config';
  if (extension === 'py') {
    const directories = path.split('/').slice(0, -1);
    if (directories.some((directory) => TEST_DIRECTORIES[directory.toLowerCase()])) return 'test';
    return name.startsWith('test_') || name.endsWith('_test.py') ? 'test' : 'python';
  }
  if (extension === 'md') return 'markdown';
  if (extension === 'json') return 'json';
  return 'asset';
};

interface KindIconProps {
  kind: TreeKind;
  expanded: boolean;
}

const KindIcon: React.FC<KindIconProps> = ({ kind, expanded }) => {
  switch (kind) {
    case 'folder':
      return expanded ? <FolderOpen size={14} /> : <Folder size={14} />;
    case 'test':
      return <FlaskConical size={14} />;
    case 'config':
      return <SlidersHorizontal size={14} />;
    case 'python':
      return <FileCode2 size={14} />;
    case 'markdown':
      return <FileText size={14} />;
    case 'json':
      return <Braces size={14} />;
    default:
      return <File size={14} />;
  }
};

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
  const { t } = useTranslation('studioShell');

  // Render file tree recursively
  const renderFileTree = (nodes: FileNode[], depth = 0): React.ReactNode => {
    return nodes.map((node) => {
      const isDir = node.type === 'directory';
      const isExpanded = !!expandedFolders[node.path];
      const isSelected = activeTabPath === node.path;
      const kind: TreeKind = isDir ? 'folder' : fileKind(node.name, node.path);
      const indent = BASE_INDENT + depth * INDENT_STEP;

      return (
        <React.Fragment key={node.path}>
          <div
            className={`tree-node${isDir ? ' is-folder' : ''}${isSelected ? ' is-active' : ''}`}
            style={{ paddingLeft: `${isDir ? indent : indent + CHEVRON_GUTTER}px` }}
            onClick={() => (isDir ? onToggleFolder(node.path) : onOpenFile(node.path))}
          >
            {/* One 1px rail per ancestor level: nesting stays readable without heavy indentation. */}
            {Array.from({ length: depth }, (_, level) => (
              <span
                key={level}
                className="tree-depth-guide"
                style={{ left: `${BASE_INDENT + level * INDENT_STEP}px` }}
              />
            ))}
            {isDir && (isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
            <span className={`tree-icon ${kind}`}>
              <KindIcon kind={kind} expanded={isExpanded} />
            </span>
            <span className="tree-label">{node.name}</span>
            {kind === 'test' && node.name.endsWith('.py') && (
              <span className="tree-badge">{t('fileTree.pythonTestBadge')}</span>
            )}
            <div className="tree-actions" onClick={(e) => e.stopPropagation()}>
              {isDir ? (
                <button
                  className="icon-btn"
                  title={t('fileTree.newFileInside')}
                  onClick={() => onCreateFileInside(node.path)}
                >
                  <Plus size={11} />
                </button>
              ) : (
                <>
                  <button className="icon-btn" title={t('fileTree.rename')} onClick={() => onRename(node.path)}>
                    <Edit2 size={11} />
                  </button>
                  <button className="icon-btn" title={t('common:delete')} onClick={() => onDelete(node.path)}>
                    <Trash2 size={11} color="#ef4444" />
                  </button>
                </>
              )}
            </div>
          </div>
          {isDir && isExpanded && node.children && renderFileTree(node.children, depth + 1)}
        </React.Fragment>
      );
    });
  };

  if (files.length === 0) {
    return (
      <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
        <p style={{ marginBottom: '10px' }}>{t('fileTree.uninitialized')}</p>
        <button className="btn btn-primary btn-sm" onClick={onBootstrapWorkspace}>
          {t('fileTree.initializeWorkspace')}
        </button>
      </div>
    );
  }

  return <>{renderFileTree(files)}</>;
};
