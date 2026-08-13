#!/usr/bin/env node
/**
 * Validate manifest.webmanifest icon entries.
 */
import { readFileSync, existsSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const MANIFEST = join(ROOT, "public/manifest.webmanifest");

const manifest = JSON.parse(readFileSync(MANIFEST, "utf8"));
const icons = manifest.icons ?? [];

const required = [
  { src: "/icons/icon-192.png", sizes: "192x192", minBytes: 500 },
  { src: "/icons/icon-512.png", sizes: "512x512", minBytes: 2000 },
  { src: "/icons/icon-512-maskable.png", sizes: "512x512", purpose: "maskable", minBytes: 2000 },
];

let ok = true;

for (const req of required) {
  const entry = icons.find((i) => i.src === req.src && i.sizes === req.sizes);
  const diskPath = join(ROOT, "public", req.src.replace(/^\//, ""));

  if (!entry) {
    console.error(`Missing manifest entry: ${req.src} (${req.sizes})`);
    ok = false;
    continue;
  }
  if (req.purpose && !String(entry.purpose || "").includes("maskable")) {
    console.error(`Missing maskable purpose for ${req.src}`);
    ok = false;
  }
  if (!existsSync(diskPath)) {
    console.error(`Missing file: ${diskPath}`);
    ok = false;
    continue;
  }
  const bytes = statSync(diskPath).size;
  if (bytes < req.minBytes) {
    console.error(`${req.src} too small (${bytes}B < ${req.minBytes}B) — placeholder?`);
    ok = false;
  } else {
    console.log(`OK ${req.src} (${bytes} bytes)`);
  }
}

if (!ok) process.exit(1);
console.log("Manifest icons validated.");
