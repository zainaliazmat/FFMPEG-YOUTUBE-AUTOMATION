# Lottie & dotLottie: An Actionable Knowledge Base for a "lottie-master" Claude Code Skill

## TL;DR
- **Default to the dotLottie (`.lottie`) format and the dotLottie runtime family** (`@lottiefiles/dotlottie-web` + framework wrappers, all powered by the Rust/WASM ThorVG engine). Per LottieFiles' dotLottie page it is "up to 10x smaller than Lottie JSON" (typically 2–10x depending on complexity and embedded assets — animations with images see the largest gains because assets are compressed inside the archive rather than base64-encoded). It bundles multiple animations/themes/state machines/fonts/images in one Deflate-compressed ZIP and renders identically across web, iOS, Android, Flutter, and React Native (ThorVG's showcase notes Canva adopted it on iOS for "up to 80% faster rendering and 70% lower peak memory usage").
- **The richest, most implementable knowledge for Claude Code is in the official docs** (docs.lottiefiles.com): exact player props/methods, the dotLottie v2 manifest structure, theming spec (slots + rules), and the state-machine spec (states, transitions, guards, inputs, actions, interactions). LottieFiles even ships an official `SKILL.md` and a `motion-design-skill` repo that this skill should mirror/extend.
- **Author with dotlottie-js (bundling), theme/slot with Motion Tokens, optimize aggressively (precision, layers, assets), and always handle reduced-motion, cleanup (`destroy()`), and SSR.** The biggest real-world failure modes are unsupported After Effects features (expressions ~75% support in ThorVG; fonts; layer effects), CORS/path errors, and not waiting for `load` before controlling playback.

## Key Findings

### 1. Format strategy: dotLottie is the new baseline
- **Lottie JSON** (`.json`, `application/json`): the original Bodymovin format. Plain, human-readable JSON; universal player support; image assets only as Data URIs; no compression, multi-animation, theming, or interactivity.
- **dotLottie** (`.lottie`, `application/zip+dotlottie`): a Deflate-compressed ZIP container. Supports multiple animations, extracted image assets (`i/`), theming, and state-machine interactivity. Smaller files; not human-readable; requires a dotLottie-compatible player.
- Reported size advantage: LottieFiles' dotLottie page states "up to 10x smaller than Lottie JSON" (typically 2–10x); the "dotLottie is the new baseline" blog cites a Fortune 500 switch cutting animation file sizes 8–10x.
- **Decision rule for the skill:** prefer `.lottie` unless the target player only supports `.json` or you need to hand-edit the file. The same dotLottie player loads both — just point `src` at either.

### 2. The implementations landscape (from lottie.github.io/implementations)
- **Web:** `lottie-web` (Airbnb), `dotlottie-web` (LottieFiles, ThorVG/WASM), plus framework wrappers `lottie-react`, `lottie-vue`, `svelte-lottie-player`; community `react-lottie`, `vue-lottie`, `ng-lottie`.
- **Android:** `lottie-android` (Airbnb), `dotlottie-android` (LottieFiles), `lottie-react-native`, LottieXamarin, NativeScript-lottie.
- **iOS:** `lottie-ios` (Airbnb), `dotlottie-ios` (LottieFiles).
- **Windows:** Lottie-Windows (Microsoft), LottieUWP.
- **Multi-platform engines:** Skottie (Skia/Google), rlottie (Samsung, C++), **ThorVG** (the dotLottie renderer), Qt Lottie, `dotlottie-rs` (Rust core), Lottie4j (Java).
- **Architecture insight:** dotlottie-web→WASM; dotlottie-ios/android/flutter/react-native→C API; all funnel into `dotlottie-rs` → ThorVG. One engine = visual consistency across platforms (a historical pain point: gradients/masks/easing drifting between iOS and Android).
- **Creation tools:** After Effects (Bodymovin by Hernan Torrisi; LottieFiles plugin), Figma plugins (LottieFiles, Lottielab, Aninix, Flow), Lottie Creator (web), LottieLab, Jitter, Phase, Haiku, Glaxnimate, Keyshape.
- **Other tools:** lottie-colorify (recolor from code), lottie-interactivity, relottie (plugin-based Lottie processor), python-lottie (manipulate/convert), puppeteer-lottie (render to image/GIF/MP4).

### 3. dotLottie-web player: exact API surface
- **Install:** `npm install @lottiefiles/dotlottie-web` (vanilla/Vue/Svelte) or `@lottiefiles/dotlottie-react`. Node 18+ supported.
- **Constructor config:** `canvas`, `src`, `data`, `autoplay`, `loop`, `speed`, `backgroundColor`, `segment: [start,end]`, `mode`, `renderConfig: { autoResize, devicePixelRatio, freezeOnOffscreen }`, `layout: { fit, align }`, `themeId`, `themeData`, `stateMachineId`, `stateMachineConfig: { openUrlPolicy: { requireUserInteraction, whitelist } }`, `useFrameInterpolation`, `marker`, `animationId`.
- **Playback methods:** `play()`, `pause()`, `stop()`, `setFrame(n)`, `setSpeed(x)`, `setLoop(bool)`, `setLoopCount(n)`, `setMode(mode)`, `setSegment(start,end)`, `setUseFrameInterpolation(bool)`, `setMarker(name)`, `markers()`, `loadAnimation(id)`, `resize()`, `freeze()`, `unfreeze()`, `setBackgroundColor()`, `setLayout()`, `setRenderConfig()`, `animationSize()`, `setViewport()`, `destroy()`.
- **Theming/slots methods:** `setTheme(id)`, `setThemeData(json)`, plus typed slot APIs `getSlotIds()`, `getSlotType()`, `setColorSlot()`, `setScalarSlot()`, `setVectorSlot()`, `setGradientSlot()`, `setTextSlot()`, `resetSlot()`, `clearSlots()`.
- **State-machine methods:** `stateMachineLoad(id)`, `stateMachineStart()`, `stateMachineStop()`, `stateMachineFireEvent('click'|'hover'|'unhover'|'complete'|custom)`, `stateMachineSetNumericInput(name,val)`, `stateMachineSetBooleanInput(name,val)`, `stateMachineSetStringInput(name,val)`, `stateMachineGetCurrentState()`, `stateMachinePostClickEvent(x,y)`.
- **Events (25+ typed):** `load`, `loadError`, `ready`, `play`, `pause`, `stop`, `complete`, `loop`, `frame` (`{ currentFrame }`), `render`, `freeze`, `unfreeze`, `destroy`.
- **Read-only props:** `isLoaded`, `isPlaying`, `isPaused`, `duration`, `totalFrames`, `currentFrame`, `loop`, `speed`, `manifest`, `backgroundColor`.
- **Rendering backends:** Software (Canvas2D), WebGL2, **WebGPU (experimental)** — switch via one-line import change; identical `DotLottie` class. `DotLottieWorker` runs rendering off-main-thread on an OffscreenCanvas (group via `workerId`). LottieFiles' dotLottie page states the runtime is "120+ FPS rendering, ~150KB runtime and WebAssembly on web."

### 4. React player (`@lottiefiles/dotlottie-react`) props reference
- Requires React ≥ 16.8.0. Component: `<DotLottieReact />`, extends `HTMLCanvasElement` props.
- Props: `autoplay` (false), `loop` (false), `src`, `speed` (1), `data`, `mode` ("forward" | "reverse" | "bounce" | "reverse-bounce"), `backgroundColor` (6/8-digit hex), `segment: [number,number]`, `renderConfig`, `playOnHover` (false), `dotLottieRefCallback`, `useFrameInterpolation` (true), `marker`, `animationId`, `themeId`, `themeData`, `layout`, `stateMachineId`, `stateMachineConfig`, `loopCount` (0 = infinite).
- `RenderConfig`: `devicePixelRatio` (default window.devicePixelRatio | 1), `autoResize` (true).
- `Layout`: `fit` ('contain' | 'cover' | 'fill' | 'none' | 'fit-width' | 'fit-height'; default 'contain'), `align` ([0.5,0.5]).
- Control pattern: get the instance via `dotLottieRefCallback={(dl) => ref.current = dl}`, then call methods / `addEventListener`. React wrapper auto-cleans up on unmount (no manual `destroy()`).

### 5. dotLottie file structure (v2 manifest)
```
my-animation.lottie
├── manifest.json   # version "2", generator, initial, animations[], themes[], stateMachines[]
├── a/  animationN.json      # Lottie JSON animations (id matches manifest, no .json)
├── i/  logo.webp            # optional image assets
├── t/  light.json dark.json # optional themes (id → t/<id>.json)
└── s/  button.json          # optional state machines (id → s/<id>.json)
```
- Manifest animation props: `id` (req), `initialTheme`, `background` (hex), `themes[]`. `initial.animation` / `initial.stateMachine` set what loads first.
- ID naming rule: alphanumeric, dots, underscores, spaces, hyphens only.

### 6. Theming spec (v1.0) — runtime property overrides via Slots
- Themes live in `t/`, each a JSON `{ "rules": [...] }`. Each rule targets a property by its **Lottie Slot ID** — a property must be assigned a slot ID (`sid`) in the source animation before it can be themed.
- Rule fields: `id` (slot ID, case-sensitive), `type` (`Color`|`Scalar`|`Position`|`Vector`|`Gradient`|`Image`|`Text`), optional `animations[]` scoping, and one of `value` / `keyframes` / `expression` (expression > keyframes > value).
- **Colors are normalized `[R,G,B]` arrays 0–1** (CSS color names NOT supported). Scalars are numbers (opacity, stroke width, rotation). Gradients are `{color,offset}` stops. Keyframes support `frame`, `value`, `inTangent`/`outTangent`, `hold`.
- Expressions use `$bm_rt` return convention with globals `time`, `value`, `thisComp`, `thisLayer`.
- System behavior: dynamic theme loading and theme inheritance are NOT supported; unknown themes rejected at validation; changes apply immediately.

### 7. State machines spec (v1.0) — interactivity without code
- Four parts: **Inputs** (typed vars: Numeric/String/Boolean + Event signals), **Interactions** (bind gestures/lifecycle to actions), **States** (one active at a time), **Transitions** (move between states when guards pass).
- Flow: interaction fires → actions update inputs → transitions re-evaluate guards → first passing transition fires → new state.
- **States:** `PlaybackState` (animation, autoplay, loop, loopCount, mode Forward/Reverse/Bounce/ReverseBounce, speed, segment, backgroundColor, final, entryActions, exitActions, transitions) and `GlobalState` (transitions checked first, for universal resets).
- **Transitions:** `Transition` (immediate, toState, guards) and `Tweened` (duration in seconds + cubic-Bézier `easing [x1,y1,x2,y2]`). During a tween, input changes are ignored.
- **Guards (AND logic):** Numeric (Equal/NotEqual/GreaterThan/GreaterThanOrEqual/LessThan/LessThanOrEqual), String (Equal/NotEqual), Boolean (Equal/NotEqual), Event (edge-triggered, consumed). `compareTo` can reference another input via `$name`.
- **Actions:** `SetNumeric`/`SetString`/`SetBoolean`/`Toggle`/`Increment`/`Decrement`/`Fire`/`Reset`; playback `SetFrame`/`SetProgress`; styling/nav `SetTheme`/`OpenUrl` (target _blank/_self/...)/`FireCustomEvent`.
- **Interactions:** Pointer (`PointerEnter`/`Exit`/`Down`/`Up`/`Move`/`Click`, optional case-sensitive `layerName`) and lifecycle (`OnComplete`, `OnLoopComplete` with `stateName`).
- Validation: `initial` must exist; ≥1 state; unique state/input names; `toState` must resolve; `final:true` states have no outgoing transitions.
- **Note:** docs flag state-machine support as "currently in early development" — full on web, platform-specific on mobile.

### 8. Motion Tokens / data binding
- Motion Tokens are the user-facing layer over Lottie **Slots**. In Lottie Creator you mark any color/text/transform as a token; developers bind tokens to live data at runtime via the **Slots API** — no re-export when data changes.
- Distinction: **Themes set defaults; tokens let code override any value at runtime.** Versioned inside the `.lottie` file; deterministic; consistent across Web/iOS/Android.

### 9. Performance, optimization & accessibility
- **File creation/optimization (AE/Bodymovin):** minimize layers and keyframes; flatten/group shapes (one shape layer + one fill for identical fills); apply scale on the highest layer possible (one CSS transform vs many); reuse identical elements; prefer motion paths/transforms over animating shape paths directly; avoid embedded raster images (convert to vectors or extract); avoid Alpha Matte / Alpha Inverted Matte (use masks); avoid frame-by-frame and BodyMovin Physics (real-time sim is heavy); reduce numeric/Bézier precision (e.g. 0.6789432 → 0.68). Bodymovin "compression" only affects keyframe precision, not image/shape weight. Export to Optimized Lottie JSON / Optimized dotLottie / TGS via the LottieFiles AE plugin; further reduce with the LottieFiles Optimizer / Advanced Optimizer.
- **Runtime performance:** `useFrameInterpolation:false` to match AE frame rate on low-end devices; `renderConfig.freezeOnOffscreen` (default true) pauses offscreen rendering; `DotLottieWorker` offloads to a Web Worker; lazy-load below-the-fold via IntersectionObserver; devicePixelRatio defaults to 75% of actual for performance (set to `window.devicePixelRatio` for full retina). Too many DOM elements is a `lottie-web` (SVG/DOM renderer) problem — the canvas-based dotLottie/ThorVG renderer avoids DOM bloat.
- **Memory:** always `destroy()` the vanilla instance on teardown (releases WebGL/canvas context, stops rAF loops, removes listeners); framework wrappers auto-clean on unmount; on native, remove state-machine listeners in lifecycle methods.
- **Accessibility (WCAG 2.1):** respect `prefers-reduced-motion` — disable autoplay / show a static frame (pause at a frame) or static image fallback; wrap canvas with `role="img"`/`region` + `aria-label`; provide alt text; label interactive elements with ARIA roles; ensure animations don't block screen readers/keyboard nav. A community pattern uses a marker named "reduced motion" played when the OS setting is on (implemented on iOS; not yet standard on web/Android). CSS: `@media (prefers-reduced-motion: reduce) { #lottie-container { display:none } }`.
- **Responsive sizing:** set canvas size via CSS; use `renderConfig.autoResize:true`; layout `fit` + `align`.

### 10. Motion design principles for marketing/UX (from the LottieFiles marketing article)
- Why motion (directional, see caveats): viewers retain ~95% of a message in video/animated form vs ~10% for static text; native video posts saw ~135% greater organic reach than photos (Socialbakers Oct 2014–Feb 2015 study of 670,000+ posts by 4,445 brand pages: 8.71% video vs 3.73% photo); a 1-second mobile load delay can cut conversions up to ~20% (so loaders matter).
- Use cases: explainer/onboarding (Instacart), interactive editorial (The Guardian British wildlife), brand storytelling/animated logos (Lyft, Meta, Pixar), simplifying complex processes (Razorpay payment flows), education (Vividbooks AR textbooks), email (eHarmony urgency clock), animated text/CTAs, social content, presentations.
- Practical guidance: keep durations under ~1s unless purposeful; use easing for natural motion; use micro-animations on buttons/cursors/scroll; don't overuse — animate where it adds the most value (key interactions, storytelling).

### 11. Sources & licensing
- **Lottie Simple License** governs public free animations on LottieFiles (and LottieLab/LottieLink): free to use, modify, distribute **including commercially**; **attribution NOT required** (encouraged, and must be visible if included); derivative works inherit the same license; you may not compile Files to build a competing service. Provided "as is."
- **Premium animations** include a commercial-use license. Marketplace-sold animations may not be re-uploaded as free. **Verify per-file:** licenses can vary per file even on the same platform — always check the specific animation's license.
- **Catalogs:** LottieFiles free-animations (categories: Finance, Icons, Gaming, Business, Space, Health, Animals; trending: interactivity, theming, loading, success, confetti, ai, arrow, login, error, check, money, 404); downloadable as Lottie JSON, dotLottie, GIF, MP4. IconScout (982K+ Lotties, JSON/AEP/ZIP, Lottie Preview tool, recolor via Color Palette/Lottie Editor). Others: Lottieflow (Webflow), Icons8/Ouch!, Lordicon, Creattie.

### 12. Showcases & examples (lottielab.com/templates/showreels)
- Common showreel/template patterns: bento-grid DNA layouts, logo reveals/"logo on screen", multi-color identity systems (4/5/6 colors), poster showcases, profile cards (spin/float/stacked, light & dark), phone-grid app showcases, card carousels (horizontal/diagonal/vertical). Demonstrates that recoloring, light/dark variants, and looping product mockups are the dominant commercial styles.
- LottieLab also provides tools the skill can reference: Figma→Lottie, SVG→Lottie, Lottie→dotLottie, file-size optimizer, Lottie→GIF/MP4/WebM.

## Details: integration patterns by framework

**Vanilla JS**
```js
import { DotLottie } from '@lottiefiles/dotlottie-web';
const dl = new DotLottie({ canvas: document.getElementById('canvas'), src: 'a.lottie', autoplay: true, loop: true });
// teardown: dl.destroy();
```

**React** — `<DotLottieReact src="a.lottie" autoplay loop />`; instance control via `dotLottieRefCallback`; workers via `DotLottieWorkerReact`.

**Vue** — `import { DotLottieVue } from '@lottiefiles/dotlottie-vue'`; `<DotLottieVue style="height:500px;width:500px" autoplay loop src="..." />`.

**Svelte** — `import { DotLottieSvelte } from '@lottiefiles/dotlottie-svelte'`; `<DotLottieSvelte src="a.lottie" loop autoplay dotLottieRefCallback={(r)=>dotLottie=r} />`.

**Web Component** — `<dotlottie-wc src="..." autoplay loop></dotlottie-wc>` + `<script type="module" src="https://unpkg.com/@lottiefiles/dotlottie-wc@latest/dist/dotlottie-wc.js">`.

**Next.js / SSR** — dotLottie needs browser APIs; import with `next/dynamic` and `{ ssr: false }`. Web Component is ⚠️ SSR (needs client-side hydration). For Vue/Nuxt community wrappers, wrap in `<client-only>`.

**Authoring with dotlottie-js** (`@dotlottie/dotlottie-js`, Node import `/node`):
```js
const dl = new DotLottie();
await dl.setAuthor('X').setVersion('2')
  .addAnimation({ id:'idle', data: idleJson, loop:true, autoplay:true })
  .addAnimation({ id:'hover', url:'https://.../hover.json' })
  .addTheme({ id:'dark', data: themeData })
  .assignTheme({ animationId:'idle', themeId:'dark' })
  .addStateMachine({ id:'button_states', data:{...} })
  .build();
const buf = await dl.toArrayBuffer();   // or .toBlob()/.toBase64()/.download('x.lottie')
```
Other class methods: `fromURL()`, `fromArrayBuffer()`, `merge()`, `getAnimations()`, `removeAnimation()`, `addPlugins()`. `enableDuplicateImageOptimization` dedupes shared images. Animations are fetched only on `build()`.

## Details: ThorVG feature-support matrix (what survives export)
ThorVG (the dotLottie engine) supports: all shapes (ellipse/group/path/polystar/rectangle), strokes (dashes, miter limit, caps, joins, width), fills (solid, opacity, fill rule, linear/radial gradient), images (embedded Base64, path/URL, JPG/PNG/WebP), transforms (anchor, auto-orient, opacity, parenting, position, scale, skew), interpolators (linear, bezier, hold, spatial bezier, rove across time), modifiers (offset path, pucker/bloat, repeater, roundness, trim path), masks (add/subtract/intersect/difference/lighten/darken/opacity/expansion/path), mattes (alpha/luma + inverted), layer effects (fill, drop shadow, gaussian blur, stroke, tint, tritone, expression control), full text (alignment, caps, document, fonts, glyphs, justify, outline, range selector, text path, tracking), and others (markers, precomps, time remap/stretch, slots).
- **Expressions: ~75% support (72% full + 3% partial).** Expressions run on the JerryScript engine gated by compile flag `THORVG_LOTTIE_EXPRESSIONS_SUPPORT`; ThorVG's "Lite" renderer presets (SW-Lite/GL-Lite/WG-Lite) drop expressions and fonts entirely (PNG only). Known gaps that WILL break: `marker`/camera/audio/video properties, `loopOut`/`loopIn` modes beyond `"cycle"` and `"pingpong"` (`"offset"`/`"continue"` unsupported), path `inTangents`/`outTangents`/`isClosed`, `createPath`, `sampleImage`, `lookAt`, `propertyGroup` levels beyond 1, `effect(name/index)`, `toComp`/`fromComp`, `pointOnPath` (per open issue thorvg #2233).
- **Clearest "will break" items:** audio/video layers, non-cycle/pingpong loop expressions, and any expression-heavy animation. Use the LottieFiles AE plugin's feature/render report and per-platform support table (Lottie-Android/iOS/Windows/Web/dotLottie) to validate before shipping.

## Details: common pitfalls & troubleshooting
- **Animation not loading:** check path typos/case-sensitivity, relative paths, 404/403/500, **CORS** (`Access-Control-Allow-Origin`), valid `.lottie`/`.json`; listen for `loadError`. Firewalls blocking `lottie.host` are a known workspace failure.
- **Not playing:** wait for `load`/`isLoaded` before calling `play()`; confirm `autoplay`/`loop`; verify valid instance ref; check marker/segment frame validity; verify state machine loaded & started.
- **Text not rendering / blank:** a very common failure — fonts not embedded or subsetted. Convert text layers to shapes/outlines in After Effects, or ensure fonts are embedded; native-font animations historically fail in web players.
- **Performance lag:** toggle `useFrameInterpolation:false`, ensure `freezeOnOffscreen`, use `DotLottieWorker`, test a known-good simple animation, profile, and confirm `destroy()` cleanup.
- **Missing visuals after export:** likely an unsupported AE feature (layer effects/expressions) — run a feature report (relottie) and simplify.

## Recommendations (staged, for building the lottie-master skill)
1. **Mirror the official `SKILL.md` first.** LottieFiles publishes `LottieFiles/dotlottie-web/SKILL.md` (package selection, workers, state machines, theming, slots, performance, SSR, common patterns) and a separate `LottieFiles/motion-design-skill`. Fold both in verbatim as the backbone, then extend with the format/spec details above. Benchmark to change: if LottieFiles bumps the runtime major version (currently v0.x) or the dotLottie spec (currently manifest v2, theme v1.0, state-machine v1.0), refresh.
2. **Ship reference docs organized by the eight themes** (creating, optimizing, integrating, dotLottie-advanced-features, motion-design-principles, implementations-landscape, sources-and-licensing, showcases). Include the exact prop/method tables and JSON spec snippets above — agents need verbatim names.
3. **Ship scripts:** (a) a dotlottie-js bundler (JSON→optimized `.lottie`, multi-animation, theme/state-machine injection); (b) an optimizer wrapper (precision reduction, strip unused assets, layer/keyframe audit via relottie); (c) a validator that checks animations against the ThorVG support matrix and flags expressions/audio/unsupported loops; (d) a reduced-motion + a11y wrapper generator for React/Vue/WC.
4. **Default conventions for generated code:** prefer `.lottie`; always `prefers-reduced-motion` handling; always `loadError` handling; `destroy()`/auto-cleanup; lazy-load offscreen; `DotLottieWorker` when >1 animation; SSR-safe dynamic import for Next.js; normalized `[R,G,B]` 0–1 for theme colors.
5. **Licensing guardrail:** when sourcing animations, record the per-file license; treat Lottie Simple License as commercial-OK/no-attribution but always verify the individual file and never re-host marketplace assets as free.

## Caveats
- **Version drift:** runtimes are v0.x and state-machine support is explicitly "early development"; APIs may change. Treat exact method names as current-as-of-2026 and re-verify against docs.lottiefiles.com.
- **Marketing statistics are not all reliable.** The widely repeated "humans process visuals 60,000x faster than text" is an unsourced/debunked claim traced to a 1997 3M brochure with no real citation — flag as marketing myth, not data. The 95% retention, 135% reach (Socialbakers, ~2014–15), and 20% conversion figures come from a 2022 LottieFiles article citing third parties; use as directional persuasion points only.
- **ThorVG vs lottie-web differences:** feature support and rendering differ between engines (e.g., DOM bloat is a lottie-web concern; expression coverage differs). Validate on the actual target renderer.
- **Bundle sizes** quoted in docs (React 45KB, JS 35KB, etc.), the "75% devicePixelRatio" default, and "~150KB runtime / 120+ FPS" are doc-stated and may vary by version.
- Some optimization specifics (fps mismatch anecdotes, precision-reduction numbers) come from third-party blogs, not primary LottieFiles/ThorVG docs.