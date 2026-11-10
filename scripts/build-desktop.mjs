import { build } from 'esbuild';
await build({entryPoints:['apps/desktop/src/main.ts'],outfile:'apps/desktop/dist/main.cjs',bundle:true,platform:'node',external:['electron']});
await build({entryPoints:['apps/desktop/src/preload.ts'],outfile:'apps/desktop/dist/preload.cjs',bundle:true,platform:'node',external:['electron']});
await build({entryPoints:['apps/desktop/src/ollama.ts'],outfile:'apps/desktop/dist/ollama-runtime.cjs',bundle:true,platform:'node'});
