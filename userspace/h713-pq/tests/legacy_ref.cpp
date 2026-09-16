/*
 * legacy_ref.cpp -- comparison harness against the legacy calculator.
 *
 * Builds against legacy/userspace/hy310-pqd/{include,src}/pqgamma.{h,cpp} and
 * writes the DE2 bank (512 u32, little endian) for one gamma exponent into a
 * file. With that the output of
 *     h713-pq gamma <exp> --lut out.bin
 * can be compared byte by byte.
 *
 * Building (example):
 *   g++ -O2 -std=c++17 -I <pqd>/include \
 *       <pqd>/src/pqgamma.cpp tests/legacy_ref.cpp -o /tmp/legacy_ref
 * Call:
 *   /tmp/legacy_ref 2.2 /tmp/legacy.bin
 *
 * Note: GammaWriter::pack_lut is private. The packing formula is documented
 * word for word in pqgamma.cpp, in pqgamma.h and in BACKGROUND.md section 5.4
 * and is rebuilt here; the curve computation itself
 * (GammaCurve::from_exponent + interpolate) comes unchanged out of the legacy
 * code. No /dev/mem is opened.
 */
#include "pqgamma.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace hy310::pqgamma;

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: %s <exponent> <output file>\n", argv[0]);
        return 2;
    }
    const double exp = std::atof(argv[1]);

    GammaCurve c = GammaCurve::from_exponent(exp);
    std::array<int16_t, LUT_ENTRIES> lut = interpolate(c);

    unsigned char raw[LUT_BULK_DWORDS * 4];
    for (size_t i = 0; i < LUT_BULK_DWORDS; ++i) {
        uint32_t even = static_cast<uint32_t>(lut[2 * i])     & LUT_SAMPLE_MASK;
        uint32_t odd  = static_cast<uint32_t>(lut[2 * i + 1]) & LUT_SAMPLE_MASK;
        uint32_t w    = (odd << LUT_SAMPLE_BITS) | even;
        raw[4 * i + 0] = static_cast<unsigned char>(w & 0xFF);
        raw[4 * i + 1] = static_cast<unsigned char>((w >> 8) & 0xFF);
        raw[4 * i + 2] = static_cast<unsigned char>((w >> 16) & 0xFF);
        raw[4 * i + 3] = static_cast<unsigned char>((w >> 24) & 0xFF);
    }

    FILE* f = std::fopen(argv[2], "wb");
    if (!f) {
        std::perror("fopen");
        return 1;
    }
    std::fwrite(raw, 1, sizeof(raw), f);
    std::fclose(f);

    /* Control numbers for the night log. */
    std::printf("exponent=%.4f points[0]=%d points[16]=%d points[32]=%d "
                "lut[0]=%d lut[512]=%d lut[1023]=%d bytes=%zu\n",
                exp, c.points[0], c.points[16], c.points[32],
                lut[0], lut[512], lut[LUT_ENTRIES - 1], sizeof(raw));
    return 0;
}
