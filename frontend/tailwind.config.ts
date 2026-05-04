import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Threat-grade palette used for confidence + composite badges
        threat: {
          green:  "#10b981",
          amber:  "#f59e0b",
          red:    "#ef4444",
          unknown:"#94a3b8",
        },
        panel: {
          bg:     "#0b0f17",   // outer background
          surface:"#101522",   // panel surface
          border: "#1c2433",
          text:   "#e2e8f0",
          muted:  "#94a3b8",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
