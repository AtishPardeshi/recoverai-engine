/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fintech: {
          dark: '#0B0F19',
          card: '#111827',
          cardHover: '#1F2937',
          border: '#374151',
          accent: '#10B981',      // Emerald Green
          accentGlow: 'rgba(16, 185, 129, 0.2)',
          blue: '#3B82F6',        // Indigo / Blue
          blueGlow: 'rgba(59, 130, 246, 0.2)',
          warning: '#F59E0B',
          danger: '#EF4444',
          muted: '#9CA3AF',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      animation: {
        'pulse-subtle': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer': 'shimmer 2s linear infinite',
      },
      keyframes: {
        shimmer: {
          from: { backgroundPosition: '200% 0' },
          to: { backgroundPosition: '-200% 0' },
        },
      }
    },
  },
  plugins: [],
}
