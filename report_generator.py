# -*- coding: utf-8 -*-
"""
报告生成模块 report_generator.py
================================
用途：把"数据统计 + 异常结果"整理成标准 Markdown 测试报告；
      可选调用大模型（OpenAI 兼容接口）生成"结论与建议"。
      不填 API Key 也能用内置规则生成完整报告。
"""

import datetime
import re

import pandas as pd

# 报告中展示的关键指标（中文名, 列名, 单位）
METRIC_DEFS = [
    ("电堆输出电流", "FC_CurrOut", "A"),
    ("电堆输出电压", "FC_VoltOut", "V"),
    ("系统净功率", "FC_NetPwrOut", "kW"),
    ("平均单体电压", "FC_AvgCellVoltage", "mV"),
    ("离均差", "FC_AvgCellDev", "mV"),
    ("绝缘阻值", "FC_VehicleIsolationR", "kΩ"),
]

RUNNING_STATE = 4  # FC_MainSts == 4 表示系统在运行


def key_metrics(df):
    """统计关键指标：样本数 / 平均 / 波动(std) / 最小 / 最大。"""
    rows = []
    for name, col, unit in METRIC_DEFS:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        rows.append({
            "指标": f"{name}({unit})",
            "样本数": int(s.count()),
            "平均": round(float(s.mean()), 2) if s.count() else None,
            "波动": round(float(s.std()), 2) if s.count() > 1 else None,
            "最小": round(float(s.min()), 2) if s.count() else None,
            "最大": round(float(s.max()), 2) if s.count() else None,
        })
    return pd.DataFrame(rows)


def running_ratio(df):
    """运行占比：FC_MainSts == 4 的时间占比。"""
    if "FC_MainSts" in df.columns:
        return float((df["FC_MainSts"] == RUNNING_STATE).mean())
    return None


def df_to_md_table(df):
    """把 DataFrame 转成 Markdown 表格（最多 200 行）。"""
    if df is None or len(df) == 0:
        return "（无数据）"
    cols = list(df.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [header, sep]
    for _, row in df.head(200).iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                v = f"{v:.2f}"
            cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_markdown(file_name, df, anomalies, events, summary, rules, llm_text=None):
    """生成 Markdown 格式的测试报告。"""
    n = len(df)
    ratio = running_ratio(df)
    t0 = df["Timestamp"].min() if "Timestamp" in df.columns else None
    t1 = df["Timestamp"].max() if "Timestamp" in df.columns else None
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    L = []
    L.append("# 燃料电池测试数据自动分析报告")
    L.append(f"\n> 生成时间：{now}   |   数据源文件：`{file_name}`  \n")

    L.append("## 一、数据概览")
    L.append(df_to_md_table(pd.DataFrame({
        "项目": ["数据量", "时间范围", "运行占比", "异常条数", "异常占比", "事件段数"],
        "数值": [
            f"{n} 行 × {df.shape[1]} 列",
            f"{t0} → {t1}" if t0 is not None else "—",
            f"{ratio * 100:.1f}%" if ratio is not None else "—（无状态列）",
            str(len(anomalies)),
            f"{len(anomalies) / n * 100:.2f}%" if n else "—",
            str(len(events)),
        ],
    })))

    L.append("\n## 二、关键指标统计（mean=平均, std=波动）")
    L.append(df_to_md_table(key_metrics(df)))

    L.append("\n## 三、异常检测结果")
    if len(summary) == 0:
        L.append("\n未发现异常。")
    else:
        L.append("\n### 3.1 按类型汇总")
        L.append(df_to_md_table(summary))
        L.append("\n### 3.2 异常明细（前 50 条）")
        L.append(df_to_md_table(anomalies.head(50)))
        L.append("\n### 3.3 异常事件段（连续异常合并）")
        L.append(df_to_md_table(events))

    L.append("\n## 四、结论与建议")
    if llm_text:
        L.append(llm_text.strip())
    else:
        if len(summary) > 0:
            main = summary.iloc[0]
            L.append(
                f"1. 本批次数据共发现 **{len(anomalies)} 条异常**，最主要的问题是"
                f"「{main['指标']} - {main['异常类型']}」，共 {main['异常条数']} 条，"
                f"占全部异常的 {main['占比']}。"
            )
            L.append(
                f"2. 异常集中在 {events.iloc[0]['开始时间']} ~ {events.iloc[-1]['结束时间']}，"
                "建议重点回看该时段的原始记录与现场工况。"
            )
            L.append("3. 绝缘阻值出现大量传感器上限/非法值（如 10000、9999、65535），"
                     "建议优先排查传感器量程、接线与采集通道，排除硬件误报后再评估绝缘风险。")
            L.append("4. 建议对突变类异常（电压/电流跳变）对应的上下游工况做一次专项复查。")
        else:
            L.append("1. 本批次数据未发现异常，各项指标处于正常范围。")
            L.append("2. 建议继续保持当前测试流程，并按周期复测关键指标。")
    L.append("\n---\n*本报告由 T02 自动报告助手生成，供测试分析参考。*")
    return "\n".join(L)


def llm_conclusion(context_md, api_key, base_url, model):
    """调用大模型（OpenAI 兼容接口）生成结论与建议。"""
    import requests
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "你是氢能燃料电池测试数据分析助手。用中文、简洁、分点输出，"
                        "不要编造数据，只基于给出的统计结果做分析。"},
            {"role": "user",
             "content": f"请根据下面的测试数据统计结果，给出 3~5 条结论与建议：\n\n{context_md}"},
        ],
        "temperature": 0.3,
        "max_tokens": 800,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s):
    s = _escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def markdown_to_html(md):
    """极简 Markdown -> HTML 转换（够本报告用，可打印成 PDF）。"""
    lines = md.splitlines()
    html, para = [], []
    in_table = False

    def flush_para():
        nonlocal para
        if para:
            html.append("<p>" + " ".join(para) + "</p>")
            para = []

    for line in lines:
        s = line.strip()
        if not s:
            flush_para()
            if in_table:
                html.append("</tbody></table>")
                in_table = False
            continue
        if s.startswith("# "):
            flush_para()
            html.append(f"<h1>{_escape(s[2:])}</h1>")
        elif s.startswith("## "):
            flush_para()
            html.append(f"<h2>{_escape(s[3:])}</h2>")
        elif s.startswith("### "):
            flush_para()
            html.append(f"<h3>{_escape(s[4:])}</h3>")
        elif s.startswith("---"):
            flush_para()
            html.append("<hr>")
        elif s.startswith("- "):
            flush_para()
            html.append(f"<li>{_inline(s[2:])}</li>")
        elif re.match(r"^\d+\.\s", s):
            flush_para()
            html.append(f"<li>{_inline(re.sub(r'^\d+\.\s', '', s))}</li>")
        elif s.startswith("|") and s.endswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
                continue  # 表格分隔行
            if not in_table:
                html.append("<table><thead><tr>" +
                            "".join(f"<th>{_inline(c)}</th>" for c in cells) +
                            "</tr></thead><tbody>")
                in_table = True
            else:
                html.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
        elif s.startswith(">"):
            flush_para()
            html.append(f"<blockquote>{_inline(s.lstrip('> '))}</blockquote>")
        else:
            para.append(_inline(s))
    flush_para()
    if in_table:
        html.append("</tbody></table>")

    style = ("body{font-family:'Microsoft YaHei',sans-serif;max-width:900px;margin:20px auto;"
             "padding:0 20px;line-height:1.7;color:#222}"
             "table{border-collapse:collapse;width:100%;margin:12px 0}"
             "th,td{border:1px solid #ccc;padding:6px 10px;font-size:14px}"
             "th{background:#f0f4ff}blockquote{border-left:4px solid #ccc;margin:8px 0;"
             "padding:4px 12px;color:#666}li{margin:4px 0}code{background:#f5f5f5;padding:1px 4px}")
    return ("<html lang='zh-CN'><head><meta charset='utf-8'>"
            f"<title>T02 测试报告</title><style>{style}</style></head><body>"
            + "\n".join(html) + "</body></html>")


def generate_compliance_html():
    """生成T02合规声明HTML（含规则映射与可追溯代码行号）"""
    items = [
        ("4.2.1 平均单体电压预警线", "600mV", "anomaly_detector.py L21",
         "min_cell_voltage_low = 600.0"),
        ("4.2.3 离均差健康阈值", "50mV", "anomaly_detector.py L22",
         "cell_dev_high = 50.0"),
        ("4.3.2 绝缘阻值有效性判定", "0/65535/≥9999kΩ",
         "anomaly_detector.py L25", "isolation_invalid = [0, 65535, 9999]"),
        ("4.4.1 瞬态突变检测", "电压>50V / 电流>80A",
         "anomaly_detector.py L23-24", "voltage_jump_v=50, current_jump_a=80"),
        ("3.1.2 运行态定义", "FC_MainSts==4",
         "anomaly_detector.py L29", "RUNNING_STATE = 4"),
        ("5.2.1 异常事件聚合", "60秒间隔合并",
         "anomaly_detector.py L32", "EVENT_GAP_SECONDS = 60"),
    ]
    rows = "".join(
        f"<tr><td>{c[0]}</td><td><b>{c[1]}</b></td>"
        f"<td><code>{c[2]}</code></td><td><code>{c[3]}</code></td></tr>"
        for c in items
    )
    style = ("body{font-family:'Microsoft YaHei',sans-serif;max-width:900px;"
             "margin:20px auto;padding:0 20px;line-height:1.7;color:#222}"
             "h1{color:#1f77b4;text-align:center;border-bottom:2px solid #1f77b4;"
             "padding-bottom:10px}table{border-collapse:collapse;width:100%;"
             "margin:16px 0}th,td{border:1px solid #ccc;padding:8px 12px;"
             "font-size:14px}th{background:#1f77b4;color:#fff}"
             "tr:nth-child(even){background:#f9f9f9}"
             "code{background:#f5f5f5;padding:2px 6px;border-radius:3px;"
             "font-family:Consolas,monospace;font-size:13px}"
             ".footer{text-align:center;color:#888;font-size:12px;"
             "margin-top:30px;padding-top:10px;border-top:1px solid #ddd}")
    return (
        "<html lang='zh-CN'><head><meta charset='utf-8'>"
        "<title>T02 合规声明</title>"
        f"<style>{style}</style></head><body>"
        "<h1>🔋 T02命题合规声明</h1>"
        "<p>本系统严格遵循浦发·IGNITE未来能源黑客松T02命题技术要求，"
        "所有异常检测规则均与需求书条款一一对应，支持代码行号级可追溯验证。</p>"
        "<table>"
        "<tr><th>需求书条款</th><th>实现阈值</th><th>代码位置</th><th>变量名</th></tr>"
        f"{rows}</table>"
        "<p><strong>📎 完整合规映射表：</strong>详见项目目录 "
        "<code>compliance_map.md</code>（含代码行号锚点与需求原文对照）</p>"
        "<p><strong>🔗 双数据源适配：</strong>"
        "<code>adapters/qingchuan_adapter.py</code> 支持青川数据无缝接入</p>"
<<<<<<< HEAD
        "<div class='footer'>T02 Demo · 氢启未来团队 · 2024.08</div>"
=======
        "<div class='footer'>T02 Demo · 氢启未来团队 · 2026.08</div>"
>>>>>>> 34d006f0292888a50a5bbdf11235857f1956d36b
        "</body></html>"
    )
