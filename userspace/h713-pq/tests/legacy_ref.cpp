/*
 * legacy_ref.cpp -- Vergleichsharness gegen den Legacy-Rechner.
 *
 * Baut gegen legacy/userspace/hy310-pqd/{include,src}/pqgamma.{h,cpp} und
 * schreibt die DE2-Bank (512 u32, little-endian) fuer einen Gamma-Exponenten
 * in eine Datei. Damit laesst sich die Ausgabe von
 *     h713-pq gamma <exp> --lut out.bin
 * byteweise vergleichen.
 *
 * Bauen (Beispiel):
 *   g++ -O2 -std=c++17 -I <pqd>/include \
 *       <pqd>/src/pqgamma.cpp tests/legacy_ref.cpp -o /tmp/legacy_ref
 * Aufruf:
 *   /tmp/legacy_ref 2.2 /tmp/legacy.bin
 *
 * Hinweis: GammaWriter::pack_lut ist privat. Die Packformel ist in
 * pqgamma.cpp, in pqgamma.h und in BACKGROUND.md Abschnitt 5.4 wortgleich
 * dokumentiert und wird hier nachgebildet; die eigentliche Kurvenrechnung
 * (GammaCurve::from_exponent + interpolate) kommt unveraendert aus dem
 * Legacy-Code. Es wird kein /dev/mem geoeffnet.
 */
#include "pqgamma.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace hy310::pqgamma;

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "Aufruf: %s <exponent> <ausgabedatei>\n", argv[0]);
        return 2;
    }
    const double exp = std::atof(argv[1]);

    GammaCurve c = GammaCurve::from_exponent(exp);
    std::array<int16_t, LUT_ENTRIES> lut = interpolate(c);

    unsigned char roh[LUT_BULK_DWORDS * 4];
    for (size_t i = 0; i < LUT_BULK_DWORDS; ++i) {
        uint32_t even = static_cast<uint32_t>(lut[2 * i])     & LUT_SAMPLE_MASK;
        uint32_t odd  = static_cast<uint32_t>(lut[2 * i + 1]) & LUT_SAMPLE_MASK;
        uint32_t w    = (odd << LUT_SAMPLE_BITS) | even;
        roh[4 * i + 0] = static_cast<unsigned char>(w & 0xFF);
        roh[4 * i + 1] = static_cast<unsigned char>((w >> 8) & 0xFF);
        roh[4 * i + 2] = static_cast<unsigned char>((w >> 16) & 0xFF);
        roh[4 * i + 3] = static_cast<unsigned char>((w >> 24) & 0xFF);
    }

    FILE* f = std::fopen(argv[2], "wb");
    if (!f) {
        std::perror("fopen");
        return 1;
    }
    std::fwrite(roh, 1, sizeof(roh), f);
    std::fclose(f);

    /* Kontrollzahlen fuer den Nachtlog. */
    std::printf("exponent=%.4f punkte[0]=%d punkte[16]=%d punkte[32]=%d "
                "lut[0]=%d lut[512]=%d lut[1023]=%d bytes=%zu\n",
                exp, c.points[0], c.points[16], c.points[32],
                lut[0], lut[512], lut[LUT_ENTRIES - 1], sizeof(roh));
    return 0;
}
