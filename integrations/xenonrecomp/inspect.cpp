#include <image.h>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include <cstdlib>
int main(int argc, char** argv) {
    if (argc != 3) { std::cerr << "Usage: aster-xex-inspect INPUT.xex OUTPUT.pe\n"; return 2; }
    try {
        std::ifstream file(argv[1], std::ios::binary);
        if (!file) return 3;
        std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)), {});
        if (data.size() < 24) return 4;
        if (setenv("ASTER_XEX_PE_OUTPUT", argv[2], 1)) return 5;
        auto image = Image::ParseImage(data.data(), data.size());
        if (!image.data) return 6;
        std::cout << "{\"image_base\":" << image.base << ",\"entry_point\":" << image.entry_point
                  << ",\"image_size\":" << image.size << ",\"section_count\":" << image.sections.size()
                  << ",\"import_symbols\":" << image.symbols.size()
                  << ",\"export_phase\":\"decoded-before-import-rewrites\",\"executed_game\":false}\n";
        return 0;
    } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 7; }
}
