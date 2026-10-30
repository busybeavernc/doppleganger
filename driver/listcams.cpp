// listcams.exe - prints the system's video capture devices, one per line, as UTF-8,
// in DirectShow enumeration order (the same order OpenCV's CAP_DSHOW indexes use).
// Build: cl /O2 /EHsc /utf-8 listcams.cpp ole32.lib oleaut32.lib strmiids.lib
#include <windows.h>
#include <dshow.h>
#include <cstdio>
#include <string>

static std::string utf8(const wchar_t* w) {
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
    return s;
}

int main() {
    if (FAILED(CoInitializeEx(nullptr, COINIT_MULTITHREADED))) return 2;
    ICreateDevEnum* devEnum = nullptr;
    IEnumMoniker* enumMon = nullptr;
    int rc = 0;
    if (FAILED(CoCreateInstance(CLSID_SystemDeviceEnum, nullptr, CLSCTX_INPROC_SERVER,
                                IID_ICreateDevEnum, (void**)&devEnum))) {
        rc = 3;
    } else if (devEnum->CreateClassEnumerator(CLSID_VideoInputDeviceCategory, &enumMon, 0) == S_OK) {
        IMoniker* mon = nullptr;
        while (enumMon->Next(1, &mon, nullptr) == S_OK) {
            IPropertyBag* bag = nullptr;
            std::string name = "(unnamed camera)";
            if (SUCCEEDED(mon->BindToStorage(nullptr, nullptr, IID_IPropertyBag, (void**)&bag))) {
                VARIANT v;
                VariantInit(&v);
                if (SUCCEEDED(bag->Read(L"FriendlyName", &v, nullptr)) && v.vt == VT_BSTR)
                    name = utf8(v.bstrVal);
                VariantClear(&v);
                bag->Release();
            }
            std::printf("%s\n", name.c_str());
            mon->Release();
        }
        enumMon->Release();
    }
    if (devEnum) devEnum->Release();
    CoUninitialize();
    return rc;
}
