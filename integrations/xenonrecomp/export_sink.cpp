// Analysis hook only. No game is executed; the original XEX remains read-only.
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <stdexcept>
void AsterDecodedImage(const uint8_t* bytes, size_t size) {
    const char* path = std::getenv("ASTER_XEX_PE_OUTPUT");
    if (!path) return;
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out || !out.write(reinterpret_cast<const char*>(bytes), size))
        throw std::runtime_error("Could not export decoded PE");
}
