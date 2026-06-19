#!/usr/bin/env node
/**
 * make_dotlottie.mjs — bundle one or more Lottie .json files into a single
 * compressed .lottie archive (dotLottie v2) using @dotlottie/dotlottie-js.
 *
 * Why .lottie over raw .json:
 *   - It's a zip: usually much smaller over the wire than equivalent JSON.
 *   - One file can hold MANY animations + shared image/font assets.
 *   - It's the container that also carries themes & state machines (those are
 *     authored in the LottieFiles editor — see references/dotlottie-and-bundling.md).
 *
 * Setup (run once in the project):
 *   npm install @dotlottie/dotlottie-js
 *
 * Usage:
 *   node make_dotlottie.mjs --out bundle.lottie anim1.json anim2.json
 *   node make_dotlottie.mjs --out icon.lottie --autoplay --loop spinner.json
 *
 * Flags:
 *   --out <path>   output .lottie path (required)
 *   --loop         set animations to loop (default off)
 *   --autoplay     set animations to autoplay (default off)
 */
import { DotLottie } from "@dotlottie/dotlottie-js";
import { readFileSync, writeFileSync } from "node:fs";
import { basename } from "node:path";

function parseArgs(argv) {
  const o = { files: [], loop: false, autoplay: false, out: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--out") o.out = argv[++i];
    else if (a === "--loop") o.loop = true;
    else if (a === "--autoplay") o.autoplay = true;
    else o.files.push(a);
  }
  return o;
}

const args = parseArgs(process.argv.slice(2));
if (!args.out || args.files.length === 0) {
  console.error("Usage: node make_dotlottie.mjs --out bundle.lottie a.json [b.json ...]");
  process.exit(1);
}

const dl = new DotLottie({ generator: "lottie-master" });
for (const file of args.files) {
  const data = JSON.parse(readFileSync(file, "utf8"));
  const id = basename(file, ".json").replace(/[^a-zA-Z0-9_-]/g, "_");
  dl.addAnimation({ id, data, loop: args.loop, autoplay: args.autoplay });
}

const ab = await dl.toArrayBuffer();
const buf = Buffer.from(ab);
writeFileSync(args.out, buf);
console.log(`Wrote ${args.out} (${buf.length.toLocaleString()} bytes, ${args.files.length} animation(s))`);
