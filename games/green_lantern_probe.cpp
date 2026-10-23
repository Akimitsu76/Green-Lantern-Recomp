// Original test harness for one recompiled accessor. No game entry/runtime.
#include "ppc_recomp_shared.h"
#include <array>
#include <cstdint>
#include <cstring>
#include <iostream>
int main() {
    alignas(32) std::array<uint8_t,1024> memory{};
    constexpr uint32_t pointer = 512;
    constexpr uint32_t displacement = 4;
    uint32_t state=0x12345678;
    for (uint32_t test=0; test<10000; ++test) {
        state = state * 1664525u + 1013904223u;
        PPCContext ctx{};
        ctx.r3.u64 = pointer;
        ctx.r4.u64 = 0xFEDCBA9876543210ull;
        ctx.lr = 0xCAFEBABEu;
        // Independent reference: lwz zero-extends a big-endian 32-bit memory word.
        memory[pointer+displacement] = static_cast<uint8_t>(state>>24);
        memory[pointer+displacement+1] = static_cast<uint8_t>(state>>16);
        memory[pointer+displacement+2] = static_cast<uint8_t>(state>>8);
        memory[pointer+displacement+3] = static_cast<uint8_t>(state);
        const auto original = memory;
        aster_game_leaf(ctx,memory.data());
        if (ctx.r3.u64 != state || ctx.r4.u64 != 0xFEDCBA9876543210ull ||
            ctx.lr != 0xCAFEBABEu || memory != original) return 1;
    }
    std::cout << "{\"native_cases_passed\":10000,\"guest_function\":\"0x823968F8\","
                 "\"scope\":\"lwz-accessor-only\",\"game_ready\":false}\n";
}
