import pefile
for dll in [r'C:\Users\vamanuel\Documents\openob_windows\openob-embedded-installer\packaging\openob_runtime\gvsbuild\bin\glib-2.0-0.dll',
            r'C:\Users\vamanuel\Documents\openob_windows\openob-embedded-installer\packaging\openob_runtime\gvsbuild\bin\ffi-8.dll']:
    pe=pefile.PE(dll)
    imports = [getattr(entry,'dll').decode() for entry in getattr(pe,'DIRECTORY_ENTRY_IMPORT',[])]
    print(dll,'imports:',imports)
