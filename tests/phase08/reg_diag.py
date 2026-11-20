"""Registry diagnostic for CUIAutomation (run on the device)."""

import os
import sys
import winreg

print("python arch:", "64" if sys.maxsize > 2**32 else "32", "| exe:", sys.executable)
print("UIAutomationCore.dll exists:", os.path.exists(r"C:\Windows\System32\UIAutomationCore.dll"))

CLS_ID = "{ff48dba4-60ef-4201-aa87-54103eef604e}"
IUIA_ID = "{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}"

for root, name in ((winreg.HKEY_CLASSES_ROOT, "HKCR"), (winreg.HKEY_LOCAL_MACHINE, "HKLM-Classes")):
    for sub in (f"CLSID\\{CLS_ID}", f"CLSID\\{CLS_ID}\\InprocServer32", f"Interface\\{IUIA_ID}"):
        try:
            key = winreg.OpenKey(root, sub)
            print(f"{name}\\{sub}: EXISTS")
            winreg.CloseKey(key)
        except OSError as exc:
            print(f"{name}\\{sub}: MISSING (winerror={getattr(exc, 'winerror', '?')})")

# scan the CLSID hive for entries whose server is UIAutomationCore.dll
key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "CLSID")
found = []
index = 0
limit = 20000
while index < limit:
    try:
        sub = winreg.EnumKey(key, index)
    except OSError:
        break
    index += 1
    try:
        inner = winreg.OpenKey(key, sub + "\\InprocServer32")
        path = winreg.QueryValueEx(inner, "")[0]
        if "uiautomationcore" in str(path).lower():
            found.append((sub, str(path)))
        winreg.CloseKey(inner)
    except OSError:
        continue
winreg.CloseKey(key)
print("CLSIDs pointing at UIAutomationCore.dll:", found[:6], f"(scanned {index})")
