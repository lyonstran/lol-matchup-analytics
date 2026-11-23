import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base './' makes every asset path relative, so the same build works locally
// and at https://lyonstran.github.io/lol-matchup-analytics/ without changes.
// No API proxy anymore: the app reads the JSON files in public/data/.
export default defineConfig({
  plugins: [react()],
  base: './',
})
