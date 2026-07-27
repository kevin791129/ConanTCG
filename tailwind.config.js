/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        "surface":                  "#131315",
        "surface-container-low":    "#1c1b1d",
        "surface-container":        "#201f21",
        "surface-container-high":   "#2a2a2c",
        "surface-container-highest":"#353437",
        "on-surface":               "#e5e1e4",
        "on-surface-variant":       "#b9cacb",
        "outline":                  "#849495",
        "outline-variant":          "#3b494b",
        "primary":                  "#dbfcff",
        "primary-container":        "#00f0ff",
        "on-primary":               "#00363a",
        "secondary":                "#e5b4ff",
        "secondary-container":      "#ad00fe",
        "on-secondary":             "#4f0077",
        "tertiary-fixed-dim":       "#eac324",
      },
      fontFamily: {
        display: ["Space Grotesk", "sans-serif"],
        body:    ["DM Sans", "sans-serif"],
      },
    },
  },
  plugins: [],
};
