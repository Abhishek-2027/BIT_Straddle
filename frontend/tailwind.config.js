/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        page: '#0B0D10',
        sidebar: '#15191F',
        card: '#171B21',
        cardHover: '#1B2027',
        borderDark: '#292E36',
        accentGreen: '#20C978',
        accentRed: '#EF4444',
        border: '#292E36',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
