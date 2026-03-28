/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        panel: '#1e1e2e',
        surface: '#181825',
        border: '#313244',
        accent: '#89b4fa',
        success: '#a6e3a1',
        warning: '#f9e2af',
        danger: '#f38ba8',
        muted: '#6c7086',
      },
    },
  },
  plugins: [],
}
