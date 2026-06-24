import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import astro from 'eslint-plugin-astro'
import globals from 'globals'

export default tseslint.config(
  { ignores: ['dist', '.astro'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...astro.configs.recommended,
  // Config files run under Node (they read process.env), so give them Node globals.
  {
    files: ['**/*.config.{js,cjs,mjs,ts}'],
    languageOptions: { globals: globals.node },
  },
)
