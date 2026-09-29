/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sky: {
          blue: '#38BDF8',
        },
        deep: {
          blue: '#0F4C81',
        },
        ice: {
          blue: '#EFF9FF',
        },
        soft: {
          blue: '#E0F2FE',
        },
        brand: {
          success: '#16A34A',
          warning: '#F59E0B',
          alert: '#EF4444',
          primary: '#0F172A',
          secondary: '#475569',
          muted: '#64748B',
        }
      },
      fontFamily: {
        sans: ['Inter', 'Manrope', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
