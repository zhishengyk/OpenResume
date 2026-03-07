import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#f5f0e8",
        ink: "#10212f",
        slate: "#41515d",
        ember: "#e76a38",
        signal: "#f1bf5a",
        mint: "#9dd6c0",
        shell: "#fbf7f0"
      },
      boxShadow: {
        console: "0 25px 80px rgba(16, 33, 47, 0.16)"
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(rgba(16,33,47,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(16,33,47,0.08) 1px, transparent 1px)"
      },
      fontFamily: {
        display: ["\"Newsreader\"", "serif"],
        body: ["\"IBM Plex Sans\"", "sans-serif"]
      }
    }
  },
  plugins: []
};

export default config;

