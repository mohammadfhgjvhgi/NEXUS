import sys, traceback
sys.path.insert(0, r"M:\NEXUS")
print("python:", sys.version.split()[0], "| platform:", sys.platform)
try:
    from nexus.vision.benchmark import render_text_png
    png = render_text_png("Hello World 123")
    print("RENDER OK, bytes:", len(png))
except Exception:
    print("RENDER FAILED — traceback:")
    traceback.print_exc()
