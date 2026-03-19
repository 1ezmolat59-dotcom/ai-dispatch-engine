/**
 * esbuild-based production build — workaround for Vite 5 + Rollup + Node v24 hang.
 * Produces the same output as `vite build` but uses esbuild bundler directly.
 *
 * Usage: node build.mjs
 */

import { build } from 'esbuild';
import { readFileSync, mkdirSync, cpSync, writeFileSync, existsSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, 'dist');

// Clean output dir
if (existsSync(OUT)) {
  const { rmSync } = await import('fs');
  rmSync(OUT, { recursive: true });
}
mkdirSync(OUT, { recursive: true });
mkdirSync(`${OUT}/assets`, { recursive: true });

// Copy public assets
try { cpSync(resolve(__dirname, 'public'), OUT, { recursive: true }); } catch {}

const pkg = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf8'));

console.log('Building with esbuild...');

const result = await build({
  entryPoints: [resolve(__dirname, 'src/main.tsx')],
  bundle: true,
  format: 'esm',
  outdir: `${OUT}/assets`,
  splitting: true,
  minify: true,
  sourcemap: false,
  target: ['es2020', 'chrome80', 'firefox80', 'safari14'],
  jsx: 'automatic',
  loader: {
    '.tsx': 'tsx',
    '.ts': 'ts',
    '.css': 'css',
    '.png': 'dataurl',
    '.svg': 'dataurl',
    '.jpg': 'dataurl',
    '.woff': 'dataurl',
    '.woff2': 'dataurl',
  },
  define: {
    'process.env.NODE_ENV': '"production"',
    'import.meta.env.MODE': '"production"',
    'import.meta.env.DEV': 'false',
    'import.meta.env.PROD': 'true',
    'import.meta.env.SSR': 'false',
  },
  metafile: true,
});

// Write the index.html pointing to built assets
const htmlIn = readFileSync(resolve(__dirname, 'index.html'), 'utf8');
const outFiles = Object.keys(result.metafile.outputs);
// Strip everything up to and including "dist/" to get a relative path like "assets/main.js"
const stripDist = (f) => f.replace(/^.*dist\//, '');
const jsFile = outFiles.find(f => f.endsWith('.js') && !f.endsWith('.chunk.js'))
  ? stripDist(outFiles.find(f => f.endsWith('.js') && !f.endsWith('.chunk.js')))
  : 'assets/main.js';
const cssFile = outFiles.find(f => f.endsWith('.css'))
  ? stripDist(outFiles.find(f => f.endsWith('.css')))
  : null;

let html = htmlIn
  // Replace the dev script tag (which has type="module" already) keeping only src change
  .replace(/<script type="module" src="\/src\/main\.tsx"><\/script>/, `<script type="module" src="/${jsFile}"></script>`)
  .replace('</head>', cssFile ? `  <link rel="stylesheet" href="/${cssFile}">\n</head>` : '</head>');

writeFileSync(`${OUT}/index.html`, html);

// Print output summary
console.log('\n✅ Build complete → dist/');
for (const [file, info] of Object.entries(result.metafile.outputs)) {
  const kb = (info.bytes / 1024).toFixed(1);
  console.log(`  ${stripDist(file)}  ${kb} KB`);
}
