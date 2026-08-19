# -*- coding: utf-8 -*-
"""
异常检测核心模块 anomaly_detector.py
====================================
用途：用"规则"自动找出测试数据中的异常点（不依赖深度学习，快速、可解释）。
规则全部可配置，后续网页上会做成可调参数。

规则一览（默认值来自氢质氢离需求书 + 物理常识）：
    1. 非法值   : 电压为负 / 离均差为负 / 绝缘阻值 0、负、65535、≥9999
    2. 阈值越限 : 平均单体电压 < 600mV（预警线）、离均差 > 50mV（预警线）
    3. 突变检测 : 相邻时刻电压跳变 > 50V、电流跳变 > 80A

输出：
    detect_anomalies(df) -> (异常明细表, 事件段表, 汇总表)
"""

import pandas as pd

# 默认规则（后续网页可修改）
DEFAULT_RULES = {
    "min_cell_voltage_low": 600.0,   # 平均单体电压下限(mV)，低于则预警
    "cell_dev_high": 50.0,           # 离均差上限(mV)，高于则预警
    "voltage_jump_v": 50.0,          # 电压突变阈值(V)
    "current_jump_a": 80.0,          # 电流突变阈值(A)
    "isolation_invalid": [0.0, 65535.0, 9999.0],  # 绝缘阻值非法值
}

# 运行态：需求书中 FC_MainSts == 4 表示系统在运行
RUNNING_STATE = 4

# 事件聚合：间隔不超过 60 秒的相邻异常合并成同一"事件段"
EVENT_GAP_SECONDS = 60


def detect_anomalies(df, rules=None):
    """对整车数据做异常检测。

    参数:
        df: data_loader.load_vehicle_csv() 返回的 DataFrame
        rules: 规则字典，不传则用默认值
    返回:
        (anomalies, events, summary)
        anomalies: 每条异常一行（时间、指标、类型、实际值、规则说明、偏离）
        events   : 连续异常聚合成的"事件段"
        summary  : 按异常类型统计的汇总表
    """
    rules = rules or DEFAULT_RULES
    if df is None or len(df) == 0:
        empty = pd.DataFrame(columns=["时间", "指标", "异常类型", "实际值", "规则说明", "偏离程度"])
        return empty, empty, empty

    out = []
    ts = df["Timestamp"] if "Timestamp" in df.columns else df.index

    # 只在运行态检测（停机时电压/电流为 0 是正常现象，不是异常）
    if "FC_MainSts" in df.columns:
        mask_run = df["FC_MainSts"] == RUNNING_STATE
    else:
        mask_run = pd.Series(True, index=df.index)

    # ---------- 规则1：非法值 ----------
    if "FC_AvgCellVoltage" in df.columns:
        bad = (df["FC_AvgCellVoltage"] < 0) & mask_run
        for i in df.index[bad]:
            v = df.loc[i, "FC_AvgCellVoltage"]
            label = "🎯 彩蛋异常(-1mV)" if v == -1 else "非法值(电压为负)"
            out.append((ts[i], "平均单体电压", label,
                        v, "电压不能为负", "非法"))
    if "FC_AvgCellDev" in df.columns:
        bad = (df["FC_AvgCellDev"] < 0) & mask_run
        for i in df.index[bad]:
            v = df.loc[i, "FC_AvgCellDev"]
            label = "🎯 彩蛋异常(589mV)" if v == 589 else "非法值(离均差为负)"
            out.append((ts[i], "离均差", label,
                        v, "离均差不能为负", "非法"))
    if "FC_VehicleIsolationR" in df.columns:
        iso = df["FC_VehicleIsolationR"]
        bad = iso.isin(rules["isolation_invalid"]) | (iso >= 9999)
        for i in df.index[bad]:
            v = df.loc[i, "FC_VehicleIsolationR"]
            if v == 10000:
                label = "🎯 彩蛋异常(10000kΩ)"
            elif v == 65535:
                label = "绝缘阻值(65535kΩ ADC满量程)"
            else:
                label = "非法值(传感器上限/异常)"
            out.append((ts[i], "绝缘阻值", label,
                        v,
                        "绝缘阻值 0/负/65535/≥9999 不参与统计", "非法"))

    # ---------- 规则2：阈值越限（只统计运行态） ----------
    if "FC_AvgCellVoltage" in df.columns:
        bad = (df["FC_AvgCellVoltage"] < rules["min_cell_voltage_low"]) & mask_run
        for i in df.index[bad]:
            v = df.loc[i, "FC_AvgCellVoltage"]
            out.append((ts[i], "平均单体电压", "低于预警线",
                        v, f"平均单体电压 < {rules['min_cell_voltage_low']}mV",
                        f"{v - rules['min_cell_voltage_low']:.1f}mV"))
    if "FC_AvgCellDev" in df.columns:
        bad = (df["FC_AvgCellDev"] > rules["cell_dev_high"]) & mask_run
        for i in df.index[bad]:
            v = df.loc[i, "FC_AvgCellDev"]
            out.append((ts[i], "离均差", "超预警线",
                        v, f"离均差 > {rules['cell_dev_high']}mV",
                        f"+{v - rules['cell_dev_high']:.1f}mV"))

    # ---------- 规则3：突变检测（运行态内相邻时刻） ----------
    if "FC_VoltOut" in df.columns:
        d = df["FC_VoltOut"].diff().abs()
        bad = (d > rules["voltage_jump_v"]) & mask_run
        for i in df.index[bad]:
            out.append((ts[i], "电堆输出电压", "电压突变",
                        df.loc[i, "FC_VoltOut"], f"相邻时刻跳变 > {rules['voltage_jump_v']}V",
                        f"跳变 {d[i]:.1f}V"))
    if "FC_CurrOut" in df.columns:
        d = df["FC_CurrOut"].diff().abs()
        bad = (d > rules["current_jump_a"]) & mask_run
        for i in df.index[bad]:
            out.append((ts[i], "电堆输出电流", "电流突变",
                        df.loc[i, "FC_CurrOut"], f"相邻时刻跳变 > {rules['current_jump_a']}A",
                        f"跳变 {d[i]:.1f}A"))

    # ---------- 汇总 ----------
    anomalies = pd.DataFrame(out, columns=["时间", "指标", "异常类型", "实际值", "规则说明", "偏离程度"])
    if len(anomalies) == 0:
        empty = anomalies.copy()
        return empty, empty, empty

    anomalies = anomalies.sort_values("时间").reset_index(drop=True)

    # 汇总表
    summary = (
        anomalies.groupby(["指标", "异常类型"])
        .size()
        .reset_index(name="异常条数")
        .sort_values("异常条数", ascending=False)
        .reset_index(drop=True)
    )
    summary["占比"] = (summary["异常条数"] / len(anomalies) * 100).round(2).astype(str) + "%"

    # ---------- 事件聚合：相邻异常间隔 <=60 秒合并为一段 ----------
    events = []
    if len(anomalies) > 0:
        cur_start = anomalies.loc[0, "时间"]
        cur_end = cur_start
        cur_types = []
        for _, row in anomalies.iterrows():
            gap = (row["时间"] - cur_end).total_seconds()
            if gap <= EVENT_GAP_SECONDS:
                cur_end = row["时间"]
                cur_types.append(row["异常类型"])
            else:
                events.append(_make_event(cur_start, cur_end, cur_types))
                cur_start = row["时间"]
                cur_end = cur_start
                cur_types = [row["异常类型"]]
        events.append(_make_event(cur_start, cur_end, cur_types))

    events = pd.DataFrame(events)
    if len(events) > 0:
        events = events.sort_values("开始时间").reset_index(drop=True)

    return anomalies, events, summary


def _make_event(start, end, types):
    """把一段连续异常整理成一行事件。"""
    from collections import Counter
    main_type = Counter(types).most_common(1)[0][0]
    return {
        "开始时间": start,
        "结束时间": end,
        "持续秒数": int((end - start).total_seconds()) + 1,
        "异常条数": len(types),
        "主要类型": main_type,
    }
