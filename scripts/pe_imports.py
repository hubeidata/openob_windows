import pefile
pe=pefile.PE(r'C:\Users\vamanuel\Documents\openob_windows\openob-embedded-installer\packaging\openob_runtime\gvsbuild\bin\girepository-1.0-1.dll')
imports = []
for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
    dll = getattr(entry, 'dll', None)
    if dll:
        imports.append(dll.decode() if isinstance(dll, bytes) else dll)
print('imports:', imports)
