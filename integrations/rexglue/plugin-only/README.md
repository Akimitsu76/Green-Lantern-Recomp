# Isolated GPU plugin rebuild scaffold

The Release plugin compiled successfully after human session 027. That artifact
has not been validated in-game: probe 028 loaded the original **RelWithDebInfo**
plugin and is a baseline, not a test of this patch. A matching RelWithDebInfo
build is now pending validation. No build was performed during session 027.

This scaffold reuses the v0.10.0 SDK's imported runtime and static third-party libraries,
compiling only the Xenos GPU plugin's 35 translation units. It never builds
rexcore/rexui or links their OBJECT libraries, and has no install/staging rule.

The local source HEAD and package version match the reviewed v0.10.0 release. The
only source class layout change is internal `VulkanPipelineCache`, allocated by
the rebuilt plugin itself. GPU plugin ABI checks remain in upstream entry points.
This makes the approach plausible, not yet proven: linking with `--no-undefined`,
checking exported entry points/dependencies and an isolated runtime smoke test
remain mandatory. A successful link alone cannot prove C++ ABI compatibility.

The SDK package provides required static archives but omits glslang headers.
The matching glslang headers were populated for the Release build at the
SDK-pinned commit `f4f1d8a352ca1908943aea2ad8c54b39b4879080`;
there is no reason to recursively fetch/build FFmpeg or the other dependencies
for this experiment. The scaffold rejects a wrong glslang commit. The SDK ships
precompiled Vulkan helper shader headers, so regeneration of those is unnecessary.

The game executable uses **RelWithDebInfo**, so its loader selects
`librexgpu-xenosrd.so` and `librexruntimerd.so`. The matching plugin must use
RelWithDebInfo too: the configuration enables profiling/performance definitions,
and matching the shared runtime and Tracy ABI is essential. Renaming a Release
`.so` to an `rd.so` does not establish compatibility and is not a valid fix.
The imported target configuration selects the SDK's matching `rd` libraries.

Commands for the matching RelWithDebInfo build, after session 027 has ended and
its status/report have been finalized:

```bash
git -C .aster/tools/rexglue-sdk submodule update --init thirdparty/glslang
.aster/tools/cmake-runtime/cmake/data/bin/cmake \
  -S integrations/rexglue/plugin-only \
  -B .aster/build/rexglue-cache-review-rd -G Ninja \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_C_COMPILER=clang \
  -DCMAKE_CXX_COMPILER=clang++
.aster/tools/cmake-runtime/cmake/data/bin/cmake \
  --build .aster/build/rexglue-cache-review-rd --target aster_rexgpu_xenos -j 4
```

These commands document the integration procedure; this documentation update
did not configure or build anything. Configure
and each build invocation refuse a session 027 status marked `running`. The build
also refuses non-Linux/non-x86_64, non-Clang, Clang older than 18, multi-config and
configurations other than Release or RelWithDebInfo. An ended status is not permission to interfere with
another active game session: check actual processes before starting a build.

Expected output:
`.aster/build/rexglue-cache-review-rd/isolated-runtime/librexgpu-xenosrd.so`.
Its RPATH points to the existing SDK runtime, not the game's staged plugin.
Check that it resolves **librexruntimerd.so** and the expected Tracy dependency.
The earlier Release artifact remains in `.aster/build/rexgpu-cache-review` and
requires a matching Release host for an independent test. Review `readelf`, `ldd -r`, exported `rex_gpu_abi_version`/`rex_gpu_create`,
and record hashes. During the smoke test, verify the exact mapped plugin path
and SHA-256 via process maps/probe evidence, and confirm the new driver-cache log
messages. A successful launch with the original plugin validates only baseline
behavior. Do not copy over a live loaded plugin. Stage a separate
experimental runtime only after linking and dependency checks pass. Keep the old
plugin for rollback, and update probe/launcher identity metadata consistently.
No runtime, game CPU recompilation or shader prewarm command is invoked here.

If headers or link symbols still disagree, stop and use a matching full SDK build
in a fresh build/install prefix. Do not remove `--no-undefined`, change class
layouts, substitute system glslang, or add fake symbol definitions to force a link.
