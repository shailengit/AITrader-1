"""conftest for strategies tests.

No sys.path mods needed — tests use importlib.util.spec_from_file_location
to load engine.py / golden_cross.py directly, avoiding the name collision
with the pre-existing `backend/strategies/` (strategy catalog) package.
"""
