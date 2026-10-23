# Validated update — 22/10/2026

The final RD plugin was built and exercised by probes 030–033. The cold run
persisted 22,743,770 payload bytes; the warm run loaded them. A deliberately
corrupted cache was rejected and rebuilt without a fatal. The plugin and warm
cache were staged to the main runtime with rollback copies preserved.
See docs/GRAPHICS_POLISH.md for measured scope and remaining issues.

A shutdown-only prototype did not persist on the host exit path (029). The final
patch saves after preload and from the storage thread every ten seconds when dirty,
in addition to normal shutdown. Earlier preparation notes below are historical.

# Persistent Vulkan driver cache — proposed SDK patch

Patch: `0001-vulkan-driver-pipeline-cache.patch`, against ReXGlue SDK v0.10.0,
commit `f5337cdc947ff6d4c4196737e2c807a48f2a1fc2`.

Status: the isolated **Release** GPU plugin compiled successfully, but has not
been loaded in a validated game run. Probe 028 loaded the original
**RelWithDebInfo** plugin and is baseline evidence only. The game uses the `rd`
configuration; a matching RelWithDebInfo plugin build is pending runtime
validation. No compilation or game restart was performed during human session
027. `git diff --check` and reverse-application check pass. Driver validation and
a two-launch comparison of the actually mapped patched plugin remain required.

The existing `.xsh` and `.xpso` files retain guest microcode and pipeline recipes,
not the Vulkan driver's compiled pipeline payload. This patch creates a
`VkPipelineCache`, supplies it to graphics pipeline creation, loads its previous
payload at shader-storage initialization, and saves snapshots after preload, on a dirty-cache timer in the storage
thread, and on orderly storage shutdown. It does not change rendering flags or shader translations.

Files live below the caller's cache root in `shaders/driver/`, separated by title,
FSI/FBO, format revision, pointer width, GPU vendor/device, driver version, Vulkan
API version and `pipelineCacheUUID`. There is no shared/cloud cache.

The file envelope records a magic/version, byte count and XXH3 checksum. Reads
reject size mismatch, payload corruption, incompatible Vulkan headers and GPU
UUIDs. Driver rejection retries an empty cache; unavailable entry points or
cache creation failure leaves ordinary uncached pipeline creation working.
A driver cache can still be internally ignored even when initialization succeeds;
the initialization byte count is not a cache-hit measurement.

Parallel graphics creation shares the default internally synchronized Vulkan
cache under shared locks. Cache replacement, snapshot queries and destruction
hold an exclusive lock, preventing mutation between size and payload queries.
Shutdown already joins creation workers before final storage shutdown. No new
worker, render command, background input or focus change is introduced.

The patch bounds file reads and serialization allocations at 64 MiB and discards
`VK_INCOMPLETE` snapshots. It cannot cap the driver's internal cache allocation.
Writes use an exclusive-create temporary file in the same directory, flush and
close it, then rename over the destination. Failed replacement preserves the old
complete file; the implementation does not delete the destination as a fallback.
This is not a power-loss durability guarantee (no fsync). Concurrent separate
processes do not merge cache contents: the last successful complete writer wins.

Limitations:

- Guest microcode analysis/translation to SPIR-V still occurs at startup.
- Shaders/pipelines never previously encountered still require creation.
- Shader changes, GPU/driver changes and render variants may need new compilation.
- Persistence occurs after preload and every ten seconds when dirty. An abnormal
  crash can lose entries since the last successful snapshot. Existing `.xsh`/`.xpso` behavior remains.
- No claim of zero compilation, faster startup, corrected shadows or lower GPU
  load is justified until measured. Release compilation passed; the patched
  plugin has not yet been validated in a runtime session.
- The temporary-file/replace path targets the project's Linux environment; Windows
  replacement semantics require separate validation.

## Integrate only after the human closes the game

1. Preserve the shipped SDK and runtime hashes. Use a separate SDK source/build
   and install prefix, never overwrite a loaded `librexgpu-xenos`.
2. On a clean SDK checkout at the commit above, `git apply --check` then apply the
   patch. The current `.aster/tools/rexglue-sdk` already contains these edits;
   do not apply twice. Initialize its normal dependencies as needed.
3. Prefer the [plugin-only scaffold](../plugin-only/README.md), which reuses
   matching SDK libraries. Use CMake 3.31, Clang 18 or later, Ninja and C++23 in
   `.aster/build/rexglue-cache-review-rd`, with
   `-DCMAKE_BUILD_TYPE=RelWithDebInfo`, and build `aster_rexgpu_xenos`. This host
   loads `librexgpu-xenosrd.so` against `librexruntimerd.so`; Release output named
   `librexgpu-xenos.so` is not selected. Do not rename a Release library to bypass
   configuration selection. A full SDK alternative must use a separate build/
   install prefix, the same configuration and matching runtime dependencies.
   Never mix SDK versions or Release/RelWithDebInfo ABIs.
4. Stage a separate experimental game runtime and record all new binary hashes.
   Confirm the exact mapped plugin path and hash during each probe, its matching
   `rd` runtime/Tracy dependencies, and the driver-cache initialization/snapshot
   messages. Probe 028 does not satisfy this step because it used the original
   plugin. Update launcher identity/probe metadata only after validation.
5. With Vulkan validation enabled where available, exercise first launch with no
   driver cache, orderly exit, and second launch of the same recorded scene.
   Confirm nonzero persisted and loaded byte counts; compare startup duration,
   frame-time distribution and pipeline creation behavior. Logs saying "Creating
   graphics pipeline" can still occur on a driver-cache hit.
6. In a disposable copy, test truncated/oversized/bad-checksum cache, mismatched
   UUID/header, unwritable directory and failed rename. Each must fall back
   without removing an existing valid destination or affecting original game data.
7. Test shutdown during shader warm-up and the asynchronous creation mode. Avoid
   treating shader-cache reuse alone as proof that the driver avoided compilation.

Primary requirements consulted:

- [VkPipelineCacheCreateInfo](https://docs.vulkan.org/refpages/latest/refpages/source/VkPipelineCacheCreateInfo.html): initial bytes must come from previously retrieved driver cache data; this patch leaves synchronization flags zero.
- [vkGetPipelineCacheData](https://docs.vulkan.org/refpages/latest/refpages/source/vkGetPipelineCacheData.html): query size before retrieval and handle `VK_INCOMPLETE` without publishing a partial snapshot.
