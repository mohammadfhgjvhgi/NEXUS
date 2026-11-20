import ctypes
class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]
def guid(t):
    d = t.strip("{}").replace("-", "")
    g = GUID()
    g.Data1 = int(d[0:8], 16); g.Data2 = int(d[8:12], 16); g.Data3 = int(d[12:16], 16)
    for i in range(8):
        g.Data4[i] = int(d[16 + i*2: 18 + i*2], 16)
    return g
clsid = guid("{ff48dba4-60ef-4201-aa87-54103eef604e}")
iid = guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")
ole32 = ctypes.windll.ole32
print("CoInitializeEx:", hex(ole32.CoInitializeEx(None, 0) & 0xFFFFFFFF))
pp = ctypes.c_void_p()
for ctx, name in ((1, "INPROC_SERVER"), (4, "LOCAL_SERVER"), (0x17, "ALL")):
    pp = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, ctx, ctypes.byref(iid), ctypes.byref(pp))
    print(f"CoCreateInstance[{name}] hr = {hex(hr & 0xFFFFFFFF)} ptr = {pp.value}")
