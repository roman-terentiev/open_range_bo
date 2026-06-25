import pandas as pd


def get_atr_stop_dist(df, window, rate):
    df = df.copy()
    df_daily = df.resample("1D").agg({
        "high": "max", 
        "low": "min", 
        "close": "last",
        "adj_high": "max", 
        "adj_low": "min", 
        "adj_close": "last"
    }).dropna()

    prev_close = df_daily["adj_close"].shift(1)
    tr = pd.concat([
        df_daily["adj_high"] - df_daily["adj_low"],
        (df_daily["adj_high"] - prev_close).abs(),
        (df_daily["adj_low"] - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = (
        tr
        .rolling(window, min_periods=window)
        .mean()
        .shift(1)
        .reindex(df.index.normalize())
        .set_axis(df.index)
    )

    df["atr_stop_dist"] = atr * rate
    return df.ffill().dropna()


def get_open_range(df_sessions, time_start, time_end):
    df_ranges = df_sessions.between_time(time_start, time_end)
    open_range_high = df_ranges["high"].groupby(df_ranges.index.normalize()).max().rename("open_range_high")
    open_range_low = df_ranges["low"].groupby(df_ranges.index.normalize()).min().rename("open_range_low")

    df_sessions = df_sessions.copy()
    dates = df_sessions.index.normalize()
    df_sessions["open_range_high"] = dates.map(open_range_high)
    df_sessions["open_range_low"]  = dates.map(open_range_low)
    df_sessions["open_range_high"] = df_sessions["open_range_high"].groupby(dates).ffill()
    df_sessions["open_range_low"]  = df_sessions["open_range_low"].groupby(dates).ffill()
    return df_sessions


def get_rel_volume(wide_data, window):
    cum_volume = wide_data["volume"].cumsum(axis=1)
    avg_cum_volume = cum_volume.shift(1).rolling(window, min_periods=window).mean()
    wide_data["rel_volume"] = cum_volume / avg_cum_volume
    return wide_data