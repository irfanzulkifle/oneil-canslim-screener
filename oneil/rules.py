"""Every threshold the screen uses, in one file.

The rule this module enforces: a number that decides whether a stock appears
must exist as a named constant, not as prose in a document. When the same
threshold is written down twice, the two copies drift, and a screen quietly
starts measuring something other than what its author believed.

Values below are the production values used by my daily and weekly scans.
The comments say what each one is for and, where relevant, which proxy it
stands in for.
"""
from __future__ import annotations

# --- Stage 1: universe -------------------------------------------------------
# Daily scan floor. Below this, price and volume are too thin for a position
# to be entered or exited without moving the tape.
UNIVERSE_MIN_MCAP = 300_000_000
UNIVERSE_TOP_BY_VOLUME = 500

# Weekly scan floor. O'Neil's own screens are biased to liquid names; the
# weekly list is the one used for trade candidates, so the floor is higher.
WEEKLY_MIN_MCAP = 1_000_000_000
WEEKLY_TOP_BY_VOLUME = 300

# --- Stage 2: weekly O'Neil gate (the "where" clause) ------------------------
# Price above both the 10-week and 30-week moving averages, with weekly
# RSI(7) above 60. This is the gate that decides whether a name is SEEN at all.
WEEK_MA_FAST = 10
WEEK_MA_SLOW = 30
RSI7_WEEKLY_MIN = 60.0

# --- Stage 3: weekly CAN SLIM scoring ---------------------------------------
EPS_GROWTH_MIN_PCT = 25.0          # C (quarterly) and A (annual) pass mark
RSI7_WEEKLY_SCORE_BAND = (55.0, 85.0)   # L: trend, not exhaustion
NEAR_HIGH_MAX_DRAWDOWN = -10.0     # N: within 10% of the 52-week high
REL_VOLUME_MIN = 1.0               # M: at least average volume

# --- Stage 3b: DAILY CAN SLIM screen ----------------------------------------
# The daily screen and the weekly screen are separate systems with separate
# thresholds, and the N factor is the one place they legitimately differ:
# the weekly candidate list is the trade list, so it demands a tighter base
# (within 10%); the daily screen is a wider net that also feeds the weekly, so
# it tolerates 15%. Do not collapse these into one number — they answer
# different questions and a shared constant would silently change one of them.
DAILY_NEAR_HIGH_MAX_DRAWDOWN = -15.0   # N: within 15% of the 52-week high
ANALYST_MARK_MIN = 0.1             # I: analyst mark above this counts as backing
MIN_SCREENER_PASSES = 3            # pipeline floor; the live daily scan keeps >= 4
ANALYST_BUY_SHARE_BONUS = 0.5      # more than half of analysts rating buy
REL_VOLUME_SURGE_BONUS = 1.2       # up day on this multiple earns M bonus

# --- Stage 4: chart audit (daily bars) --------------------------------------
SMA_WINDOWS = (20, 50, 200)        # alignment: 20 > 50 > 200
RS_LINE_LOOKBACK = 63              # ~3 months of sessions
RS_LINE_TOLERANCE = 0.99           # within 1% of the 3-month ratio high
VDU_RECENT_DAYS = 3                # volume dry-up: last 3 sessions
VDU_BASELINE_DAYS = 50             # ... against the prior 50
VDU_MAX_RATIO = 0.60               # < 60% of baseline = dry-up
VCP_RECENT_DAYS = 5                # contraction: last 5 sessions
VCP_PRIOR_DAYS = 20                # ... against the prior 20
VCP_MAX_CONTRACTION = 0.50         # half the prior range or tighter
RS_3M_DAYS = 63
CHART_CHECKS = 5                   # one point per check, 0-5

# --- Stage 4b: weekly volume dry-up + accumulation weeks ---------------------
WEEKLY_VDU_BASELINE_WEEKS = 10     # completed weeks
WEEKLY_VDU_MAX_RATIO = 0.60
ACCUM_UP_DOWN_VOL_MIN = 1.5        # up-week volume / down-week volume
ACCUM_LOOKBACK_WEEKS = 5
BASE_LOOKBACK_WEEKS = 6            # multi-week base detector window
BASE_MIN_ACCUMULATION_WEEKS = 3    # of the last 6
READY_MAX_DISTANCE_TO_HIGH = -5.0  # "ready to break out": within 5% of high

# --- Stage 5: ranking -------------------------------------------------------
W_SCREENER = 0.6
W_CHART = 0.4

# Sector M factor (O'Neil: buy in the leading sectors).
M_TOP_SECTOR_RANKS = 3
M_SECOND_TIER_RANKS = 6
M_LAGGARD_RANK = 10
M_TOP_BOOST = 0.5
M_SECOND_BOOST = 0.2
M_LAGGARD_PENALTY = -0.3

# Arithmetic maximum of the rank. If a gate is ever set above this, the gate
# is not strict, it is broken: nothing can satisfy it.
FINAL_RANK_CEILING = (
    6 * W_SCREENER + CHART_CHECKS * W_CHART + M_TOP_BOOST
)  # 6.1

FINAL_RANK_MIN = 4.0       # baseline quality: screen >= 5, chart >= 2
FINAL_RANK_STRONG = 4.5    # strong: screen >= 5, chart >= 3

# --- Deploy gates -----------------------------------------------------------
VIX_MAX = 20.0

# The 10-year yield gate is a shock detector, not a level ban. A level-based
# rule ("> 4.80% = halt") stayed on for 76 consecutive sessions in 2026 and
# blocked every trade while the market was fine. A rate *shock* is what flushes
# growth names, so the operative test is the change over ten sessions.
TENY_SHOCK_BP = 25.0
TENY_SHOCK_LOOKBACK = 10
TENY_HALF_SIZE_LEVEL = 4.60       # above this: half size, not a ban
TENY_LEGACY_HALT_LEVEL = 4.80     # retained only for the legacy absolute mode
USE_ABSOLUTE_HALT = False
