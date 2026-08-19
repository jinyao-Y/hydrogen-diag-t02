# -*- coding: utf-8 -*-
"""
图表模块 charts.py
==================
用途：把"翻译官"的数据和"质检员"的异常画成 plotly 图表，汇总输出到一个 HTML 文件，
      浏览器直接打开即可查看（无需启动任何服务）。

函数：
    save_report_html(df, anomalies, events, out="charts_output.html")
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

RUNNING_STATE = 4          # 运行态（需求书：FC_MainSts==4）
ISOLATION_INVALID = [0.0, 65535.0, 9999.0]  # 绝缘阻值非法值
ISOLATION_WARN_KOHM = 350.0   # 绝缘阻值预警线 kΩ
ISOLATION_ALARM_KOHM = 250.0  # 绝缘阻值报警线 kΩ
MIN_CELL_VOLTAGE_MV = 600.0   # 平均单体电压预警线 mV

# 异常指标 -> 在图上显示的列
METRIC_COL = {
    "电堆输出电流": "FC_CurrOut",
    "电堆输出电压": "FC_VoltOut",
    "平均单体电压": "FC_AvgCellVoltage",
    "离均差": "FC_AvgCellDev",
}


def _running(df):
    """只取运行态的数据（停机时电压/电流为 0，画图没有意义）。"""
    if "FC_MainSts" in df.columns:
        return df[df["FC_MainSts"] == RUNNING_STATE]
    return df


def chart_overview(df, anomalies):
    """图1：关键信号时序 + 异常红点（双轴：电流 / 平均单体电压）。"""
    d = _running(df)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=d["Timestamp"], y=d["FC_CurrOut"], name="电堆电流(A)",
                   line=dict(width=1, color="#1f77b4")),
        secondary_y=False,
    )
    if "FC_AvgCellVoltage" in d.columns:
        fig.add_trace(
            go.Scatter(x=d["Timestamp"], y=d["FC_AvgCellVoltage"], name="平均单体电压(mV)",
                       line=dict(width=1, color="#2ca02c")),
            secondary_y=True,
        )
    # 异常红点（电流/电压类）
    for metric in ("电堆输出电流", "电堆输出电压", "平均单体电压"):
        sub = anomalies[anomalies["指标"] == metric]
        if len(sub):
            sec = metric != "电堆输出电流"
            fig.add_trace(
                go.Scatter(x=sub["时间"], y=sub["实际值"], mode="markers",
                           name=f"异常-{metric}",
                           marker=dict(size=7, color="red", symbol="x")),
                secondary_y=sec,
            )
    fig.update_layout(title="图1 关键信号时序（红色 x = 异常点）", height=420,
                      hovermode="x unified", margin=dict(l=40, r=40, t=50, b=30))
    fig.update_yaxes(title_text="电堆电流 (A)", secondary_y=False)
    fig.update_yaxes(title_text="平均单体电压 (mV)", secondary_y=True)
    return fig


def chart_cell_voltage(df, anomalies):
    """图2：平均单体电压曲线 + 离均差 + 600mV 预警线。"""
    d = _running(df)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=d["Timestamp"], y=d["FC_AvgCellVoltage"], name="平均单体电压(mV)",
                   line=dict(width=1, color="#2ca02c")),
        secondary_y=False,
    )
    if "FC_AvgCellDev" in d.columns:
        fig.add_trace(
            go.Scatter(x=d["Timestamp"], y=d["FC_AvgCellDev"], name="离均差(mV)",
                       mode="markers", marker=dict(size=2, color="#ff7f0e"), opacity=0.6),
            secondary_y=True,
        )
    fig.add_hline(y=MIN_CELL_VOLTAGE_MV, line_dash="dash", line_color="red",
                  annotation_text=f"预警线 {MIN_CELL_VOLTAGE_MV}mV", secondary_y=False)
    fig.update_layout(title="图2 平均单体电压与离均差", height=420,
                      hovermode="x unified", margin=dict(l=40, r=40, t=50, b=30))
    fig.update_yaxes(title_text="平均单体电压 (mV)", secondary_y=False)
    fig.update_yaxes(title_text="离均差 (mV)", secondary_y=True)
    return fig


def chart_isolation(df):
    """图3：绝缘阻值散点 + 350/250kΩ 报警线（剔除非法值后）。"""
    if "FC_VehicleIsolationR" not in df.columns:
        return None
    iso = df["FC_VehicleIsolationR"]
    valid = df[~iso.isin(ISOLATION_INVALID) & (iso < 9999) & (iso > 0)]
    fig = go.Figure()
    if len(valid):
        fig.add_trace(
            go.Scatter(x=valid["Timestamp"], y=valid["FC_VehicleIsolationR"],
                       mode="markers", name="绝缘阻值(kΩ)",
                       marker=dict(size=3, color="#9467bd", opacity=0.6)),
        )
    fig.add_hline(y=ISOLATION_WARN_KOHM, line_dash="dash", line_color="orange",
                  annotation_text="预警线 350kΩ")
    fig.add_hline(y=ISOLATION_ALARM_KOHM, line_dash="dash", line_color="red",
                  annotation_text="报警线 250kΩ")
    fig.update_layout(title="图3 绝缘阻值趋势（低于报警线有漏电风险）", height=380,
                      hovermode="x unified", margin=dict(l=40, r=40, t=50, b=30))
    fig.update_yaxes(title_text="绝缘阻值 (kΩ)")
    return fig


def chart_events(events):
    """图4：异常事件时间轴（Plotly Express Gantt图，悬停查看详情）"""
    if events is None or len(events) == 0:
        return None
    # 重命名列名供 px.timeline 使用
    cols_map = {"开始时间": "start", "结束时间": "finish",
                "主要类型": "task", "持续秒数": "duration_s", "异常条数": "count"}
    df_tl = events[list(cols_map.keys())].rename(columns=cols_map)
    # 生成唯一标签
    df_tl["label"] = df_tl.apply(lambda r: f"#{r.name+1} {r['task']}", axis=1)
    df_tl["hover"] = df_tl.apply(
        lambda r: f"{r['label']}<br>起止: {str(r['start'])[:19]} ~ {str(r['finish'])[:19]}<br>"
                  f"持续: {r['duration_s']}s | 异常{r['count']}条", axis=1)
    fig = px.timeline(
        df_tl, x_start="start", x_end="finish", y="task", color="task",
        title="图4 异常事件时间轴（点击图例可筛选 · 悬停查看详情）",
        hover_data={"hover": True}, opacity=0.85,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=360, margin=dict(l=40, r=40, t=50, b=30),
                      hoverlabel=dict(bgcolor="#fff", font_size=13))
    fig.update_xaxes(title_text="时间", tickformat="%H:%M:%S")
    return fig


def save_report_html(df, anomalies, events, out="charts_output.html"):
    """生成 4 张图并保存为一个自包含的 HTML 文件。"""
    figs = [
        ("图1 关键信号时序（红 x = 异常点）", chart_overview(df, anomalies)),
        ("图2 平均单体电压与离均差（含 600mV 预警线）", chart_cell_voltage(df, anomalies)),
        ("图3 绝缘阻值趋势（含 350/250kΩ 报警线）", chart_isolation(df)),
        ("图4 异常事件时间轴", chart_events(events)),
    ]

    parts = [
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
        "<title>T02 数据可视化</title></head><body style='font-family:Microsoft YaHei, sans-serif;'>",
        "<h2 style='text-align:center'>T02 测试数据分析可视化</h2>",
    ]
    first = True
    for title, fig in figs:
        if fig is None:
            continue
        parts.append(f"<h3>{title}</h3>")
        parts.append(fig.to_html(full_html=False, include_plotlyjs="cdn" if first else False))
        first = False
    parts.append("</body></html>")

    html = "\n".join(parts)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out
