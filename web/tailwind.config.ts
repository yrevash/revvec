import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0a0a0b",
        accent: "#ff6a26",
        accentSoft: "#ffd2bd",
        muted: "#6b6b73",
        surface: "#fafaf7",
        deep: "#0c0c0e",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular"],
        display: ["Instrument Serif", "ui-serif", "Georgia"],
      },
      animation: {
        "fade-up": "fade-up 0.6s ease-out forwards",
        "subtle-pulse": "subtle-pulse 3s ease-in-out infinite",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "subtle-pulse": {
          "0%,100%": { opacity: "0.6" },
          "50%": { opacity: "1" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
