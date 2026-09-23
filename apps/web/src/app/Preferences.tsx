import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import i18n, { DEFAULT_LANGUAGE, LanguageCode, SUPPORTED_LANGUAGES, storeLanguage } from '../i18n';

/** Start pages a user can pick; the paths must stay in sync with the router table. */
export const START_PAGE_OPTIONS = [
  // Keys carry their namespace so they resolve from the settings page's own namespace.
  { path: '/', labelKey: 'nav:dashboard' },
  { path: '/projects', labelKey: 'nav:projects' },
  { path: '/test-cases', labelKey: 'nav:testCases' },
  { path: '/runs', labelKey: 'nav:runs' },
  { path: '/failures', labelKey: 'nav:failures' },
  { path: '/quality', labelKey: 'nav:quality' },
] as const;

export interface UiPreferences {
  language: LanguageCode;
  startPage: string;
  /** `null` means "keep using the last selected project". */
  defaultProjectId: string | null;
}

const PREFERENCES_STORAGE_KEY = 'ai-qa.ui-preferences';

const DEFAULT_PREFERENCES: UiPreferences = {
  language: DEFAULT_LANGUAGE,
  startPage: '/',
  defaultProjectId: null,
};

interface PreferencesValue extends UiPreferences {
  setLanguage: (language: LanguageCode) => void;
  setStartPage: (path: string) => void;
  setDefaultProjectId: (projectId: string | null) => void;
  reset: () => void;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

function readStoredPreferences(): UiPreferences {
  try {
    const raw = window.localStorage.getItem(PREFERENCES_STORAGE_KEY);
    if (!raw) {
      return DEFAULT_PREFERENCES;
    }
    const parsed = JSON.parse(raw) as Partial<UiPreferences>;
    const language = SUPPORTED_LANGUAGES.some((entry) => entry.code === parsed.language)
      ? (parsed.language as LanguageCode)
      : DEFAULT_PREFERENCES.language;
    return {
      language,
      startPage: typeof parsed.startPage === 'string' ? parsed.startPage : DEFAULT_PREFERENCES.startPage,
      defaultProjectId:
        typeof parsed.defaultProjectId === 'string' ? parsed.defaultProjectId : DEFAULT_PREFERENCES.defaultProjectId,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export const PreferencesProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [preferences, setPreferences] = useState<UiPreferences>(() => readStoredPreferences());

  // Keep i18next and the stored preference in step, whichever one changed first.
  useEffect(() => {
    if (i18n.resolvedLanguage !== preferences.language) {
      void i18n.changeLanguage(preferences.language);
    }
    storeLanguage(preferences.language);
    try {
      window.localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      /* storage unavailable: preferences last for this session only */
    }
  }, [preferences]);

  const update = useCallback((changes: Partial<UiPreferences>) => {
    setPreferences((prev) => ({ ...prev, ...changes }));
  }, []);

  const value = useMemo<PreferencesValue>(
    () => ({
      ...preferences,
      setLanguage: (language) => update({ language }),
      setStartPage: (startPage) => update({ startPage }),
      setDefaultProjectId: (defaultProjectId) => update({ defaultProjectId }),
      reset: () => setPreferences(DEFAULT_PREFERENCES),
    }),
    [preferences, update]
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
};

export function usePreferences(): PreferencesValue {
  const value = useContext(PreferencesContext);
  if (!value) {
    throw new Error('usePreferences must be used inside <PreferencesProvider>');
  }
  return value;
}
