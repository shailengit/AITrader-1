import importlib.util, os, sys
os.environ.setdefault("DB_USER", "postgres")
os.environ.setdefault("DB_PASSWORD", "sarina00")
os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "5431")
os.environ.setdefault("DB_NAME", "sp1500_1d")
_gc_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "strategies", "golden_cross.py")
_spec = importlib.util.spec_from_file_location("gc_under_test", _gc_path)
_gc = importlib.util.module_from_spec(_spec)
sys.modules["gc_under_test"] = _gc
_spec.loader.exec_module(_gc)
def precompute(t, s, e): return _gc.precompute(t, s, e)
def entry_score(c, st): return _gc.entry_score(c, st)
def holding_score(t, d, h, st): return _gc.holding_score(t, d, h, st)
def exit_check(t, d, h, db): return _gc.exit_check(t, d, h, db)
def build_config(as_of=None, end=None, capital=None):
    return _gc.build_config(as_of=as_of, end=end, capital=capital)
