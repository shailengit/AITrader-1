# Code Review: Task 6 - MarkovSignalProvider (Backtest Bridge)

## Files to review

### 1. `backend/app/services/markov/signal_provider.py` (NEW - 148 lines)
- Injects into QuantGen's exec() sandbox via executor.py
- Serves pre-computed historical signals for backtesting
- O(1) lookup per (ticker, date) pair
- Builds cache from scratch each time (trains recognizer, runs predictions)

### 2. `backend/app/services/executor.py` (MODIFIED - line 39 import + line 312 exec_globals entry)
- Adds `from app.services.markov.signal_provider import MarkovSignalProvider`
- Registers `"MarkovSignalProvider": MarkovSignalProvider` in exec_globals

### 3. `backend/tests/services/markov/test_signal_provider.py` (NEW - 24 lines)
- Three tests: initial state, unknown ticker regime, cache key format

## What to evaluate

### Code Quality
1. Does each file have one clear responsibility with a well-defined interface?
2. Are units decomposed so they can be understood and tested independently?
3. Is the implementation following the file structure from the plan?
4. Did this implementation create new files that are already large, or significantly grow existing files?

### Duplication with SignalGenerator
signal_provider.py has ~60% overlap with signal_generator.py:
- Same regime + recognizer loading pattern
- Same convergence rules (is_bull + is_low_vol + is_buy)
- Both build same Dict structure for signals
- But signal_provider is for backtesting (pre-computed batch, date-keyed lookup) while signal_generator is for live scanning (single-row prediction, latest ticker features)

Is this acceptable duplication for a backtest-or-live split, or should they share a common base?

### Correctness
- Does _build_cache() have any bugs?
  - The date keying (line 88-89): `date.strftime('%Y-%m-%d')`
  - Missing date fallback (lines 121, 130, 139): `cache.get(list(cache.keys())[-1] if cache else '')`
  - What happens when `feat_data` has no rows? The `predictions.index` loop would be empty
  - The `None` vs zero-length check: `if feat_data is None: return False` but what about empty DataFrame?

### Test coverage
- Are the tests meaningful or just "doesn't crash" tests?
- What's NOT tested: _build_cache(), get_signal() with actual populated cache, lazily initializing regime manager, etc.