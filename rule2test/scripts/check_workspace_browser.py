"""Run the standalone-suite browser regression against an isolated temporary database."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    try:import playwright
    except ImportError:
        print('Install requirements-browser.txt and run python -m playwright install chromium.',file=sys.stderr)
        return 2
    tests=unittest.defaultTestLoader.loadTestsFromName('tests.integration.test_workspace_rendering')
    result=unittest.TextTestRunner(verbosity=2).run(tests)
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
