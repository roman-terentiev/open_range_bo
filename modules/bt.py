import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def get_df_day(date, wide_dict): 
    df = pd.DataFrame()
    df["open"] = wide_dict["open"].loc[date]
    df["close"] = wide_dict["close"].loc[date]
    df["atr_stop_dist"] = wide_dict["atr_stop_dist"].loc[date]  
    df["open_range_high"] = wide_dict["open_range_high"].loc[date]
    df["open_range_low"] = wide_dict["open_range_low"].loc[date]   
    df["rel_volume"] = wide_dict["rel_volume"].loc[date]  
    return df


def get_trades_day(
    df, 
    contract_mult, 
    comm_usd, 
    spread_usd, 
    slipp_rate, 
    toll_rate, 
    min_rel_volume,
    range_time_start,
    range_time_end
    ):  
    # Trade every 5 minutes
    minutes = df.index.map(lambda t: t.minute)
    signal_rows = df.loc[minutes % 5 == 4].iloc[:-1]
    trade_rows  = df.loc[minutes % 5 == 0].iloc[1:]
    if len(signal_rows) != len(trade_rows):
        trade_rows = trade_rows.iloc[:len(signal_rows)]

    round_trip_cost = comm_usd * 2 + spread_usd

    # Opening range condition
    range_time_start = pd.to_datetime(range_time_start).time()
    range_time_end = pd.to_datetime(range_time_end).time()
    is_bullish_range = df["close"].loc[range_time_end] > df["open"].loc[range_time_start] 
    is_bearish_range = df["close"].loc[range_time_end] < df["open"].loc[range_time_start] 

    # Large volume condition
    is_large_volume = df["rel_volume"].loc[range_time_end] > min_rel_volume

    trades = []
    trade = None
    done = False
    
    for i in range(len(trade_rows)):
        if not is_bullish_range and not is_bearish_range:
            break

        if done:
            break

        signal_row = signal_rows.iloc[i]
        trade_row = trade_rows.iloc[i]

        if signal_row.name <= range_time_end:
            continue

        if trade is None:
            # Entry long
            if signal_row["close"] > signal_row["open_range_high"] and is_bullish_range and is_large_volume:
                entry_price = trade_row["open"] * (1 + slipp_rate)
                trade = {
                    "trade_type": "long",
                    "start_time": trade_row.name,
                    "end_time": None,
                    "entry_price": entry_price,
                    "stop_price": entry_price - trade_row["atr_stop_dist"],
                }
  
            # Entry short
            elif signal_row["close"] < signal_row["open_range_low"] and is_bearish_range and is_large_volume:
                entry_price = trade_row["open"] * (1 - slipp_rate)
                trade = {
                    "trade_type": "short",
                    "start_time": trade_row.name,
                    "end_time": None,
                    "entry_price": entry_price,
                    "stop_price": entry_price + trade_row["atr_stop_dist"],
                }
        else:
            # Exit long
            if trade["trade_type"] == "long":
                below_atr_stop = signal_row["close"] < trade["stop_price"] * (1 + toll_rate)
                if below_atr_stop:
                    trade["end_time"] = trade_row.name
                    trade["exit_price"] = trade_row["open"] * (1 - slipp_rate)
                    trade["round_trip_cost"] = round_trip_cost
                    trade["pnl"] = (trade["exit_price"] - trade["entry_price"]) * contract_mult - round_trip_cost
                    trade["ret"] = trade["pnl"] / (trade["entry_price"] * contract_mult)
                    trade["exit_reason"] = "below_atr_stop"   
                    trades.append(trade)
                    trade = None
                    done = True

            # Exit short
            elif trade["trade_type"] == "short":
                above_atr_stop = signal_row["close"] > trade["stop_price"] * (1 - toll_rate)
                if above_atr_stop:
                    trade["end_time"] = trade_row.name
                    trade["exit_price"] = trade_row["open"] * (1 + slipp_rate)
                    trade["round_trip_cost"] = round_trip_cost
                    trade["pnl"] = (trade["entry_price"] - trade["exit_price"]) * contract_mult - round_trip_cost
                    trade["ret"] = trade["pnl"] / (trade["entry_price"] * contract_mult)
                    trade["exit_reason"] = "above_atr_stop"   
                    trades.append(trade)
                    trade = None
                    done = True
                    
    if trade is not None and trade["end_time"] is None:
        eod_row = df.iloc[-1]
        trade["end_time"] = eod_row.name
        
        # Exit long
        if trade["trade_type"] == "long":
            trade["exit_price"] = eod_row["close"] * (1 - slipp_rate)
            trade["round_trip_cost"] = round_trip_cost
            trade["pnl"] = (trade["exit_price"] - trade["entry_price"]) * contract_mult - round_trip_cost
            trade["ret"] = trade["pnl"] / (trade["entry_price"] * contract_mult)

        # Exit short
        elif trade["trade_type"] == "short":
            trade["exit_price"] = eod_row["close"] * (1 + slipp_rate)
            trade["round_trip_cost"] = round_trip_cost
            trade["pnl"] = (trade["entry_price"] - trade["exit_price"]) * contract_mult - round_trip_cost
            trade["ret"] = trade["pnl"] / (trade["entry_price"] * contract_mult)

        if trade.get("exit_reason") is None:
            trade["exit_reason"] = "eod"
            
        trades.append(trade)
        
    return trades


def get_trades(
    calendar, 
    wide_dict, 
    contract_mult, 
    comm_usd, 
    spread_usd, 
    slipp_rate, 
    toll_rate,
    min_rel_volume,
    range_time_start,
    range_time_end,
):
    trades = []
    for date in calendar:
        df = get_df_day(date, wide_dict)
        trades_day = get_trades_day(
            df, 
            contract_mult=contract_mult, 
            comm_usd=comm_usd, 
            spread_usd=spread_usd, 
            slipp_rate=slipp_rate, 
            toll_rate=toll_rate,
            min_rel_volume=min_rel_volume,
            range_time_start=range_time_start,
            range_time_end=range_time_end,
        )
        
        if len(trades_day) > 0:    
            for trade in trades_day:
                for column in ("start_time", "end_time"):
                    trade[column] = pd.Timestamp.combine(date, trade[column])
                trades.append(trade)

    trades = pd.DataFrame(trades)
    if trades.empty:
        return trades

    trades.index = pd.to_datetime(trades["start_time"].dt.date)
    trades.index.name = "date"
    trades["duration"] = (trades["end_time"] - trades["start_time"]).dt.total_seconds() / 60
    return trades


def get_sized_trades_equity(
    trades, 
    calendar, 
    init_balance, 
    risk_per_trade, 
    max_leverage, 
    contract_mult, 
    save_dir,
    ):
    trades = trades.copy()
    trades["sl_per_contract"] = np.nan
    trades["num_contracts"] = np.nan

    balance = init_balance
    equity = pd.Series(init_balance, index=calendar, name="equity", dtype=float)

    for date in calendar:
        if not trades.empty and date in trades.index:
            for i in np.flatnonzero(trades.index == date):
                trade = trades.iloc[i]
                
                sl_per_contract = abs(trade["entry_price"] - trade["stop_price"]) * contract_mult + trade["round_trip_cost"]
                num_contracts_by_risk = np.floor(balance * risk_per_trade / sl_per_contract)
                num_contracts_by_leverage = np.floor(balance * max_leverage / (trade["entry_price"] * contract_mult))
                num_contracts = int(min(num_contracts_by_risk, num_contracts_by_leverage))
                balance += num_contracts * trade["pnl"]

                trades.iloc[i, trades.columns.get_loc("sl_per_contract")] = sl_per_contract
                trades.iloc[i, trades.columns.get_loc("num_contracts")] = num_contracts
                
        equity.loc[date] = balance
    
    fig, ax = plt.subplots(figsize=(12, 6))
    equity.plot(ax=ax)
    ax.set_title("Equity Curve")
    ax.set_xlabel("Time")
    ax.set_ylabel("Equity")
    fig.savefig(save_dir / "equity.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    trades.to_csv(save_dir / "trades.csv")
    equity.to_csv(save_dir / "equity.csv")
    return equity