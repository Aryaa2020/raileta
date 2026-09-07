/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        railway: {
          blue: '#003f87',
          orange: '#ff6b35',
          green: '#2ecc71',
          red: '#e74c3c',
          yellow: '#f39c12'
        }
      }
    },
  },
  plugins: [],
}
