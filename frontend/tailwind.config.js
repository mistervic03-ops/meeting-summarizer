/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
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
