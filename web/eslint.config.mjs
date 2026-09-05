import { defineConfig, globalIgnores } from 'eslint/config';
import js from '@eslint/js';
import ts from 'typescript-eslint';
import hooks from 'eslint-plugin-react-hooks';

const eslintConfig = defineConfig([
  globalIgnores(['dist/**', '.next/**', '.vinext/**', 'out/**', 'build/**', 'next-env.d.ts']),
  js.configs.recommended,
  ...ts.configs.recommended,
  { files: ['app/**/*.{ts,tsx}'], ...hooks.configs.flat.recommended },
]);

export default eslintConfig;
