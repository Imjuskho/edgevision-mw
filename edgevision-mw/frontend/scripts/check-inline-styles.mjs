#!/usr/bin/env node
/**
 * Fail CI when inline style={{}} count exceeds threshold.
 * Dynamic geometry (progress widths, canvas coords) should use data attributes + CSS where possible.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(import.meta.dirname, "..", "src");
const MAX_INLINE = 20;

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (!entry.includes("node_modules")) walk(full, files);
    } else if (/\.(tsx|jsx)$/.test(entry)) {
      files.push(full);
    }
  }
  return files;
}

const offenders = [];
let total = 0;

for (const file of walk(ROOT)) {
  const content = readFileSync(file, "utf8");
  const matches = content.match(/style=\{\{/g) ?? [];
  if (matches.length) {
    total += matches.length;
    offenders.push({ file: file.replace(ROOT + "/", ""), count: matches.length });
  }
}

offenders.sort((a, b) => b.count - a.count);

console.log(`Inline style={{}} count: ${total} (max ${MAX_INLINE})`);
if (offenders.length) {
  console.log("\nTop offenders:");
  for (const row of offenders.slice(0, 15)) {
    console.log(`  ${row.count.toString().padStart(3)}  ${row.file}`);
  }
}

if (total > MAX_INLINE) {
  console.error(`\nFAIL: ${total} inline styles exceeds limit of ${MAX_INLINE}.`);
  process.exit(1);
}

console.log("\nOK: inline style count within limit.");
