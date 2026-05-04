from backend.main import app
for r in sorted(app.routes, key=lambda r: getattr(r, "path", str(r))):
    methods = sorted(getattr(r, "methods", set()) or {"WS"})
    print(f"  {'|'.join(methods):<10} {getattr(r, 'path', '?')}")
