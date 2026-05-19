import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "rgb(10 12 18)",
          panel: "rgb(15 18 26)",
          subtle: "rgb(20 24 33)",
        },
        accent: {
          green: "rgb(74 222 128)",
          red: "rgb(248 113 113)",
          amber: "rgb(251 191 36)",
          blue: "rgb(96 165 250)",
        },
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "JetBrains Mono",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
