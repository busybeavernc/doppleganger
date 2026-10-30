// micmute.exe - mute/unmute the PC's microphones at the Windows level (every app hears silence).
//   micmute mute            mutes every active, currently-unmuted microphone; prints the ids it muted
//   micmute unmute id ...   unmutes exactly those ids (so mics you had muted yourself stay muted)
//   micmute list            prints "id<TAB>muted" for each active microphone
// Build: cl /O2 /EHsc /utf-8 micmute.cpp ole32.lib
#include <windows.h>
#include <mmdeviceapi.h>
#include <endpointvolume.h>
#include <cstdio>
#include <cwchar>
#include <string>

static std::string utf8(const wchar_t* w) {
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
    return s;
}

static IAudioEndpointVolume* volumeOf(IMMDevice* dev) {
    IAudioEndpointVolume* vol = nullptr;
    if (FAILED(dev->Activate(__uuidof(IAudioEndpointVolume), CLSCTX_ALL, nullptr, (void**)&vol))) return nullptr;
    return vol;
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 2) { std::fprintf(stderr, "usage: micmute mute|unmute <ids>|list\n"); return 1; }
    if (FAILED(CoInitializeEx(nullptr, COINIT_MULTITHREADED))) return 2;
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                                __uuidof(IMMDeviceEnumerator), (void**)&en))) return 3;
    int rc = 0;
    if (std::wcscmp(argv[1], L"unmute") == 0) {
        for (int i = 2; i < argc; i++) {
            IMMDevice* dev = nullptr;
            if (FAILED(en->GetDevice(argv[i], &dev))) { rc = 4; continue; }
            if (IAudioEndpointVolume* vol = volumeOf(dev)) { vol->SetMute(FALSE, nullptr); vol->Release(); }
            dev->Release();
        }
    } else {
        bool doMute = std::wcscmp(argv[1], L"mute") == 0;
        IMMDeviceCollection* col = nullptr;
        if (SUCCEEDED(en->EnumAudioEndpoints(eCapture, DEVICE_STATE_ACTIVE, &col))) {
            UINT n = 0;
            col->GetCount(&n);
            for (UINT i = 0; i < n; i++) {
                IMMDevice* dev = nullptr;
                if (FAILED(col->Item(i, &dev))) continue;
                LPWSTR id = nullptr;
                dev->GetId(&id);
                if (IAudioEndpointVolume* vol = volumeOf(dev)) {
                    BOOL muted = FALSE;
                    vol->GetMute(&muted);
                    if (doMute && !muted) {
                        if (SUCCEEDED(vol->SetMute(TRUE, nullptr))) std::printf("%s\n", utf8(id).c_str());
                    } else if (!doMute) {
                        std::printf("%s\t%d\n", utf8(id).c_str(), muted ? 1 : 0);
                    }
                    vol->Release();
                }
                CoTaskMemFree(id);
                dev->Release();
            }
            col->Release();
        }
    }
    en->Release();
    CoUninitialize();
    return rc;
}
