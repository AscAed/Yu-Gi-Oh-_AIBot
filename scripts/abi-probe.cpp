#include <cstddef>
#include <windows.h>
#include "ocgapi_types.h"
static_assert(sizeof(OCG_CardData) == 64);
static_assert(offsetof(OCG_CardData, race) == 32);
static_assert(sizeof(OCG_DuelOptions) == 136);
static_assert(offsetof(OCG_DuelOptions, cardReader) == 64);
static_assert(sizeof(OCG_NewCardInfo) == 24);
static_assert(sizeof(OCG_QueryInfo) == 20);
int main(int argc, char** argv) {
    if(argc != 2) return 1;
    auto lib = LoadLibraryA(argv[1]);
    if(!lib) return 2;
    auto version = reinterpret_cast<void (*)(int*, int*)>(GetProcAddress(lib, "OCG_GetVersion"));
    if(!version) return 3;
    int major = 0, minor = 0;
    version(&major, &minor);
    FreeLibrary(lib);
    return (major == 11 && minor == 0) ? 0 : 4;
}
