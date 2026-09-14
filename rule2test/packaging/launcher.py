"""Frozen-build entry point. Keeps PyInstaller's analysis rooted at one import."""
import multiprocessing,sys
from factory.app import main

if __name__=="__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
