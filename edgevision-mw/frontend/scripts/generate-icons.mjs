#!/usr/bin/env node
/**
 * Generate PWA PNG icons from the brand SVG mark.
 * Usage: node scripts/generate-icons.mjs
 * Requires: sharp (devDependency)
 */
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const SVG_PATH = join(ROOT, "public/icons/icon.svg");
const OUT_DIR = join(ROOT, "public/icons");

const SIZES = [
  { name: "icon-192.png", size: 192, maskable: false },
  { name: "icon-512.png", size: 512, maskable: false },
  { name: "icon-512-maskable.png", size: 512, maskable: true },
];

async function main() {
  if (!existsSync(SVG_PATH)) {
    console.error(`SVG not found: ${SVG_PATH}`);
    process.exit(1);
  }

  let sharp;
  try {
    sharp = (await import("sharp")).default;
  } catch {
    console.error("sharp is required. Run: npm install -D sharp");
    process.exit(1);
  }

  const svg = readFileSync(SVG_PATH);

  for (const { name, size, maskable } of SIZES) {
    const outPath = join(OUT_DIR, name);
    let pipeline = sharp(svg).resize(size, size, { fit: "contain", background: { r: 15, g: 23, b: 42, alpha: 1 } });

    if (maskable) {
      // Safe zone ~80% for maskable icons
      const inner = Math.round(size * 0.72);
      const pad = Math.round((size - inner) / 2);
      pipeline = sharp(svg)
        .resize(inner, inner, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } })
        .extend({
          top: pad,
          bottom: pad,
          left: pad,
          right: pad,
          background: { r: 15, g: 23, b: 42, alpha: 1 },
        });
    }

    await pipeline.png().toFile(outPath);
    const stat = (await import("node:fs")).statSync(outPath);
    console.log(`Wrote ${name} (${stat.size} bytes, ${size}x${size}${maskable ? ", maskable" : ""})`);
  }

  console.log("\nIcon generation complete.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
