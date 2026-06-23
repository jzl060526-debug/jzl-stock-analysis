# -*- coding: utf-8 -*-
"""专业交互图表模块：黑底K线 + 分时图 + B/S买卖点。"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


PLOTLY_2K_CONFIG = {
    "scrollZoom": False,
    "displaylogo": False,
    "modeBarButtonsToAdd": ["drawline", "eraseshape"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "kline_2k_export",
        "height": 1440,
        "width": 2560,
        "scale": 2,
    },
}


def get_chart_theme(mode: str = "dark") -> dict:
    """K线/分时图主题。白天模式使用白底黑字，日K上涨为空心红、下跌为深绿。"""
    if mode == "light":
        return {
            "template": "plotly_white",
            "paper": "#ffffff",
            "plot": "#ffffff",
            "text": "#111827",
            "muted": "#64748b",
            "grid": "rgba(15, 23, 42, 0.13)",
            "cross": "rgba(15, 23, 42, 0.38)",
            "up": "#ef4444",
            "up_fill": "rgba(255,255,255,0.0)",
            "down": "#15803d",
            "down_fill": "#15803d",
            "vol_up": "rgba(239, 68, 68, 0.50)",
            "vol_down": "rgba(21, 128, 61, 0.55)",
            "ma5": "#e58f00",
            "ma10": "#7c3aed",
            "ma20": "#0284c7",
            "ma60": "#2563eb",
            "minute": "#0ea5e9",
            "avg": "#f59e0b",
        }
    return {
        "template": "plotly_dark",
        "paper": "#05070b",
        "plot": "#05070b",
        "text": "#e5e7eb",
        "muted": "#94a3b8",
        "grid": "rgba(148, 163, 184, 0.14)",
        "cross": "rgba(226, 232, 240, 0.32)",
        "up": "#ff4d4f",
        "up_fill": "#ff4d4f",
        "down": "#16a34a",
        "down_fill": "#16a34a",
        "vol_up": "rgba(255, 77, 79, 0.62)",
        "vol_down": "rgba(22, 163, 74, 0.58)",
        "ma5": "#facc15",
        "ma10": "#a855f7",
        "ma20": "#0ea5e9",
        "ma60": "#2563eb",
        "minute": "#38bdf8",
        "avg": "#facc15",
    }


def _safe_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for col in ["date", "datetime"]:
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    for col in ["open", "close", "high", "low", "volume", "amount", "MA5", "MA10", "MA20", "MA60", "price"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _trade_df(trades: pd.DataFrame | None) -> pd.DataFrame:
    if trades is None or trades.empty:
        return pd.DataFrame()
    t = trades.copy()
    if "date" in t.columns:
        t["date"] = pd.to_datetime(t["date"], errors="coerce")
    if "price" in t.columns:
        t["price"] = pd.to_numeric(t["price"], errors="coerce")
    if "volume" in t.columns:
        t["volume"] = pd.to_numeric(t["volume"], errors="coerce").fillna(0).astype(int)
    t = t.dropna(subset=["date", "price"])
    return t


def make_empty_chart(title: str = "暂无数据", mode: str = "dark") -> go.Figure:
    th = get_chart_theme(mode)
    fig = go.Figure()
    fig.add_annotation(
        text="暂无可展示数据",
        x=0.5,
        y=0.5,
        showarrow=False,
        xref="paper",
        yref="paper",
        font=dict(size=22, color=th["muted"]),
    )
    fig.update_layout(
        title=title,
        template=th["template"],
        height=640,
        paper_bgcolor=th["paper"],
        plot_bgcolor=th["plot"],
        font=dict(color=th["text"], family="Microsoft YaHei, Arial"),
        margin=dict(l=18, r=54, t=54, b=24),
    )
    return fig


def _apply_common_layout(fig: go.Figure, title: str, th: dict, height: int, show_rangeslider: bool = False) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0.015, xanchor="left", font=dict(size=18, color=th["text"])),
        template=th["template"],
        height=height,
        paper_bgcolor=th["paper"],
        plot_bgcolor=th["plot"],
        font=dict(color=th["text"], family="Microsoft YaHei, Arial", size=12),
        margin=dict(l=18, r=58, t=56, b=24),
        hovermode="x unified",
        dragmode="pan",
        legend=dict(orientation="h", y=1.035, x=1, xanchor="right", bgcolor="rgba(0,0,0,0)"),
        xaxis_rangeslider_visible=show_rangeslider,
        uirevision=title,
        transition=dict(duration=180, easing="cubic-in-out"),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor=th["grid"],
        zeroline=False,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikecolor=th["cross"],
        spikethickness=1,
        rangeslider_visible=show_rangeslider,
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor=th["grid"],
        zeroline=False,
        side="right",
        showspikes=True,
        spikemode="across",
        spikecolor=th["cross"],
        spikethickness=1,
    )
    return fig


def make_kline_chart(
    df: pd.DataFrame,
    title: str = "日K图",
    trades: pd.DataFrame | None = None,
    mode: str = "dark",
    height: int = 900,
    show_rangeslider: bool = False,
) -> go.Figure:
    df = _safe_df(df)
    th = get_chart_theme(mode)
    if df.empty or not {"date", "open", "high", "low", "close"}.issubset(df.columns):
        return make_empty_chart(title, mode)
    df = df.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)
    if df.empty:
        return make_empty_chart(title, mode)

    # 使用交易日序号作为X轴，压缩周末和节假日空白。
    df["_x"] = list(range(len(df)))
    tick_step = max(1, len(df) // 8)
    tick_idx = list(range(0, len(df), tick_step))
    if len(df) - 1 not in tick_idx:
        tick_idx.append(len(df) - 1)
    tick_text = [pd.to_datetime(df.loc[i, "date"]).strftime("%Y-%m-%d") for i in tick_idx]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.74, 0.26],
    )
    fig.add_trace(
        go.Candlestick(
            x=df["_x"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="日K",
            increasing_line_color=th["up"],
            increasing_fillcolor=th.get("up_fill", th["up"]),
            decreasing_line_color=th["down"],
            decreasing_fillcolor=th.get("down_fill", th["down"]),
            whiskerwidth=0.45,
        ),
        row=1,
        col=1,
    )

    ma_config = {
        "MA5": ("MA5", th["ma5"], 2.2),
        "MA10": ("MA10", th["ma10"], 1.8),
        "MA20": ("MA20", th["ma20"], 1.8),
        "MA60": ("MA60", th["ma60"], 1.6),
    }
    for ma_col, (label, color, width) in ma_config.items():
        if ma_col in df.columns and df[ma_col].notna().any():
            fig.add_trace(
                go.Scatter(
                    x=df["_x"],
                    y=df[ma_col],
                    mode="lines",
                    name=label,
                    line=dict(width=width, color=color, shape="spline", smoothing=0.35),
                    hovertemplate=f"{label}: %{{y:.2f}}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    if "volume" in df.columns:
        colors = [th["vol_up"] if c >= o else th["vol_down"] for o, c in zip(df["open"], df["close"])]
        fig.add_trace(
            go.Bar(
                x=df["_x"],
                y=df["volume"],
                name="成交量",
                marker_color=colors,
                opacity=0.9,
                hovertemplate="成交量: %{y:.0f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    tdf = _trade_df(trades)
    if not tdf.empty:
        date_to_x = {pd.to_datetime(d).strftime("%Y-%m-%d"): int(x) for d, x in zip(df["date"], df["_x"])}
        tdf["_date_key"] = pd.to_datetime(tdf["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        tdf["_x"] = tdf["_date_key"].map(date_to_x)
        tdf = tdf.dropna(subset=["_x"]).copy()
        tdf["_x"] = tdf["_x"].astype(int)
        buy = tdf[tdf["side"].astype(str).str.contains("买", na=False)].copy()
        sell = tdf[tdf["side"].astype(str).str.contains("卖", na=False)].copy()
        for label, part, color, symbol, yshift in [
            ("买入点", buy, th["up"], "triangle-up", 12),
            ("卖出点", sell, th["down"], "triangle-down", -12),
        ]:
            if part.empty:
                continue
            texts = []
            hover = []
            for i, r in part.reset_index(drop=True).iterrows():
                prefix = "B" if "买" in str(r.get("side")) else "S"
                texts.append(f"{prefix}{i+1}<br>{r.get('price', ''):.2f}")
                hover.append(
                    f"日期：{pd.to_datetime(r.get('date')).strftime('%Y-%m-%d')}<br>"
                    f"方向：{r.get('side','')}｜{r.get('action_type','')}<br>"
                    f"价格：{float(r.get('price',0)):.2f}<br>"
                    f"数量：{int(r.get('volume',0))}股<br>"
                    f"理由：{r.get('reason','')}<br>"
                    f"本子：{r.get('note','')}"
                )
            fig.add_trace(
                go.Scatter(
                    x=part["_x"],
                    y=part["price"],
                    mode="markers+text",
                    name=label,
                    marker=dict(symbol=symbol, size=15, color=color, line=dict(color="#ffffff", width=1.2)),
                    text=texts,
                    textposition="top center" if yshift > 0 else "bottom center",
                    textfont=dict(size=11, color=color),
                    hovertext=hover,
                    hoverinfo="text",
                ),
                row=1,
                col=1,
            )

    fig = _apply_common_layout(fig, title, th, height=height, show_rangeslider=show_rangeslider)
    fig.update_xaxes(type="linear", tickmode="array", tickvals=tick_idx, ticktext=tick_text, range=[max(-3, len(df)-180), len(df)+3], row=1, col=1)
    fig.update_xaxes(type="linear", tickmode="array", tickvals=tick_idx, ticktext=tick_text, range=[max(-3, len(df)-180), len(df)+3], row=2, col=1)
    # 自动设置价格区间上下边界，避免K线被压缩到难以观察；仍允许工具栏局部缩放。
    try:
        y_low = float(df["low"].tail(180).min())
        y_high = float(df["high"].tail(180).max())
        pad = max((y_high - y_low) * 0.08, y_high * 0.01)
        fig.update_yaxes(title_text="价格", range=[y_low - pad, y_high + pad], row=1, col=1, fixedrange=False)
    except Exception:
        fig.update_yaxes(title_text="价格", row=1, col=1)
    fig.update_yaxes(title_text="成交量", row=2, col=1, fixedrange=False)
    return fig



def _make_intraday_axis(df: pd.DataFrame, x_col: str):
    """把A股分时的午休时间压缩掉。

    交易时间轴：
    - 09:30 -> 0
    - 11:30 -> 120
    - 13:00 -> 120
    - 15:00 -> 240

    这样 11:30 到 13:00 不会在图上留出一大段空白，
    视觉效果更接近同花顺/东方财富这类交易软件的分时图。
    """
    dt = pd.to_datetime(df[x_col], errors="coerce")
    minutes = dt.dt.hour * 60 + dt.dt.minute

    morning_start = 9 * 60 + 30
    morning_end = 11 * 60 + 30
    afternoon_start = 13 * 60
    afternoon_end = 15 * 60

    # 只保留正常交易时段；午休时间和异常时间不画线。
    valid = ((minutes >= morning_start) & (minutes <= morning_end)) | ((minutes >= afternoon_start) & (minutes <= afternoon_end))
    out = df.loc[valid].copy()
    dt = dt.loc[valid]
    minutes = minutes.loc[valid]

    session_x = []
    for m in minutes:
        if m <= morning_end:
            session_x.append(int(m - morning_start))
        else:
            # 13:00 与 11:30 压缩到同一位置120。
            session_x.append(int((morning_end - morning_start) + (m - afternoon_start)))

    out["_session_x"] = session_x
    out["_time_label"] = dt.dt.strftime("%Y-%m-%d %H:%M")
    return out


def _apply_intraday_xaxis(fig: go.Figure, has_volume: bool) -> go.Figure:
    """分时图专用X轴：压缩午休，显示真实交易时间刻度。"""
    tickvals = [0, 30, 60, 90, 120, 150, 180, 210, 240]
    ticktext = ["09:30", "10:00", "10:30", "11:00", "11:30/13:00", "13:30", "14:00", "14:30", "15:00"]
    fig.update_xaxes(
        type="linear",
        range=[-3, 243],
        tickmode="array",
        tickvals=tickvals,
        ticktext=ticktext,
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        row=1,
        col=1,
    )
    if has_volume:
        fig.update_xaxes(
            type="linear",
            range=[-3, 243],
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikethickness=1,
            row=2,
            col=1,
        )
    return fig


def make_minute_chart(
    df: pd.DataFrame,
    title: str = "分时图",
    mode: str = "dark",
    height: int = 560,
    show_avg: bool = True,
) -> go.Figure:
    df = _safe_df(df)
    th = get_chart_theme(mode)
    if df.empty:
        return make_empty_chart(title, mode)

    x_col = "datetime" if "datetime" in df.columns else "date" if "date" in df.columns else "time" if "time" in df.columns else None
    if x_col is None or "close" not in df.columns:
        return make_empty_chart(title, mode)

    df = df.dropna(subset=[x_col, "close"]).sort_values(x_col)
    if df.empty:
        return make_empty_chart(title, mode)

    # 尽量只显示最近一个交易日/最新日期，避免多日分钟线压缩。
    if pd.api.types.is_datetime64_any_dtype(df[x_col]) and len(df) > 0:
        last_day = df[x_col].dt.date.max()
        today_df = df[df[x_col].dt.date == last_day]
        if len(today_df) >= 20:
            df = today_df

    # A股分时专用：压缩 11:30-13:00 午休时间。
    # 11:30 与 13:00 在X轴上共用同一个位置，避免中间出现空白断层。
    use_intraday_axis = pd.api.types.is_datetime64_any_dtype(df[x_col])
    if use_intraday_axis:
        df = _make_intraday_axis(df, x_col)
        if df.empty:
            return make_empty_chart(title, mode)
        plot_x = df["_session_x"]
        hover_time = df["_time_label"]
    else:
        plot_x = df[x_col]
        hover_time = df[x_col].astype(str)

    has_volume = "volume" in df.columns and df["volume"].notna().any()
    if has_volume:
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.035, row_heights=[0.72, 0.28])
    else:
        fig = make_subplots(rows=1, cols=1)

    custom_price = pd.DataFrame({"time": hover_time, "close": df["close"]})
    fig.add_trace(
        go.Scatter(
            x=plot_x,
            y=df["close"],
            mode="lines",
            name="分时价",
            line=dict(width=2.4, color=th["minute"], shape="spline", smoothing=0.45),
            customdata=custom_price[["time", "close"]].to_numpy(),
            hovertemplate="%{customdata[0]}<br>价格: %{customdata[1]:.2f}<extra></extra>",
        ),
        row=1,
        col=1,
    )

    if show_avg:
        # 用分钟收盘价做简化均价线；不是严格成交额加权均价，但适合观察走势。
        avg = df["close"].expanding().mean()
        custom_avg = pd.DataFrame({"time": hover_time, "avg": avg})
        fig.add_trace(
            go.Scatter(
                x=plot_x,
                y=avg,
                mode="lines",
                name="均价线",
                line=dict(width=1.7, color=th["avg"], shape="spline", smoothing=0.55),
                customdata=custom_avg[["time", "avg"]].to_numpy(),
                hovertemplate="%{customdata[0]}<br>均价: %{customdata[1]:.2f}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    if has_volume:
        custom_vol = pd.DataFrame({"time": hover_time, "volume": df["volume"]})
        fig.add_trace(
            go.Bar(
                x=plot_x,
                y=df["volume"],
                name="分时量",
                marker_color="rgba(148, 163, 184, 0.45)",
                opacity=0.75,
                customdata=custom_vol[["time", "volume"]].to_numpy(),
                hovertemplate="%{customdata[0]}<br>分时量: %{customdata[1]:,.0f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    fig = _apply_common_layout(fig, title, th, height=height, show_rangeslider=False)
    try:
        y_low = float(df["close"].min())
        y_high = float(df["close"].max())
        pad = max((y_high - y_low) * 0.12, y_high * 0.003)
        fig.update_yaxes(title_text="价格", range=[y_low - pad, y_high + pad], row=1, col=1, fixedrange=False)
    except Exception:
        fig.update_yaxes(title_text="价格", row=1, col=1)
    if has_volume:
        fig.update_yaxes(title_text="分时量", row=2, col=1, fixedrange=False)

    if use_intraday_axis:
        fig = _apply_intraday_xaxis(fig, has_volume=has_volume)

    # 分时图更适合水平拖动/缩放，禁用日期range slider，减少视觉干扰。
    fig.update_layout(hovermode="x unified")
    return fig

