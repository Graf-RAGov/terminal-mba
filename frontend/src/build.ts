/**
 * Build script: bundles app.ts + styles.css into index.html
 * Uses split/join template injection to inline CSS and JS
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync, cpSync } from "fs";
import { join, dirname } from "path";

const srcDir = dirname(import.meta.path);
const distDir = join(srcDir, "..", "dist");

// Ensure dist exists
mkdirSync(distDir, { recursive: true });

// Read source files
const html = readFileSync(join(srcDir, "index.html"), "utf-8");
const css = readFileSync(join(srcDir, "styles.css"), "utf-8");

// Bundle app.ts via Bun
const result = await Bun.build({
  entrypoints: [join(srcDir, "app.ts")],
  outdir: distDir,
  minify: false,
  target: "browser",
  format: "esm",
});

if (!result.success) {
  console.error("Build failed:", result.logs);
  process.exit(1);
}

// Read built JS
const jsFile = result.outputs[0];
const js = await jsFile.text();

// Inject into template using split/join (avoids $ issues)
const output = html
  .split("{{STYLES}}")
  .join(css)
  .split("{{SCRIPT}}")
  .join(js);

writeFileSync(join(distDir, "index.html"), output);

// Copy manifest and sw
for (const file of ["manifest.json", "sw.js"]) {
  const src = join(srcDir, file);
  if (existsSync(src)) {
    cpSync(src, join(distDir, file));
  }
}

console.log("Build complete: dist/index.html");
