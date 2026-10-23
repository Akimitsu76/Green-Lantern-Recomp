# Persisting translated SPIR-V — feasibility review only

The driver-cache patch does **not** skip guest microcode translation. The current
`InitializeShaderStorage` obtains shader variants from `.xpso`, reads original
microcode from `.xsh`, analyzes it and calls the SPIR-V translator again. A warm
`VkPipelineCache` may reduce driver compilation, but cannot bypass that CPU work.

A separate translated-SPIR-V cache is feasible, but saving `.spv` keyed only by
shader hash would be incorrect. No such shortcut was implemented in this task.

A safe cache key needs explicit, canonical serialization of at least:

- Schema/revision plus the exact translator/build fingerprint, including patched
  sources and pinned glslang SPIR-V builder version. A release name alone cannot
  invalidate a locally changed translator.
- Guest shader type and original microcode digest/length, plus complete 64-bit
  shader modification. Keep original `.xsh` available for validation and fallback.
- Every `SpirvShaderTranslator::Features` field: SPIR-V version, maximum storage
  buffer range, full draw indices, vertex/fragment storage atomics, clip/cull
  distance, image-view swizzle, float preservation/denorm/rounding behavior,
  fragment sample interlock, demote-to-helper, and sample-rate shading.
- FSI/FBO selection, native 2x MSAA capabilities with/without attachments, and both
  draw-resolution scale dimensions. These are constructor inputs, not all encoded
  in the shader modification.
- Any subsequently introduced code-generation options. Serialize individual
  numeric/boolean fields; never hash raw C++ structs with padding or bitfields.

Vulkan device/driver identity can conservatively partition a first implementation
in addition to the feature fingerprint. Correct portability needs a feature and
SPIR-V target-environment contract; reusing an opaque driver cache and reusing
SPIR-V have different compatibility rules.

Restoring only the bytecode is insufficient. `Shader::Translation` privately owns
`is_translated_`, `is_valid_`, errors and translated bytes. In addition,
`SpirvShaderTranslator::PostTranslation` sets `SpirvShader` texture bindings,
sampler bindings and used-texture mask. These drive descriptor and pipeline layout
construction. Skipping that state restoration risks wrong textures, descriptor
layouts or crashes even when the SPIR-V module itself is accepted.

A follow-up implementation should add reviewed import/export APIs to the shader
classes/translator, publish an immutable validated translation and matching
resource metadata under the existing synchronization model, and retain microcode
analysis for runtime metadata that remains necessary. Cached binding bitfields
must be stored as explicit fields and range-checked. Shader module handles and
other process/driver handles must never be serialized.

Validate bounded file lengths, checksums, SPIR-V word alignment/magic/version,
entry point/stage, target capabilities and resource metadata before use. Run
SPIR-V validation against the chosen Vulkan target environment. Cache misses,
corruption or validation/module-creation failure must fall back to normal
translation; publish the cache only after successful translation/module handling,
using same-directory temporary files and replacement.

Before claiming success, compare cold and warm launches of identical scenes,
report separate counters for microcode analysis, translation hits/misses, driver
pipeline creation, total prewarm time and frame-time stalls. Test all key changes,
corrupt files, simultaneous access, cancellation and shutdown. New shader variants
will still require translation and driver work.

Files that would need API changes include
`include/rex/graphics/pipeline/shader/shader.h`,
`include/rex/graphics/pipeline/shader/spirv.h`, and their translator implementations,
in addition to Vulkan pipeline storage. Those are intentionally outside this
task's two-file SDK patch; no unsafe private-state mutation was added.
