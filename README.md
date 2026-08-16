# 缠论结构分析 (Chan-Structure Analysis)

基于**缠论（Chan Theory）**的股票走势结构分析技能：输入「分析 {股票代码}，{操作级别}」，自动完成 K 线 → 笔 → 中枢 → 买卖点 → 背驰的完整结构拆解，输出带交互图表的 HTML 结构报告。

适用于 WorkBuddy / TRAE 等支持 Skills 的 AI 助手（依赖**通达信 MCP** 拉取 K 线数据，本地 Python 计算，无第三方依赖）。

## 功能特性

- **笔划分**：含 MIN_GAP 成笔口径、内部极值矫正
- **中枢识别**：下-上-下三笔重叠，支持连接段排除、跨界延伸
- **买卖点**：一买 / 二买 / 三买 / 三卖（基于离开中枢后的回踩/反抽确认，重写于 v0.2.0）
- **背驰判定**：走势级别趋势背驰 + 笔级别盘整背驰分级，MACD 面积对比
- **交互图表**：K 线 + 笔连接 + 中枢区间（ZG/ZD 标注）+ 买卖点 + 背驰点 + MACD 柱面板
- **固定算法**：同一份数据永远输出同一结果，不引入主观预测

## 目录结构

```
chan-structure-analysis/
├── SKILL.md                  # 技能入口（触发词、快速上手）
├── references/
│   └── usage.md              # 执行流程、级别映射、固定算法详解
└── assets/
    ├── analyze.py            # 主脚本：读数据 → 调引擎 → 生成 HTML 报告
    ├── chanlon_engine.py     # 固定算法引擎（笔/中枢/买卖点/背驰，纯算法无 IO）
    ├── charts_template.js    # ECharts 图表模板（MACD 面板、背驰/买卖点标注）
    ├── report_template.html  # 报告 HTML 模板
    └── _shared/js/
        └── echarts.min.js    # ECharts 运行时（见下方「依赖」）
```

## 快速上手（3 步）

1. **拉数据**：调通达信 `tdx_kline` 拉取该股该级别 K 线（`tqFlag="1"` 前复权，`wantNum=300`）。
2. **存数据**：按约定格式存为 `assets/data/{code}_{period}.json`（格式见 `references/usage.md`）。
3. **跑脚本**：`python "assets/analyze.py" {code} {period} {名称}` → 生成 `assets/output/{code}_{period}/chan-{code}-{period}.html`。

## 依赖

- Python 3.10+（仅标准库，无第三方依赖）
- 通达信 MCP（拉取 K 线数据）
- **echarts.min.js**：因体积（约 1MB）未纳入本仓库，请从 [Apache ECharts 官方 CDN](https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js) 下载后放到 `assets/_shared/js/echarts.min.js`。

## 数据格式

```json
{
  "code": "600519", "period": "30min", "name": "贵州茅台",
  "meta": {"change_pct": 1.23, "turnover": 0.56},
  "bars": [
    {"t": "2026-08-14 14:00", "o": 52.1, "h": 52.6, "l": 51.9, "c": 52.4}
  ]
}
```

## 免责声明

本技能输出的结构分析与操作建议仅供参考，**不构成投资建议**；涉及实际交易请结合风险管理。
