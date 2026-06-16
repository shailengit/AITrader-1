"""
Indicator Registry — unified catalog of technical indicators from all available sources.

Aggregates indicator metadata from:
  - ta (ta-lib wrapper)
  - vectorbt (VBT)
  - pandas-ta

Each indicator is a dict with the shape documented in get_indicator_catalog().
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# TA Indicators (ta library — ta-lib wrapper)
# ---------------------------------------------------------------------------

TA_INDICATORS: list[dict[str, Any]] = [
    # ── Momentum ──────────────────────────────────────────────────────────
    {
        "name": "RSI",
        "source": "ta",
        "category": "momentum",
        "description": "Relative Strength Index — measures speed and magnitude of price changes",
        "params": [
            {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.momentum import RSIIndicator\nrsi = RSIIndicator(close, window=14).rsi()",
        "pine_equivalent": "ta.rsi(src, len)",
    },
    {
        "name": "StochRSI",
        "source": "ta",
        "category": "momentum",
        "description": "Stochastic RSI — RSI value normalized to a 0-100 range using stochastic formula",
        "params": [
            {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "RSI lookback period"},
            {"name": "smooth1", "type": "int", "default": 3, "min": 1, "max": 50, "description": "Internal smoothing"},
            {"name": "smooth2", "type": "int", "default": 3, "min": 1, "max": 50, "description": "Output smoothing"},
        ],
        "code_snippet": "from ta.momentum import StochRSIIndicator\nstoch_rsi = StochRSIIndicator(close, window=14, smooth1=3, smooth2=3).stochrsi()",
        "pine_equivalent": "ta.stochrsi(src, len)",
    },
    {
        "name": "MACD",
        "source": "ta",
        "category": "momentum",
        "description": "Moving Average Convergence Divergence — trend-following momentum indicator",
        "params": [
            {"name": "window_fast", "type": "int", "default": 12, "min": 2, "max": 100, "description": "Fast EMA period"},
            {"name": "window_slow", "type": "int", "default": 26, "min": 2, "max": 200, "description": "Slow EMA period"},
            {"name": "window_sign", "type": "int", "default": 9, "min": 2, "max": 100, "description": "Signal line period"},
        ],
        "code_snippet": "from ta.momentum import MACD\nmacd = MACD(close, window_slow=26, window_fast=12, window_sign=9)\nhist = macd.macd_diff()",
        "pine_equivalent": "ta.macd(src, fastlen, slowlen, siglen)",
    },
    {
        "name": "Williams %R",
        "source": "ta",
        "category": "momentum",
        "description": "Williams Percent Range — overbought/oversold indicator comparing close to highest high",
        "params": [
            {"name": "lbp", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.momentum import WilliamsRIndicator\nwilliams_r = WilliamsRIndicator(high, low, close, lbp=14).williams_r()",
        "pine_equivalent": "ta.willr(src, len)",
    },
    {
        "name": "ROC",
        "source": "ta",
        "category": "momentum",
        "description": "Rate of Change — percentage change between current price and price n periods ago",
        "params": [
            {"name": "window", "type": "int", "default": 12, "min": 1, "max": 200, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.momentum import ROCIndicator\nroc = ROCIndicator(close, window=12).roc()",
        "pine_equivalent": "ta.roc(src, len)",
    },
    {
        "name": "Awesome Oscillator",
        "source": "ta",
        "category": "momentum",
        "description": "Awesome Oscillator — midpoint of 5-period vs 34-period simple moving average of median price",
        "params": [
            {"name": "window1", "type": "int", "default": 5, "min": 1, "max": 100, "description": "Short SMA period"},
            {"name": "window2", "type": "int", "default": 34, "min": 1, "max": 200, "description": "Long SMA period"},
        ],
        "code_snippet": "from ta.momentum import AwesomeOscillatorIndicator\nao = AwesomeOscillatorIndicator(high, low, window1=5, window2=34).awesome_oscillator()",
        "pine_equivalent": "ta.ao(high, low, fastlen, slowlen)",
    },
    {
        "name": "KAMA",
        "source": "ta",
        "category": "momentum",
        "description": "Kaufman's Adaptive Moving Average — EMA with smoothing factor adjusted by market noise",
        "params": [
            {"name": "window", "type": "int", "default": 10, "min": 2, "max": 100, "description": "Efficiency ratio period"},
            {"name": "pow1", "type": "int", "default": 2, "min": 1, "max": 10, "description": "Fast smoothing constant"},
            {"name": "pow2", "type": "int", "default": 30, "min": 1, "max": 50, "description": "Slow smoothing constant"},
        ],
        "code_snippet": "from ta.momentum import KAMAIndicator\nkama = KAMAIndicator(close, window=10, pow1=2, pow2=30).kama()",
        "pine_equivalent": "ta.kama(src, len)",
    },
    # ── Trend ────────────────────────────────────────────────────────────
    {
        "name": "EMA",
        "source": "ta",
        "category": "trend",
        "description": "Exponential Moving Average — places greater weight on recent prices",
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 1, "max": 200, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.trend import EMAIndicator\nema = EMAIndicator(close, window=20).ema_indicator()",
        "pine_equivalent": "ta.ema(src, len)",
    },
    {
        "name": "SMA",
        "source": "ta",
        "category": "trend",
        "description": "Simple Moving Average — arithmetic mean over a specified window",
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 1, "max": 200, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.trend import SMAIndicator\nsma = SMAIndicator(close, window=20).sma_indicator()",
        "pine_equivalent": "ta.sma(src, len)",
    },
    {
        "name": "ADX",
        "source": "ta",
        "category": "trend",
        "description": "Average Directional Index — measures trend strength regardless of direction",
        "params": [
            {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.trend import ADXIndicator\nadx = ADXIndicator(high, low, close, window=14).adx()",
        "pine_equivalent": "ta.adx(high, low, close, len)",
    },
    {
        "name": "Aroon",
        "source": "ta",
        "category": "trend",
        "description": "Aroon — identifies whether a security is trending and the strength of that trend",
        "params": [
            {"name": "window", "type": "int", "default": 25, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.trend import AroonIndicator\naroon = AroonIndicator(close, window=25)\naroon_up = aroon.aroon_up()\naroon_down = aroon.aroon_down()",
        "pine_equivalent": "ta.aroon(high, low, len)",
    },
    {
        "name": "PSAR",
        "source": "ta",
        "category": "trend",
        "description": "Parabolic Stop and Reverse — trailing stop-and-reversal indicator",
        "params": [
            {"name": "step", "type": "float", "default": 0.02, "min": 0.001, "max": 0.5, "description": "Acceleration factor step"},
            {"name": "max_step", "type": "float", "default": 0.2, "min": 0.01, "max": 1.0, "description": "Maximum acceleration factor"},
        ],
        "code_snippet": "from ta.trend import PSARIndicator\npsar = PSARIndicator(high, low, close, step=0.02, max_step=0.2).psar()",
        "pine_equivalent": "ta.sar(high, low, start, inc, max)",
    },
    {
        "name": "Ichimoku Cloud",
        "source": "ta",
        "category": "trend",
        "description": "Ichimoku Kinko Hyo — comprehensive indicator showing support/resistance, trend direction, and momentum",
        "params": [
            {"name": "window1", "type": "int", "default": 9, "min": 2, "max": 100, "description": "Tenkan-sen period"},
            {"name": "window2", "type": "int", "default": 26, "min": 2, "max": 100, "description": "Kijun-sen period"},
            {"name": "window3", "type": "int", "default": 52, "min": 2, "max": 200, "description": "Senkou Span B period"},
        ],
        "code_snippet": "from ta.trend import IchimokuIndicator\nichimoku = IchimokuIndicator(high, low, window1=9, window2=26)\ntenkan = ichimoku.ichimoku_conversion_line()\nkijun = ichimoku.ichimoku_base_line()",
        "pine_equivalent": "ta.ichimoku(high, low, tenkan, kijun, senkou)",
    },
    {
        "name": "CCI",
        "source": "ta",
        "category": "trend",
        "description": "Commodity Channel Index — identifies cyclical trends and overbought/oversold levels",
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "Lookback period"},
            {"name": "constant", "type": "float", "default": 0.015, "min": 0.001, "max": 0.1, "description": "Divisor constant"},
        ],
        "code_snippet": "from ta.trend import CCIIndicator\ncci = CCIIndicator(high, low, close, window=20, constant=0.015).cci()",
        "pine_equivalent": "ta.cci(high, low, close, len)",
    },
    # ── Volume ───────────────────────────────────────────────────────────
    {
        "name": "OBV",
        "source": "ta",
        "category": "volume",
        "description": "On-Balance Volume — cumulative volume indicator relating volume to price change",
        "params": [],
        "code_snippet": "from ta.volume import VolumeWeightedAveragePrice\n# OBV via ta library\nobv = (close.diff().gt(0) * volume + close.diff().lt(0) * -volume).cumsum()",
        "pine_equivalent": "ta.obv(src, volume)",
    },
    {
        "name": "MFI",
        "source": "ta",
        "category": "volume",
        "description": "Money Flow Index — volume-weighted RSI measuring buying/selling pressure",
        "params": [
            {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.volume import MFIIndicator\nmfi = MFIIndicator(high, low, close, volume, window=14).money_flow_index()",
        "pine_equivalent": "ta.mfi(high, low, close, volume, len)",
    },
    {
        "name": "Chaikin Money Flow",
        "source": "ta",
        "category": "volume",
        "description": "Chaikin Money Flow — accumulation/distribution volume over a specified period",
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.volume import ChaikinMoneyFlowIndicator\ncmf = ChaikinMoneyFlowIndicator(high, low, close, volume, window=20).chaikin_money_flow()",
        "pine_equivalent": "ta.cmf(high, low, close, volume, len)",
    },
    {
        "name": "Volume Price Trend",
        "source": "ta",
        "category": "volume",
        "description": "Volume Price Trend (VPT) — cumulative volume-adjusted price trend",
        "params": [],
        "code_snippet": "from ta.volume import VolumePriceTrendIndicator\nvpt = VolumePriceTrendIndicator(close, volume).volume_price_trend()",
        "pine_equivalent": "ta.pvt(src, volume)",
    },
    # ── Volatility ──────────────────────────────────────────────────────
    {
        "name": "Bollinger Bands",
        "source": "ta",
        "category": "volatility",
        "description": "Bollinger Bands — volatility bands placed above and below a moving average",
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "SMA period"},
            {"name": "window_dev", "type": "int", "default": 2, "min": 1, "max": 5, "description": "Standard deviation multiplier"},
        ],
        "code_snippet": "from ta.volatility import BollingerBands\nbb = BollingerBands(close, window=20, window_dev=2)\nbb_upper = bb.bollinger_hband()\nbb_lower = bb.bollinger_lband()",
        "pine_equivalent": "ta.bb(src, len, mult)",
    },
    {
        "name": "Average True Range",
        "source": "ta",
        "category": "volatility",
        "description": "Average True Range — market volatility measure based on high-low range",
        "params": [
            {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "from ta.volatility import AverageTrueRange\natr = AverageTrueRange(high, low, close, window=14).average_true_range()",
        "pine_equivalent": "ta.atr(high, low, close, len)",
    },
]

# ---------------------------------------------------------------------------
# VectorBT Indicators
# ---------------------------------------------------------------------------

VBT_INDICATORS: list[dict[str, Any]] = [
    {
        "name": "VBT MA",
        "source": "vectorbt",
        "category": "trend",
        "description": "VectorBT Moving Average — flexible MA supporting SMA, EMA, WMA, etc.",
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 1, "max": 200, "description": "Lookback period"},
            {"name": "ewm", "type": "bool", "default": False, "description": "Use exponential weighting if True"},
        ],
        "code_snippet": "import vectorbt as vbt\nma = vbt.MA.run(close, window=20, ewm=False).ma",
        "pine_equivalent": "ta.sma(src, len) / ta.ema(src, len)",
    },
    {
        "name": "VBT RSI",
        "source": "vectorbt",
        "category": "momentum",
        "description": "VectorBT RSI — Relative Strength Index with vectorized computation",
        "params": [
            {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "import vectorbt as vbt\nrsi = vbt.RSI.run(close, window=14).rsi",
        "pine_equivalent": "ta.rsi(src, len)",
    },
    {
        "name": "VBT BBANDS",
        "source": "vectorbt",
        "category": "volatility",
        "description": "VectorBT Bollinger Bands — volatility bands with vectorized computation",
        "params": [
            {"name": "window", "type": "int", "default": 20, "min": 2, "max": 100, "description": "SMA period"},
            {"name": "alpha", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "description": "Standard deviation multiplier"},
        ],
        "code_snippet": "import vectorbt as vbt\nbb = vbt.BBANDS.run(close, window=20, alpha=2)\nupper = bb.upper\nlower = bb.lower",
        "pine_equivalent": "ta.bb(src, len, mult)",
    },
    {
        "name": "VBT MACD",
        "source": "vectorbt",
        "category": "momentum",
        "description": "VectorBT MACD — Moving Average Convergence Divergence with vectorized computation",
        "params": [
            {"name": "fast_window", "type": "int", "default": 12, "min": 2, "max": 100, "description": "Fast EMA period"},
            {"name": "slow_window", "type": "int", "default": 26, "min": 2, "max": 200, "description": "Slow EMA period"},
            {"name": "signal_window", "type": "int", "default": 9, "min": 2, "max": 100, "description": "Signal line period"},
        ],
        "code_snippet": "import vectorbt as vbt\nmacd = vbt.MACD.run(close, fast_window=12, slow_window=26, signal_window=9)\nhist = macd.histogram",
        "pine_equivalent": "ta.macd(src, fastlen, slowlen, siglen)",
    },
    {
        "name": "VBT STOCH",
        "source": "vectorbt",
        "category": "momentum",
        "description": "VectorBT Stochastic Oscillator — compares close to high-low range over a period",
        "params": [
            {"name": "k_window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "%K lookback period"},
            {"name": "d_window", "type": "int", "default": 3, "min": 1, "max": 50, "description": "%D smoothing period"},
        ],
        "code_snippet": "import vectorbt as vbt\nstoch = vbt.STOCH.run(high, low, close, k_window=14, d_window=3)\nk = stoch.percent_k\nd = stoch.percent_d",
        "pine_equivalent": "ta.stoch(high, low, close, klen, dlen)",
    },
    {
        "name": "VBT ATR",
        "source": "vectorbt",
        "category": "volatility",
        "description": "VectorBT Average True Range — volatility measure with vectorized computation",
        "params": [
            {"name": "window", "type": "int", "default": 14, "min": 2, "max": 100, "description": "Lookback period"}
        ],
        "code_snippet": "import vectorbt as vbt\natr = vbt.ATR.run(high, low, close, window=14).atr",
        "pine_equivalent": "ta.atr(high, low, close, len)",
    },
    {
        "name": "VBT OBV",
        "source": "vectorbt",
        "category": "volume",
        "description": "VectorBT On-Balance Volume — cumulative volume indicator with vectorized computation",
        "params": [],
        "code_snippet": "import vectorbt as vbt\nobv = vbt.OBV.run(close, volume).obv",
        "pine_equivalent": "ta.obv(src, volume)",
    },
]

# ---------------------------------------------------------------------------
# pandas-ta Indicators
# ---------------------------------------------------------------------------

PANDAS_TA_INDICATORS: list[dict[str, Any]] = [
    {
        "name": "Supertrend",
        "source": "pandas-ta",
        "category": "trend",
        "description": "Supertrend — trend-following indicator based on ATR that provides buy/sell signals",
        "params": [
            {"name": "length", "type": "int", "default": 10, "min": 2, "max": 100, "description": "ATR period"},
            {"name": "multiplier", "type": "float", "default": 3.0, "min": 0.5, "max": 10.0, "description": "ATR multiplier"},
        ],
        "code_snippet": "import pandas_ta as ta\ntrend = ta.supertrend(high, low, close, length=10, multiplier=3)",
        "pine_equivalent": "ta.supertrend(high, low, close, len, mult)",
    },
    {
        "name": "TTM Squeeze",
        "source": "pandas-ta",
        "category": "volatility",
        "description": "TTM Squeeze — identifies Bollinger Band/Keltner Channel squeeze setups for breakout trading",
        "params": [
            {"name": "length", "type": "int", "default": 20, "min": 2, "max": 100, "description": "BB/KC period"},
            {"name": "bb_mult", "type": "float", "default": 2.0, "min": 0.5, "max": 5.0, "description": "Bollinger Band multiplier"},
            {"name": "kc_mult", "type": "float", "default": 1.5, "min": 0.5, "max": 5.0, "description": "Keltner Channel multiplier"},
        ],
        "code_snippet": "import pandas_ta as ta\nsqz = ta.squeeze(high, low, close, length=20, bb_mult=2.0, kc_mult=1.5)",
        "pine_equivalent": "ta.squeeze(high, low, close, len, bb_mult, kc_mult)",
    },
    {
        "name": "KDJ",
        "source": "pandas-ta",
        "category": "momentum",
        "description": "KDJ — Chinese variant of the Stochastic Oscillator with a third line (J)",
        "params": [
            {"name": "length", "type": "int", "default": 9, "min": 2, "max": 100, "description": "Lookback period"},
            {"name": "signal", "type": "int", "default": 3, "min": 1, "max": 50, "description": "Signal line smoothing"},
        ],
        "code_snippet": "import pandas_ta as ta\nkdj = ta.kdj(high, low, close, length=9, signal=3)",
        "pine_equivalent": "ta.stoch(high, low, close, klen, dlen) with J = 3*K - 2*D",
    },
]

# ---------------------------------------------------------------------------
# Combined catalog
# ---------------------------------------------------------------------------

_ALL_INDICATORS: list[dict[str, Any]] = TA_INDICATORS + VBT_INDICATORS + PANDAS_TA_INDICATORS


def get_indicator_catalog(
    category: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return the full indicator catalog, optionally filtered.

    Parameters
    ----------
    category : str, optional
        Filter by category (``"momentum"``, ``"trend"``, ``"volatility"``, ``"volume"``).
    search : str, optional
        Case-insensitive substring match against indicator name or description.

    Returns
    -------
    list[dict]
        Matching indicator dicts.
    """
    result = _ALL_INDICATORS

    if category:
        result = [i for i in result if i["category"] == category]

    if search:
        q = search.lower()
        result = [
            i
            for i in result
            if q in i["name"].lower() or q in i["description"].lower()
        ]

    return result


def get_indicator_sources() -> list[str]:
    """Return the list of available indicator source names."""
    return ["ta", "vectorbt", "pandas-ta"]


def get_indicator_categories() -> list[str]:
    """Return the list of available indicator categories."""
    return ["momentum", "trend", "volatility", "volume"]
