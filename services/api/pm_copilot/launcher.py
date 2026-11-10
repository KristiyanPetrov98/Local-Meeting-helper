"""One executable dispatches only fixed private worker entry points."""
import importlib
import json
import multiprocessing
import sys

def main():
    multiprocessing.freeze_support()
    if len(sys.argv)==3 and sys.argv[1]=='--worker':
        from .runtime import MODULES
        module=MODULES.get(sys.argv[2])
        if not module:raise SystemExit(2)
        raise SystemExit(importlib.import_module(module).main())
    if len(sys.argv)>1:raise SystemExit(2)
    from .__main__ import main as serve
    serve()

if __name__=='__main__':main()
