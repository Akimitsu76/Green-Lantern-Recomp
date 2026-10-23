// Delimited native codegen experiment. Never invokes the game's entry point.
#include <recompiler.h>
#include <file.h>
#include <iostream>
int main(int argc, char** argv) {
    if (argc != 5) return 2; // SOURCE.xex ADDRESS OUTPUT_DIR PPC_CONTEXT_TEMPLATE
    try {
        auto file = LoadFile(argv[1]);
        Recompiler r;
        r.image = Image::ParseImage(file.data(), file.size());
        const auto address = std::stoull(argv[2], nullptr, 0);
        const Section* code = nullptr;
        for (const auto& s : r.image.sections)
            if ((s.flags & SectionFlags_Code) && address >= s.base && address+8 <= s.base+s.size) code=&s;
        if (!code) return 3;
        auto* bytes = static_cast<const uint8_t*>(r.image.Find(address));
        // Admit only the independently validated 2-instruction accessor for this experiment.
        const auto instruction = ByteSwap(*reinterpret_cast<const uint32_t*>(bytes));
        const auto last = ByteSwap(*reinterpret_cast<const uint32_t*>(bytes+4));
        if ((instruction >> 26) != 32 || ((instruction >> 21)&31)!=3 ||
            ((instruction >> 16)&31)!=3 || last != 0x4e800020) return 4;
        auto fn=Function::Analyze(bytes, 8, address);
        if (fn.size != 8) return 5;
        r.image.symbols.clear();
        r.image.symbols.emplace("aster_game_leaf", address, 8, Symbol_Function);
        if (!r.Recompile(fn)) return 6;
        r.out.clear();
        r.functions.push_back(fn);
        r.config.outDirectoryPath = argv[3];
        std::filesystem::create_directories(argv[3]);
        r.Recompile(argv[4]);
        std::cout << "ASTER_LEAF_GENERATED address=" << std::hex << address << " bytes=8\n";
        return 0;
    } catch(const std::exception& e) { std::cerr << e.what() << '\n'; return 7; }
}
