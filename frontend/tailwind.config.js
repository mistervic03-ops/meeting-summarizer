/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "#131820",
          surface: "#171D25",
          rail: "#151B23",
          field: "#1A2029",
          popover: "#1C232D",
          hover: "#202732",
          line: "#29313B",
          border: "#3A4450",
          inverse: "#D9DDE3",
          text: "#ECEFF3",
          body: "#D2D7DE",
          muted: "#8A929E",
          subtle: "#69727E",
          accent: "#A58ABF",
          "accent-soft": "#201B2A",
          "accent-border": "#46325B",
          "accent-button": "#6E5288",
          "accent-button-hover": "#624A79",
          "warning-surface": "#271F14",
          "warning-border": "#4D3A1B",
          warning: "#D1A458",
          "warning-strong": "#E0C083",
          "success-border": "#214A3B",
          success: "#7FBE9E",
          "danger-border": "#553137",
          danger: "#D8848B"
        },
        brand: {
          50: "#F7F2FB",
          100: "#EEE4F7",
          200: "#DDC9EF",
          500: "#6B3FA0",
          600: "#5D348D",
          700: "#4D2A75"
        }
      },
      boxShadow: {
        card: "0 18px 50px rgba(35, 24, 54, 0.10)"
      },
      fontFamily: {
        sans: ["Inter", "Pretendard", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"]
      }
    }
  },
  plugins: []
};
