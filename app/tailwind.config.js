/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Text", "Inter", "sans-serif"],
        mono: ["SF Mono", "ui-monospace", "Menlo", "monospace"],
      },
      colors: {
        ink: { DEFAULT: "#0a0a0a", soft: "#1a1a1a" },
        surface: { DEFAULT: "#f8f6f3", card: "#ffffff", deep: "#ece8e2" },
        accent: { DEFAULT: "#c2410c", soft: "#fdba74" },
        muted: { DEFAULT: "#737373" },
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,0.04), 0 4px 16px rgba(0,0,0,0.06)",
      },
      animation: {
        "pulse-slow": "pulse-slow 2.2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      keyframes: {
        "pulse-slow": {
          "0%, 100%": { opacity: "0.45", transform: "scale(1.0)" },
          "50%":      { opacity: "0.12", transform: "scale(1.18)" },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
