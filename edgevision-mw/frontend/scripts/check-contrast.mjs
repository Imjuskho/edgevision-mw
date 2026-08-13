#!/usr/bin/env node
/**
 * Validates WCAG AA contrast (4.5:1) for semantic text/background pairs in each theme.
 * Run: node scripts/check-contrast.mjs
 */

const PAIRS = [
  ["--text-primary", "--bg-surface"],
  ["--text-secondary", "--bg-surface"],
  ["--text-muted", "--bg-surface"],
  ["--text-tertiary", "--bg-surface"],
  ["--success-text", "--success-surface"],
  ["--warning-text", "--warning-surface"],
  ["--danger-text", "--danger-surface"],
  ["--info-text", "--info-surface"],
];

const THEMES = ["dark", "light", "high-contrast"];

// Approximate resolved values per theme (matches studio-tokens.css)
const RESOLVED = {
  dark: {
    "--bg-surface": [0.18, 0.02, 260],
    "--text-primary": [0.96, 0.01, 260],
    "--text-secondary": [0.78, 0.02, 260],
    "--text-muted": [0.78, 0.02, 260],
    "--text-tertiary": [0.78, 0.02, 260],
    "--success-surface": [0.22, 0.06, 145],
    "--success-text": [0.82, 0.12, 145],
    "--warning-surface": [0.24, 0.06, 85],
    "--warning-text": [0.86, 0.10, 85],
    "--danger-surface": [0.22, 0.06, 25],
    "--danger-text": [0.82, 0.12, 25],
    "--info-surface": [0.22, 0.06, 250],
    "--info-text": [0.82, 0.10, 250],
  },
  light: {
    "--bg-surface": [1, 0, 260],
    "--text-primary": [0.22, 0.02, 260],
    "--text-secondary": [0.48, 0.02, 260],
    "--text-muted": [0.58, 0.02, 260],
    "--text-tertiary": [0.58, 0.02, 260],
    "--success-surface": [0.94, 0.04, 145],
    "--success-text": [0.35, 0.10, 145],
    "--warning-surface": [0.96, 0.04, 85],
    "--warning-text": [0.40, 0.10, 85],
    "--danger-surface": [0.96, 0.04, 25],
    "--danger-text": [0.40, 0.12, 25],
    "--info-surface": [0.95, 0.04, 250],
    "--info-text": [0.38, 0.10, 250],
  },
  "high-contrast": {
    "--bg-surface": [0.04, 0, 0],
    "--text-primary": [1, 0, 0],
    "--text-secondary": [0.92, 0, 0],
    "--text-muted": [0.8, 0, 0],
    "--text-tertiary": [0.8, 0, 0],
    "--success-surface": [0.04, 0, 0],
    "--success-text": [0.78, 0.15, 145],
    "--warning-surface": [0.04, 0, 0],
    "--warning-text": [0.92, 0.12, 85],
    "--danger-surface": [0.04, 0, 0],
    "--danger-text": [0.72, 0.18, 25],
    "--info-surface": [0.04, 0, 0],
    "--info-text": [0.88, 0.12, 250],
  },
};

function oklchToRgb(l, c, h) {
  const hr = (h * Math.PI) / 180;
  const a = c * Math.cos(hr);
  const b = c * Math.sin(hr);
  const l_ = l + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = l - 0.0894841775 * a - 1.291485548 * b;
  const l3 = l_ ** 3;
  const m3 = m_ ** 3;
  const s3 = s_ ** 3;
  let r = 4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3;
  let g = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3;
  let bl = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.707614701 * s3;
  const clamp = (x) => Math.max(0, Math.min(1, x));
  return [clamp(r), clamp(g), clamp(bl)];
}

function relLum([r, g, b]) {
  const f = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function contrast(fg, bg) {
  const l1 = relLum(fg);
  const l2 = relLum(bg);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

let failed = 0;

for (const theme of THEMES) {
  const tokens = RESOLVED[theme];
  console.log(`\nTheme: ${theme}`);
  for (const [fgKey, bgKey] of PAIRS) {
    const fg = oklchToRgb(...tokens[fgKey]);
    const bg = oklchToRgb(...tokens[bgKey]);
    const ratio = contrast(fg, bg);
    const pass = ratio >= 4.5;
    if (!pass) failed += 1;
    console.log(`  ${fgKey} on ${bgKey}: ${ratio.toFixed(2)}:1 ${pass ? "✓" : "✗ FAIL"}`);
  }
}

if (failed > 0) {
  console.error(`\n${failed} pair(s) failed WCAG AA.`);
  process.exit(1);
}
console.log("\nAll pairs pass WCAG AA (4.5:1).");
