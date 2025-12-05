import pandas as pd
import numpy as np

# ============================================================
# Required Columns in DF:
# df = pd.DataFrame({
#   'open','high','low','close','volume','timestamp'
# })
# timestamp must be pandas datetime
# ============================================================

def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def vwap(df):
    q = df['volume']
    p = df['close']
    return (p * q).cumsum() / q.cumsum()

def compute_intraday_strategy(df,
                              ema_len=200,
                              vol_len=20,
                              vol_mult=1.5,
                              rr_ratio=1.6,
                              vwap_dist_pct=0.15,
                              sl_buffer_pct=0.08,
                              only_first_break=True,
                              avoid_lunch=True,
                              trade_start="0915",
                              trade_end="1525"):

    df = df.copy()

    # ============================================================
    # Indicators
    # ============================================================

    df["EMA200"] = ema(df["close"], ema_len)
    df["VWAP"] = vwap(df)
    df["VolMA"] = df["volume"].rolling(vol_len).mean()

    # Previous Day High/Low (PDH / PDL)
    df["date"] = df["timestamp"].dt.date
    daily_high = df.groupby("date")["high"].max().shift(1)
    daily_low  = df.groupby("date")["low"].min().shift(1)

    df["PDH"] = df["date"].map(daily_high)
    df["PDL"] = df["date"].map(daily_low)

    # Time numeric (HHMM)
    df["HH"] = df["timestamp"].dt.hour
    df["MM"] = df["timestamp"].dt.minute
    df["curTime"] = df["HH"] * 100 + df["MM"]

    trade_start = int(trade_start)
    trade_end = int(trade_end)

    # Session logic
    df["in_session"] = (df["curTime"] >= trade_start) & (df["curTime"] <= trade_end)
    df["in_lunch"] = avoid_lunch & (df["curTime"].between(1200, 1330))
    df["can_trade"] = df["in_session"] & (~df["in_lunch"])

    # ============================================================
    # Conditions
    # ============================================================

    df["vol_ok"] = df["volume"] > (df["VolMA"] * vol_mult)

    df["dist_pct"] = (df["close"] - df["VWAP"]).abs() / df["VWAP"] * 100
    df["vwap_ok"] = df["dist_pct"] >= vwap_dist_pct

    df["uptrend"] = df["close"] > df["EMA200"]
    df["downtrend"] = df["close"] < df["EMA200"]

    # Breakouts
    df["long_break"] = (df["close"] > df["PDH"]) & (df["close"].shift(1) <= df["PDH"])
    df["short_break"] = (df["close"] < df["PDL"]) & (df["close"].shift(1) >= df["PDL"])

    # ============================================================
    # Execution Loop (Tick-by-tick)
    # ============================================================

    trades = []
    longTakenToday = False
    shortTakenToday = False
    active_position = None

    prev_date = None

    for i in range(len(df)):

        row = df.iloc[i]
        cur_date = row["date"]

        # Reset daily flags at new day
        if prev_date is not None and cur_date != prev_date:
            longTakenToday = False
            shortTakenToday = False
        prev_date = cur_date

        # Forced square-off at session end
        if row["curTime"] == trade_end and active_position is not None:
            entry, sl, tp, side = active_position

            trades.append({
                "entry_time": entry["timestamp"],
                "exit_time": row["timestamp"],
                "entry_price": entry["close"],
                "exit_price": row["close"],
                "side": side,
                "reason": "Forced Square-Off"
            })
            active_position = None
            continue

        # If a trade is running, check SL/TP
        if active_position is not None:
            entry, sl, tp, side = active_position

            if side == "LONG":
                # SL hit
                if row["low"] <= sl:
                    trades.append({
                        "entry_time": entry["timestamp"],
                        "exit_time": row["timestamp"],
                        "entry_price": entry["close"],
                        "exit_price": sl,
                        "side": side,
                        "reason": "SL Hit"
                    })
                    active_position = None
                    continue

                # TP hit
                if row["high"] >= tp:
                    trades.append({
                        "entry_time": entry["timestamp"],
                        "exit_time": row["timestamp"],
                        "entry_price": entry["close"],
                        "exit_price": tp,
                        "side": side,
                        "reason": "TP Hit"
                    })
                    active_position = None
                    continue

            if side == "SHORT":
                if row["high"] >= sl:
                    trades.append({
                        "entry_time": entry["timestamp"],
                        "exit_time": row["timestamp"],
                        "entry_price": entry["close"],
                        "exit_price": sl,
                        "side": side,
                        "reason": "SL Hit"
                    })
                    active_position = None
                    continue

                if row["low"] <= tp:
                    trades.append({
                        "entry_time": entry["timestamp"],
                        "exit_time": row["timestamp"],
                        "entry_price": entry["close"],
                        "exit_price": tp,
                        "side": side,
                        "reason": "TP Hit"
                    })
                    active_position = None
                    continue

        # No new entries if position is open
        if active_position is not None:
            continue

        # === Entry Logic ===

        # Long Entry
        if (
            row["can_trade"] and
            row["vol_ok"] and
            row["vwap_ok"] and
            row["uptrend"] and
            row["long_break"] and
            (not longTakenToday)
        ):
            sl_vwap = row["VWAP"] * (1 - sl_buffer_pct/100)
            sl = min(sl_vwap, row["low"])
            if sl < row["close"]:
                risk = row["close"] - sl
                tp = row["close"] + (risk * rr_ratio)
                active_position = (row, sl, tp, "LONG")
                longTakenToday = True

        # Short Entry
        elif (
            row["can_trade"] and
            row["vol_ok"] and
            row["vwap_ok"] and
            row["downtrend"] and
            row["short_break"] and
            (not shortTakenToday)
        ):
            sl_vwap = row["VWAP"] * (1 + sl_buffer_pct/100)
            sl = max(sl_vwap, row["high"])
            if sl > row["close"]:
                risk = sl - row["close"]
                tp = row["close"] - (risk * rr_ratio)
                active_position = (row, sl, tp, "SHORT")
                shortTakenToday = True

    return pd.DataFrame(trades)
