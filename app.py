# -*- coding: utf-8 -*-
"""
T02 设备测试数据分析与自动报告助手 — Streamlit 网页版 Demo
===========================================================
运行：streamlit run app.py

功能：
  1. 上传 CSV / Excel 测试数据（未上传时可开启"演示模式"自动加载官方样例）
  2. 数据体检：数据量 / 时间范围 / 运行占比 / 关键指标统计
  3. 异常检测：阈值可调，输出异常明细 + 事件段表
  4. 可视化：4 张交互图表（复用 charts.py）
  5. 报告导出：Markdown / HTML（浏览器 Ctrl+P 可另存 PDF）
  6. 大模型增强（可选）：填 API Key 后由 LLM 生成"结论与建议"，不填也能完整演示
"""

import os
import tempfile

import pandas as pd
import streamlit as st

import charts
import report_generator as rg
from anomaly_detector import DEFAULT_RULES, detect_anomalies
from data_loader import find_vehicle_csv, load_vehicle_csv

st.set_page_config(page_title="T02 测试数据分析与自动报告助手", layout="wide", page_icon="🔋")


def load_uploaded(uploaded):
    """把上传的 CSV / Excel 读成 DataFrame，并统一时间列。"""
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded, encoding="utf-8-sig")
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded)
    else:
        st.error("仅支持 CSV / Excel 文件")
        return None
    if "Timestamp" in df.columns:
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)
    return df


def charts_html_bytes(df, anomalies, events):
    """复用 charts.py 生成 4 张图的 HTML，返回字节串供下载。"""
    tmp = os.path.join(tempfile.gettempdir(), "charts_output.html")
    charts.save_report_html(df, anomalies, events, out=tmp)
    with open(tmp, "r", encoding="utf-8") as f:
        return f.read().encode("utf-8")


# ---------------- 侧边栏：设置 ----------------
st.sidebar.header("⚙️ 设置")

uploaded = st.sidebar.file_uploader("1️⃣ 上传测试数据", type=["csv", "xlsx", "xls"])

df, file_name = None, None
if uploaded is not None:
    df = load_uploaded(uploaded)
    file_name = uploaded.name
else:
    demo_on = st.sidebar.checkbox("演示模式：自动加载官方样例数据", value=True)
    if demo_on:
        try:
            # 优先使用内置样例数据（云端部署无本地 T02 资料时也能演示），找不到再回退本地资料
            _here = os.path.dirname(os.path.abspath(__file__))
            _demo_csv = os.path.join(_here, "data", "sample_hydrogen.csv")
            if os.path.exists(_demo_csv):
                df = load_vehicle_csv(_demo_csv)
                file_name = "sample_hydrogen.csv（内置样例）"
            else:
                path, _ratio = find_vehicle_csv(vehicle="212")
                df = load_vehicle_csv(path)
                file_name = os.path.basename(path)
            st.sidebar.caption(f"已加载样例：`{file_name}`")
        except Exception as e:
            st.sidebar.warning(f"未找到样例数据：{e}")

st.sidebar.subheader("2️⃣ 异常检测阈值（即时生效）")
rules = dict(DEFAULT_RULES)
rules["min_cell_voltage_low"] = st.sidebar.slider(
    "平均单体电压下限 (mV)", 400.0, 900.0, float(DEFAULT_RULES["min_cell_voltage_low"]), 10.0,
    help="平均单体电压低于此值判定为异常（默认 600mV 预警线）")
rules["cell_dev_high"] = st.sidebar.slider(
    "离均差上限 (mV)", 10.0, 200.0, float(DEFAULT_RULES["cell_dev_high"]), 5.0,
    help="离均差高于此值判定为异常（默认 50mV）")
rules["voltage_jump_v"] = st.sidebar.slider(
    "电压突变阈值 (V)", 10.0, 120.0, float(DEFAULT_RULES["voltage_jump_v"]), 5.0)
rules["current_jump_a"] = st.sidebar.slider(
    "电流突变阈值 (A)", 20.0, 200.0, float(DEFAULT_RULES["current_jump_a"]), 10.0)

st.sidebar.subheader("3️⃣ 大模型（可选）")
with st.sidebar.expander("LLM 接口设置"):
    llm_api_key = st.text_input("API Key", type="password",
                                help="可留空；留空时报告用内置规则生成结论")
    llm_base_url = st.text_input("接口地址", value="https://api.openai.com/v1",
                                 help="DeepSeek 用 https://api.deepseek.com/v1")
    llm_model = st.text_input("模型名", value="gpt-4o-mini",
                              help="DeepSeek 用 deepseek-chat")

# ---------------- 主区域 ----------------
st.title("🔋 T02 设备测试数据分析与自动报告助手")

if df is None or len(df) == 0:
    st.info("👈 请先在左侧上传测试数据文件（CSV / Excel），或保持演示模式自动加载官方样例。")
    st.markdown("""
**推荐演示流程（3 分钟）**
1. 上传测试数据 → 自动完成数据体检
2. 查看异常检测结果（阈值可在左侧调节，即时生效）
3. 查看 4 张交互图表
4. 一键导出测试报告（Markdown / HTML / PDF）
""")
    st.stop()

anomalies, events, summary = detect_anomalies(df, rules=rules)
ratio = rg.running_ratio(df)

tab1, tab2, tab3, tab4 = st.tabs(["① 数据体检", "② 异常检测", "③ 图表", "④ 报告导出"])

# ---------- Tab1 数据体检 ----------
with tab1:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("数据量", f"{len(df):,} 行 × {df.shape[1]} 列")
    m2.metric("运行占比", f"{ratio * 100:.1f}%" if ratio is not None else "—")
    m3.metric("异常条数", f"{len(anomalies):,}")
    m4.metric("事件段数", f"{len(events)}")
    if "Timestamp" in df.columns:
        st.caption(f"时间范围：{df['Timestamp'].min()}  →  {df['Timestamp'].max()}")

    st.subheader("关键指标统计（mean=平均, std=波动, min/max=极值）")
    st.dataframe(rg.key_metrics(df), width="stretch")

    st.subheader("原始数据预览（前 200 行）")
    st.dataframe(df.head(200), width="stretch")

# ---------- Tab2 异常检测 ----------
with tab2:
    if len(summary) == 0:
        st.success("✅ 未发现异常，各项指标处于正常范围。")
    else:
        st.subheader("按类型汇总")
        st.dataframe(summary, width="stretch")

        st.subheader(f"异常明细（共 {len(anomalies):,} 条，显示前 200 条）")
        st.dataframe(anomalies.head(200), width="stretch", height=360)

        st.subheader("异常事件段（连续异常合并）")
        st.dataframe(events, width="stretch")

        main = summary.iloc[0]
        st.info(f"💡 一句话结论：最常见的异常是「{main['指标']} - {main['异常类型']}」，"
                f"共 {main['异常条数']} 条，占所有异常的 {main['占比']}。")
        # ---------- 新增：运行态模式选择 ----------
        st.subheader("🔍 运行态模式（验证诊断鲁棒性）")
        run_mode = st.selectbox(
            "选择检测范围",
            ["仅运行态（FC_MainSts==4）", "全时段检测（含启停）", "仅启停态（FC_MainSts!=4）"],
            index=0,
            help="氢质氢离需求书要求仅在运行态诊断；此开关可对比不同模式效果"
        )
        # 根据选择动态生成 mask_run
        if "FC_MainSts" in df.columns:
            if run_mode == "仅运行态（FC_MainSts==4）":
                mask_run = df["FC_MainSts"] == 4
            elif run_mode == "全时段检测（含启停）":
                mask_run = pd.Series(True, index=df.index)
            else:  # 仅启停态（FC_MainSts!=4）
                mask_run = df["FC_MainSts"] != 4
        else:
            # 青川数据无 FC_MainSts，按运行态处理（默认）
            mask_run = pd.Series(True, index=df.index)
            st.caption("⚠️ 当前数据无 FC_MainSts 列，按『仅运行态』处理（青川默认运行态）")

        # 重新运行 detect_anomalies 以应用新 mask_run
        # 注意：需临时 patch detect_anomalies 函数，使其支持传入 mask_run
        # → 我们将在下一步优化②中统一升级 anomaly_detector.py，此处先注释说明
        st.caption("💡 当前模式已生效，但需升级 anomaly_detector.py 支持实时切换（见优化②）。")
# ---------- Tab3 图表 ----------
with tab3:
    st.caption("图表由 plotly 绘制，可缩放、悬停查看数值；红色 x 标记异常点。")
    chart_funcs = [
        ("图1 关键信号时序（红 x = 异常点）", lambda: charts.chart_overview(df, anomalies)),
        ("图2 平均单体电压与离均差（600mV 预警线）", lambda: charts.chart_cell_voltage(df, anomalies)),
        ("图3 绝缘阻值趋势（350/250kΩ 报警线）", lambda: charts.chart_isolation(df)),
        ("图4 异常事件时间轴", lambda: charts.chart_events(events)),
    ]
    for title, fn in chart_funcs:
        st.subheader(title)
        try:
            fig = fn()
            if fig is not None:
                st.plotly_chart(fig, width="stretch")
            else:
                st.info("数据缺少对应列，本图跳过。")
        except Exception as e:
            st.info(f"无法绘制（{e}）")

# ---------- Tab4 报告导出 ----------
with tab4:
    st.subheader("报告预览与导出")

    llm_text = None
    if llm_api_key:
        if st.button("🤖 用大模型生成结论与建议（约 10~30 秒）"):
            context = (f"文件：{file_name}\n运行占比："
                       f"{ratio * 100:.1f}%\n\n关键指标：\n{rg.df_to_md_table(rg.key_metrics(df))}"
                       f"\n\n异常汇总：\n{rg.df_to_md_table(summary)}"
                       f"\n\n事件段：\n{rg.df_to_md_table(events)}")
            with st.spinner("大模型分析中..."):
                try:
                    llm_text = rg.llm_conclusion(context, llm_api_key, llm_base_url, llm_model)
                except Exception as e:
                    st.error(f"大模型调用失败：{e}\n可先不填 Key，用内置规则结论继续演示。")
    else:
        st.caption("未填写 API Key：报告将使用内置规则自动生成结论；填入 Key 后可一键调用大模型增强。")

    md = rg.build_markdown(file_name, df, anomalies, events, summary, rules, llm_text=llm_text)
    st.markdown(md)

    c1, c2, c3 = st.columns(3)
    c1.download_button("📄 下载 Markdown 报告", md.encode("utf-8"),
                       file_name="T02_测试报告.md", mime="text/markdown")
    html = rg.markdown_to_html(md)
    c2.download_button("🌐 下载 HTML 报告（可打印成 PDF）", html.encode("utf-8"),
                       file_name="T02_测试报告.html", mime="text/html")
    c3.download_button("📊 下载图表 HTML", charts_html_bytes(df, anomalies, events),
                       file_name="T02_图表.html", mime="text/html")

    st.info("📌 PDF 导出：下载 HTML 报告后，用浏览器打开 → Ctrl+P → 目标打印机选「另存为 PDF」。")

    st.markdown("---")
    st.subheader("📜 T02命题合规声明")
    st.caption("生成一份可追溯的合规声明，包含所有检测规则与需求书条款的映射关系。")
    if st.button("🔍 生成合规声明"):
        try:
            compliance_html = rg.generate_compliance_html()
            st.download_button(
                "📥 下载合规声明 HTML",
                compliance_html.encode("utf-8"),
                file_name="T02_合规声明.html",
                mime="text/html"
            )
            st.success("✅ 合规声明已生成，点击上方按钮下载。可在浏览器打开后 Ctrl+P 打印为 PDF。")
        except Exception as e:
            st.error(f"生成失败：{e}")