# dotLottie (`.lottie`): bundling, themes, and interactivity

`.lottie` is a **zip archive** (a superset of plain Lottie) standardized by
LottieFiles. Reach for it when raw `.json` isn't enough.

## When to use `.lottie` vs `.json`
| Use `.json` when… | Use `.lottie` when… |
|---|---|
| single, simple animation | shipping **many** animations as one asset |
| you want max compatibility / zero setup | you want **theming** (runtime recolor without re-export) |
| editing/recoloring quickly | you want **state machines** (hover/click/scroll interactivity, no JS) |
| | the animation has shared **image/font** assets to dedupe |
| | smaller payload over the wire matters (zip compression) |

Both are rendered by the same modern players (`@lottiefiles/dotlottie-*`) — point
`src` at either. So a good default: author/generate `.json`, and bundle to
`.lottie` only when you need its extra capabilities or are shipping a set.

## What's inside a `.lottie`
```
my.lottie  (zip)
├── manifest.json        # lists animations, themes, state machines, default play settings
├── a/spinner.json       # animation(s)  (folder name may vary by version)
├── a/success.json
├── i/…                  # shared images (optional)
├── f/…                  # fonts (optional)
├── t/…                  # themes (optional)
└── s/…                  # state machines (optional)
```
The **manifest** is what the player reads first to know what's bundled and how to
play it. Inspect any `.lottie` with: `python scripts/fetch_lottie.py file.lottie --info`.

## Bundling `.json` → `.lottie` (tested, works)
Use the bundled Node script (`scripts/make_dotlottie.mjs`). One-time setup in the
project: `npm install @dotlottie/dotlottie-js`.
```bash
# single animation, set to autoplay + loop
node scripts/make_dotlottie.mjs --out icon.lottie --autoplay --loop spinner.json
# bundle several animations into one file
node scripts/make_dotlottie.mjs --out pack.lottie spinner.json success.json error.json
```
Programmatic (Node, `@dotlottie/dotlottie-js` v1.x — **V2 API**):
```js
import { DotLottie } from "@dotlottie/dotlottie-js"; // auto-resolves Node build
import { readFileSync, writeFileSync } from "node:fs";

const dl = new DotLottie({ generator: "my-app" });
dl.addAnimation({ id: "spinner", data: JSON.parse(readFileSync("spinner.json","utf8")),
                  loop: true, autoplay: true });
const ab = await dl.toArrayBuffer();          // V2: builds directly (no .build())
writeFileSync("spinner.lottie", Buffer.from(ab));
```
> Version note: the package has changed APIs across majors. In the installed v1.6.x
> the class is `DotLottie`, constructed with `{ generator }` (no `setAuthor`), and
> `toArrayBuffer()` builds without a separate `.build()` step. If you hit
> "X is not a function", introspect: `Object.getOwnPropertyNames(Object.getPrototypeOf(new DotLottie()))`.

## Themes (runtime recolor, no re-export)
A theme is a set of property overrides (colors, opacities, stroke widths…) bundled
in the file. The player switches them instantly via `setTheme(id)`. Authoring
themes reliably is easiest in the **LottieFiles editor / Lottie Creator** (define
color slots, export themed `.lottie`), because the slot/rule schema is detailed and
version-sensitive. At runtime:
```js
const dotLottie = new DotLottie({ canvas, src: "themed.lottie", autoplay: true });
dotLottie.setTheme("dark");          // activate a bundled theme
dotLottie.resetTheme();
```
For purely programmatic recoloring of a `.json`, the recipe in
`references/json-format.md` §8 (walk and overwrite `fl`/`st` colors) is simpler and
fully under your control.

## State Machines (interactivity without JavaScript)
dotLottie v2 can embed a **state machine**: states (each tied to an animation or a
segment), transitions, and triggers (pointer enter/exit/down, scroll, custom
events, input values). This lets a designer ship an interactive button/toggle as a
single file — the developer just renders it.
```js
const dotLottie = new DotLottie({
  canvas: document.getElementById("canvas"),
  src: "interactive-button.lottie",
  stateMachineId: "main",            // start the embedded machine
  autoplay: true,
});
// optional: drive it from your UI
dotLottie.loadStateMachine("main");
dotLottie.startStateMachine();
dotLottie.postEvent({ type: "PointerDown" });
// listen back
dotLottie.addEventListener("stateMachineStateEntered", (e) => console.log(e));
```
The player emits typed events: `stateMachineStart`, `stateMachineTransition`,
`stateMachineStateEntered`, custom events, and input changes — wire these into app
logic. **Author** state machines visually in Lottie Creator and export them inside
the `.lottie`; hand-writing the state-machine JSON is possible but error-prone.

## Rendering engine (why `.lottie` performs well)
Modern dotLottie players share one Rust + WASM core (`dotlottie-rs`) rendering via
**ThorVG**, with Software / WebGL2 / WebGPU backends and playback up to 120fps. The
same core ships on web, iOS, and Android, so animations look identical everywhere.
See `references/integration.md` for selecting a renderer and worker offloading.
