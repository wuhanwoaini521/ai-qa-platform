import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { '@typescript-eslint': tsPlugin, 'react-hooks': reactHooks },
    rules: {
      'no-eval': 'error',
      'no-new-func': 'error',
      'no-debugger': 'error',
      'no-unreachable': 'error',
      'no-constant-condition': ['error', { checkLoops: false }],
      'no-dupe-else-if': 'error',
      'no-duplicate-case': 'error',
      'no-unsafe-finally': 'error',
      'react-hooks/rules-of-hooks': 'error',
      '@typescript-eslint/no-duplicate-enum-values': 'error',
    },
  },
  {
    files: [
      'src/features/runtime/**/*.{ts,tsx}',
      'src/features/runs/{runStore,useRunStore}.ts',
    ],
    rules: { '@typescript-eslint/no-explicit-any': 'error' },
  },
];
