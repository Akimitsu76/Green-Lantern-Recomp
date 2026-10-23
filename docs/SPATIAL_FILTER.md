# Linux spatial presentation and asynchronous pipelines

This update targets the pinned ReXGlue 0.10.0 Linux x86-64 SDK. It does not
include guest assets, replacement HD textures, or generated game code.

`0003-vulkan-deferred-pipelines.patch` applies after the driver-cache patch.
It queues new real graphics pipelines without compiling a temporary pipeline
on the command processor. Pending draws use the existing complete-frame
preservation policy. Vertex/pixel memory-export shaders retain synchronous
creation because skipping them could change guest-visible memory. Translation,
loading and the first real pipeline can still cause delays; this is not a
zero-stutter guarantee. Creation failure clears the pending state for retry.

The original host library in `integrations/rexglue/presenter-filter` interposes
only the SDK's final paint-pipeline creation. It supplies a bounded Catmull-Rom
reconstruction fragment shader for `cubic` and modest local-contrast sharpening
for `sharp`. Neighborhood clamping limits ringing. There is no temporal history,
motion-vector assumption or modification to the game's render targets. Internal
rendering remains at 1x; window output can be 1920x1080 or higher. Bilinear stays
available. The spatial variants also support bounded screen-space dithering.

The module also retains the swapchain format after successful pipeline creation
(the missing assignment reported in upstream issue #507), so the final pipeline
is reused. It is compiled against the pinned SDK's private C++ layout and must
not be used with another SDK version or a FidelityFX-enabled SDK build.
`LD_PRELOAD` and `ASTER_PRESENT_FILTER` are set only for the game child. Build
artifacts are recorded and verified by SHA-256 before launch. It has no Windows
D3D12 implementation yet.

The arena lifetime shim immediately unlinks only a `/xenia_memory_*` object
successfully and exclusively created by that call. Its open descriptor and
mappings remain valid until the last reference closes. It never removes an
existing arena and prevents `_Exit` from leaving new named arenas behind.

The public SPIR-V headers are generated from `spatial.frag` using
`glslangValidator -V` (for sharp, add `-DASTER_SHARP=1`). Encode the resulting
little-endian uint32 words as `cubic_spirv` / `sharp_spirv` arrays.
For the `_dither` variants add `-DASTER_DITHER=1`. All variants
were checked with `spirv-val`; end-to-end verification still requires comparing
actual game-window captures. Source and header hashes are part of the build key.

## Experimental AMD EASU option

`fsr1` now selects AMD's unmodified FSR 1 EASU edge-adaptive reconstruction through the original Vulkan presenter adapter. It is an EASU-only integration, not the complete EASU+RCAS pipeline: no separate RCAS sharpening pass is implemented. The existing `sharp` option remains the separate bounded cubic filter. No temporal history, synthesized motion vectors, neural model or frame generation is used.

The source remains 720p. EASU is applied only for enlargement between 1x and 2x per axis (1080p/1440p for a 720p source); at 1:1, downscaling or above 2x it falls back to bilinear. Use explicit 1920x1080 output for initial testing. This bounds the filter to the intended scaling range; 4K chained EASU is not implemented. The entire final image, including HUD, is filtered.

Upstream headers and MIT license are included verbatim, with pinned revision and hashes in FSR-SOURCE.json. Run `python3 scripts/generate_presenter_shaders.py` to regenerate and spirv-val-check all six variants. Selecting EASU requires integration recipe 6 and a regenerated local presenter; older installations must be updated first. Windows has no EASU adapter yet.
