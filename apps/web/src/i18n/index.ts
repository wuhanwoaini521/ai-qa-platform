import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

/**
 * Translation resources are loaded from `locales/<language>/<namespace>.json`.
 *
 * The glob keeps the resource map out of this file on purpose: adding a namespace means adding two
 * files, not editing a central registry (which every feature would otherwise have to touch).
 */
const modules = import.meta.glob<Record<string, unknown>>('./locales/*/*.json', { eager: true });

export const SUPPORTED_LANGUAGES = [
  { code: 'zh-CN', label: '中文' },
  { code: 'en', label: 'English' },
] as const;

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]['code'];

const LANGUAGE_STORAGE_KEY = 'ai-qa.language';
export const DEFAULT_LANGUAGE: LanguageCode = 'zh-CN';

function buildResources(): Record<string, Record<string, Record<string, unknown>>> {
  const resources: Record<string, Record<string, Record<string, unknown>>> = {};
  for (const [path, module] of Object.entries(modules)) {
    const match = /\.\/locales\/([^/]+)\/([^/]+)\.json$/.exec(path);
    if (!match) {
      continue;
    }
    const [, language, namespace] = match;
    resources[language] ??= {};
    resources[language][namespace] = module as Record<string, unknown>;
  }
  return resources;
}

export function readStoredLanguage(): LanguageCode {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (stored && SUPPORTED_LANGUAGES.some((entry) => entry.code === stored)) {
      return stored as LanguageCode;
    }
  } catch {
    /* storage unavailable: fall through to the default */
  }
  return DEFAULT_LANGUAGE;
}

export function storeLanguage(language: LanguageCode): void {
  try {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch {
    /* storage unavailable: the choice only lasts for this session */
  }
}

void i18n.use(initReactI18next).init({
  resources: buildResources(),
  lng: readStoredLanguage(),
  fallbackLng: 'en',
  defaultNS: 'common',
  ns: ['common'],
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
