import sys, importlib.util, shutil
sys.path.insert(0, r"M:\NEXUS")
mods = ["pytesseract", "PIL", "winsdk", "winrt", "tesseract"]
for m in mods:
    print("module", m, ":", bool(importlib.util.find_spec(m)))
print("tesseract binary:", shutil.which("tesseract"))
try:
    import pytesseract
    print("tesseract version:", pytesseract.get_tesseract_version())
except Exception as e:
    print("tesseract probe:", type(e).__name__, str(e)[:120])
