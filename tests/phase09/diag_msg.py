
import ctypes, ctypes.wintypes as wt
print("MSG fields:", [f[0] for f in wt.MSG._fields_])
print("MSG size:", ctypes.sizeof(wt.MSG))
print("ver:", __import__("sys").version)
