import React from 'react';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';

interface QuickOpenProps {
  files: string[];
  query: string;
  selectedIndex: number;
  onQueryChange: (value: string) => void;
  onSelectedIndexChange: React.Dispatch<React.SetStateAction<number>>;
  onSelect: (path: string) => void;
  onClose: () => void;
}

export const QuickOpen: React.FC<QuickOpenProps> = ({
  files,
  query,
  selectedIndex,
  onQueryChange,
  onSelectedIndexChange,
  onSelect,
  onClose,
}) => {
  const { t } = useTranslation('studioShell');
  // Filtered files for Quick Open
  const filteredQuickFiles = files.filter((p) =>
    p.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-dialog"
        style={{ maxWidth: '480px', marginTop: '-150px' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: '12px', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Search size={16} color="#64748b" />
          <input
            autoFocus
            type="text"
            className="form-control"
            style={{ border: 'none', boxShadow: 'none', padding: '4px', fontSize: '14px' }}
            placeholder={t('quickOpen.placeholder')}
            value={query}
            onChange={(e) => {
              onQueryChange(e.target.value);
              onSelectedIndexChange(0);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') onClose();
              if (e.key === 'ArrowDown') {
                e.preventDefault();
                onSelectedIndexChange((prev) =>
                  Math.min(prev + 1, filteredQuickFiles.length - 1)
                );
              }
              if (e.key === 'ArrowUp') {
                e.preventDefault();
                onSelectedIndexChange((prev) => Math.max(prev - 1, 0));
              }
              if (e.key === 'Enter' && filteredQuickFiles[selectedIndex]) {
                onSelect(filteredQuickFiles[selectedIndex]);
              }
            }}
          />
        </div>
        <div style={{ maxHeight: '280px', overflowY: 'auto', padding: '6px' }}>
          {filteredQuickFiles.length === 0 ? (
            <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '12px' }}>
              {t('quickOpen.noMatches')}
            </div>
          ) : (
            filteredQuickFiles.map((p, idx) => (
              <div
                key={p}
                style={{
                  padding: '8px 12px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontFamily: 'var(--font-mono)',
                  background: idx === selectedIndex ? '#eff6ff' : 'transparent',
                  color: idx === selectedIndex ? '#2563eb' : '#334155',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
                onClick={() => onSelect(p)}
              >
                <span>{p}</span>
                <span style={{ fontSize: '10px', color: '#94a3b8' }}>{t('quickOpen.fileLabel')}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
