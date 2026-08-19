# T02 设备测试数据分析与自动报告助手（Streamlit 网页 Demo）

> 🚀 **快速启动演示（推荐答辩使用）**：双击本目录下的 `run_demo.bat`，即可全自动完成数据加载 → 异常检测 → 图表生成 → Markdown 报告输出全流程（无需打开浏览器、无需手动上传、无需调参）。

浦发·IGNITE 未来能源黑客松 T02 命题的线上评审演示 Demo。
上传氢能电堆/整车测试数据（CSV / Excel），自动完成：数据体检 → 异常检测 → 可视化 → 一键生成测试报告。

## 一、项目文件

| 文件 | 作用 |
| --- | --- |
| `app.py` | Streamlit 主程序（网页入口） |
| `data_loader.py` | 数据解析：读 CSV / Excel，统一时间列 |
| `anomaly_detector.py` | 异常检测：规则引擎（非法值/越限/突变），阈值可调 |
| `charts.py` | 4 张交互图表（plotly） |
| `report_generator.py` | 生成 Markdown 报告 + 可选大模型结论 + Markdown 转 HTML |
| `demo_task2.py` / `demo_task3.py` / `demo_task4.py` | 命令行版分步演示（开发过程留档） |
| `requirements.txt` | Python 依赖清单 |

## 二、安装与运行

```powershell
cd C:\Users\yjy23\Desktop\AI+能源黑客松比赛
pip install -r requirements.txt
streamlit run app.py
```

- 浏览器会自动打开 `http://localhost:8501`。
- 端口被占用时可换端口：`streamlit run app.py --server.port 8502`
- 已确认环境：Python 3.13 + streamlit 1.61 + pandas 3.0 + plotly 6.9 可直接运行。

## 三、使用流程（3 分钟演示）

1. **数据上传**：左侧「上传测试数据」选择 CSV/Excel；不上传时默认开启「演示模式」，自动加载官方整车样例数据（车辆 212）。
2. **数据体检**：Tab「① 数据体检」查看数据量、运行占比、关键指标统计、原始数据预览。
3. **异常检测**：Tab「② 异常检测」查看异常汇总、异常明细、事件段；左侧滑块可实时调整阈值（如单体电压下限 600mV）。
4. **图表**：Tab「③ 图表」查看 4 张交互图（信号时序、单体电压/离均差、绝缘阻值、事件时间轴）。
5. **报告导出**：Tab「④ 报告导出」预览报告，下载 Markdown / HTML / 图表 HTML；HTML 在浏览器打开后 `Ctrl+P → 另存为 PDF`。

## 四、大模型 API Key 配置（可选）

不填 Key 也能完整演示（内置规则自动生成"结论与建议"）。需要大模型增强时，在左侧「LLM 接口设置」填写：

| 字段 | 示例 |
| --- | --- |
| API Key | `sk-xxxxxxxx` |
| 接口地址 | OpenAI：`https://api.openai.com/v1`；DeepSeek：`https://api.deepseek.com/v1`；智谱：`https://open.bigmodel.cn/api/paas/v4` |
| 模型名 | OpenAI：`gpt-4o-mini`；DeepSeek：`deepseek-chat`；智谱：`glm-4-flash` |

填好后到「④ 报告导出」点击「用大模型生成结论与建议」，报告第四节会自动替换为 LLM 生成的结论。

> 注意：代码里没有写死任何 Key，评审演示前请勿在共享屏幕时暴露 Key；网络不可用时请关闭该功能。

## 五、评审演示建议

1. 开场 30 秒：一句话说清产品——"上传测试数据，自动体检、找异常、出报告"。
2. 演示上传官方 CSV → 数据体检 → 异常检测（重点讲 315 条异常、绝缘非法值占 99%、10 个事件段）。
3. 拖动阈值滑块展示"规则可解释、可调参"。
4. 展示 4 张图 + 导出 Markdown 报告，说明"可对接大模型生成结论"。

## 六、常见问题

- **中文乱码**：确认用 UTF-8 保存代码（本项目文件均无 BOM）；CSV 读取默认 `utf-8-sig`。
- **报错 No module named 'streamlit'**：先执行 `pip install -r requirements.txt`。
- **加载慢**：整车 CSV 较大（2~5MB），上传后自动抽样预览，不影响异常检测。