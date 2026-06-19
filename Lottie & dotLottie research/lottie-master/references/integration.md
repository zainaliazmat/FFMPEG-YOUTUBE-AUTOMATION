# Using Lottie in projects (every framework)

Player versions verified current at build time. The modern `@lottiefiles/dotlottie-*`
family renders **both** `.json` and `.lottie` (point `src` at either) on a Rust+WASM
/ ThorVG core. The legacy `lottie-web` family renders `.json` only but has the widest
historical footprint. **Default to the dotLottie players** for new work.

## Pick a player
| Target | Package | Notes |
|--------|---------|-------|
| Vanilla web (canvas) | `@lottiefiles/dotlottie-web` | imperative `DotLottie` class |
| Web, zero build | `@lottiefiles/dotlottie-wc` | `<dotlottie-wc>` custom element via CDN |
| React | `@lottiefiles/dotlottie-react` | `DotLottieReact` component |
| Vue | `@lottiefiles/dotlottie-vue` | `DotLottieVue` |
| Svelte | `@lottiefiles/dotlottie-svelte` | `DotLottieSvelte` |
| SolidJS | `@lottiefiles/dotlottie-solid` | `DotLottieSolid` |
| React (legacy, .json) | `lottie-react` | community wrapper over `lottie-web` |
| Vanilla (legacy, .json) | `lottie-web` | the original Airbnb/Bodymovin player |
| React Native | `lottie-react-native` | native iOS/Android rendering |
| Flutter | `lottie` (pub.dev) | |
| iOS native | `lottie-ios` (Swift PM/CocoaPods) | |
| Android native | `com.airbnb.android:lottie` | |

Runtime needs for the WASM players: **WebAssembly + Canvas 2D + Fetch**; Node **18+**
for SSR/thumbnailing. Web Workers / OffscreenCanvas / WebGL2 / WebGPU are optional
performance enhancers.

---

## Web — no build step (web component)
```html
<dotlottie-wc src="/anim/spinner.lottie" autoplay loop
              style="width:200px;height:200px"></dotlottie-wc>
<script type="module"
  src="https://unpkg.com/@lottiefiles/dotlottie-wc@latest/dist/dotlottie-wc.js"></script>
```

## Web — vanilla JS (canvas, full control)
```bash
npm install @lottiefiles/dotlottie-web
```
```js
import { DotLottie } from "@lottiefiles/dotlottie-web";
const dotLottie = new DotLottie({
  canvas: document.querySelector("#canvas"),
  src: "/anim/spinner.lottie",     // .lottie OR .json
  autoplay: true,
  loop: true,
});
// control it
dotLottie.play(); dotLottie.pause(); dotLottie.stop();
dotLottie.setSpeed(1.5);
dotLottie.setFrame(30);
dotLottie.addEventListener("complete", () => console.log("done"));
```

## React
```bash
npm install @lottiefiles/dotlottie-react
```
```jsx
import { DotLottieReact } from "@lottiefiles/dotlottie-react";

export default function Loader() {
  return <DotLottieReact src="/anim/spinner.lottie" loop autoplay
                         style={{ width: 200, height: 200 }} />;
}
```
**Props:** `src` (URL to .json/.lottie) · `data` (inline JSON string or ArrayBuffer)
· `loop` · `autoplay` · `speed` · `mode` (`"forward" | "reverse" | "bounce" |
"reverse-bounce"`) · `backgroundColor` (`"#RRGGBB"`/`"#RRGGBBAA"`) · `renderConfig`
· `dotLottieRefCallback`. It extends `<canvas>` props.

**Custom playback controls** via the ref callback:
```jsx
import { useRef } from "react";
import { DotLottieReact } from "@lottiefiles/dotlottie-react";

function Player() {
  const ref = useRef(null);
  return (
    <>
      <DotLottieReact src="/anim/spinner.lottie" autoplay loop
        dotLottieRefCallback={(dl) => (ref.current = dl)} />
      <button onClick={() => ref.current?.play()}>Play</button>
      <button onClick={() => ref.current?.pause()}>Pause</button>
      <button onClick={() => ref.current?.setFrame(30)}>Seek 30</button>
      <button onClick={() => ref.current?.setTheme("dark")}>Dark theme</button>
    </>
  );
}
```

## Next.js (App Router) — must disable SSR
The WASM player needs browser APIs, so load it client-only:
```jsx
"use client";
import dynamic from "next/dynamic";
const DotLottieReact = dynamic(
  () => import("@lottiefiles/dotlottie-react").then((m) => m.DotLottieReact),
  { ssr: false }
);
export default function Hero() {
  return <DotLottieReact src="/anim/hero.lottie" autoplay loop />;
}
```
Put `.lottie`/`.json` files under `public/` and reference them with an absolute path.

## Vue
```vue
<script setup>
import { DotLottieVue } from "@lottiefiles/dotlottie-vue";
</script>
<template>
  <DotLottieVue style="height:200px;width:200px" autoplay loop
                src="/anim/spinner.lottie" />
</template>
```

## Svelte
```svelte
<script>
  import { DotLottieSvelte } from "@lottiefiles/dotlottie-svelte";
</script>
<DotLottieSvelte src="/anim/spinner.lottie" loop autoplay />
```

## Legacy React (`lottie-react`, `.json` only)
Handy when you already have a `.json` and want the classic API or `lottieRef`:
```jsx
import Lottie from "lottie-react";
import animationData from "./spinner.json";   // import the JSON directly
export default () => <Lottie animationData={animationData} loop autoplay />;
```

## React Native
```bash
npm install lottie-react-native
```
```jsx
import LottieView from "lottie-react-native";
export default () => (
  <LottieView source={require("./spinner.json")} autoPlay loop
              style={{ width: 200, height: 200 }} />
);
```

## Flutter
```yaml
# pubspec.yaml
dependencies:
  lottie: ^3.0.0
```
```dart
import 'package:lottie/lottie.dart';
Lottie.asset('assets/spinner.json', repeat: true);   // or Lottie.network(url)
```

## iOS (Swift) & Android (Kotlin)
```swift
import Lottie                          // lottie-ios
let v = LottieAnimationView(name: "spinner")
v.loopMode = .loop; v.play()
```
```kotlin
// layout: <com.airbnb.lottie.LottieAnimationView app:lottie_fileName="spinner.json"
//          app:lottie_autoPlay="true" app:lottie_loop="true"/>
lottieView.playAnimation()
```

---

## Performance knobs (web)
- **Renderer backend**: import from `@lottiefiles/dotlottie-web` (software, safe
  default), or the `/webgl` or `/webgpu` entry points for GPU rendering of heavy
  scenes. Benchmark on the LottieFiles Perf Playground before committing.
- **Off-thread**: use the worker entry / `OffscreenCanvas` to keep the main thread
  free when several animations play at once.
- **Pause when offscreen**: gate playback with an `IntersectionObserver`; don't
  animate what isn't visible. This is the biggest real-world win.
- **Size the canvas to display size** and cap device pixel ratio for huge screens.
- See `references/optimization.md` for shrinking the file itself.
