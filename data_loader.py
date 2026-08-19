# -*- coding: utf-8 -*-
"""
数据解析核心模块 data_loader.py
================================
用途：T02 各类原始数据的"翻译官"——把原始文件读成 pandas 表格，统一时间格式。
后续所有功能（画图、找异常、出报告）都会复用它。

常用函数：
    find_vehicle_csv(vehicle="212")   -> 自动挑一个"数据量足且真正在运行"的整车 CSV 路径
    load_vehicle_csv(path)            -> 读 CSV 并整理时间列，返回 DataFrame
"""

import glob
import os

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))


def find_t02_root():
    """找到 T02 资料文件夹（脚本放在比赛项目根目录）。"""
    for name in sorted(os.listdir(ROOT)):
        if name.startswith("T02"):
            return os.path.join(ROOT, name)
    return ROOT


def _running_ratio(path):
    """快速估算一个整车数据文件里"真正运行"（FC_MainSts==4）的时间占比。"""
    try:
        cols = pd.read_csv(path, encoding="utf-8-sig", nrows=20000, usecols=["FC_MainSts"])
        if len(cols) == 0:
            return 0.0
        return float((cols["FC_MainSts"] == 4).mean())
    except Exception:
        return 0.0


def find_vehicle_csv(vehicle="212", min_mb=2, max_mb=5, prefer_running=True):
    """挑一个大小合适、且最好有实际运行数据的整车 CSV 文件。

    参数:
        vehicle: 车辆编号，212 或 345
        min_mb / max_mb: 文件大小范围（MB），太小可能只有停车数据，太大加载慢
        prefer_running: 是否优先挑选"真正在运行"的数据片
    返回:
        (CSV 绝对路径, 运行时间占比 0~1)
    """
    t02 = find_t02_root()
    pattern = os.path.join(t02, "**", vehicle, "*.csv")
    files = glob.glob(pattern, recursive=True)
    if not files:
        raise FileNotFoundError(f"没有找到车辆 {vehicle} 的整车数据 CSV，请检查 T02 资料是否完整")

    # 过滤出大小合适的文件，按大小排序（大的靠后）
    candidates = [
        f for f in files
        if min_mb * 1024 * 1024 <= os.path.getsize(f) <= max_mb * 1024 * 1024
    ]
    if not candidates:
        candidates = sorted(files, key=os.path.getsize)[-3:]
    candidates.sort(key=os.path.getsize)

    if prefer_running:
        # 只检查最大的 10 个候选，选运行占比最高的（避免读到停车时段的全 0 数据）
        scored = sorted(
            ((_running_ratio(f), f) for f in candidates[-10:]),
            key=lambda x: x[0],
            reverse=True,
        )
        best_ratio, best = scored[0]
        return best, best_ratio
    return candidates[-1], None


def load_vehicle_csv(path):
    """读取整车数据 CSV，并把时间列整理成标准格式。"""
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)
    return df
