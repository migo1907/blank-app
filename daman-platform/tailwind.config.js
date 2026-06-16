/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'daman-blue': {
          50: '#E8F0F9',
          100: '#D1E1F3',
          200: '#A3C3E7',
          300: '#75A5DB',
          400: '#4787CF',
          500: '#1969C3',
          600: '#14539C',
          700: '#0F3D75',
          800: '#0A274E',
          900: '#051127',
        },
        'daman-navy': {
          DEFAULT: '#043572',
          light: '#0A4D99',
          dark: '#02203F',
        },
      },
    },
  },
  plugins: [],
};
