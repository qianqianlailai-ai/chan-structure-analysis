# -*- coding: utf-8 -*-
"""缠论结构分析 · 命令行入口
================================
用法:
    python analyze.py <code> <period> [name] [--out <dir>]

示例:
    python analyze.py 300058 30min 蓝色光标

数据约定:
    从 assets/data/<code>_<period>.json 读取 K 线（格式见下方 __doc__ 或 SKILL.md）。
    输出到 assets/output/<code>_<period>/ 下的 charts.js 与 HTML 报告。

注意:
    数据文件须由对话环境中调用通达信 MCP 获取后按约定格式保存。
    本脚本不联网、不调 MCP，纯本地计算。
"""
import json
import os
import sys
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chanlon_engine as eng

DATA_DIR = os.path.join(HERE, "data")
OUT_BASE = os.path.join(HERE, "output")
SHARED_SRC = os.path.join(HERE, "_shared")

PERIOD_ALIAS = {
    "5min": "5min", "5m": "5min", "5分钟": "5min",
    "15min": "15min", "15m": "15min", "15分钟": "15min",
    "30min": "30min", "30m": "30min", "30分钟": "30min",
    "1h": "1h", "60min": "1h", "1小时": "1h",
    "day": "day", "日": "day", "日线": "day",
    "week": "week", "周": "week", "周线": "week",
    "month": "month", "月": "month", "月线": "month",
}
PERIOD_LABEL = {"5min": "5分钟", "15min": "15分钟", "30min": "30分钟",
                "1h": "1小时", "day": "日线", "week": "周线", "month": "月线"}


def load_data(code, period):
    path = os.path.join(DATA_DIR, f"{code}_{period}.json")
    if not os.path.exists(path):
        sys.exit(f"[错误] 未找到数据文件: {path}\n请先在对话中调用通达信 MCP 拉取 K 线并保存到该约定路径。")
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except json.JSONDecodeError as e:
        sys.exit(f"[错误] 数据文件不是合法 JSON（可能被截断或损坏）: {path}\n位置: 第 {e.lineno} 行第 {e.colno} 列: {e.msg}\n请重新拉取 K 线并完整保存。")
    if not isinstance(obj, dict):
        sys.exit(f"[错误] 数据文件顶层必须是 JSON 对象（含 bars 数组），实际是 {type(obj).__name__}。\n正确格式见 SKILL.md 第 2 步。")
    raw = obj.get("bars")
    if not isinstance(raw, list) or not raw:
        sys.exit(f"[错误] 数据文件缺少 bars 数组或为空。\n正确格式: {{\"bars\": [{{\"t\": \"日期 时间(秒)\", \"o\":.., \"h\":.., \"l\":.., \"c\":..}}]}}")
    bars = []
    for idx, b in enumerate(raw):
        if not isinstance(b, dict):
            sys.exit(f"[错误] bars[{idx}] 必须是对象（含 t/o/h/l/c 字段），实际是 {type(b).__name__}。")
        try:
            t = str(b["t"]).strip()
            o = float(b["o"]); h = float(b["h"]); l = float(b["l"]); c = float(b["c"])
        except (KeyError, TypeError, ValueError) as e:
            sys.exit(f"[错误] bars[{idx}] 字段缺失或数值非法: {e}\n每根K线需含 t/o/h/l/c（t=日期时间字符串，o/h/l/c=可转 float 的价格），示例见 SKILL.md。")
        if len(t) < 8:
            sys.exit(f"[错误] bars[{idx}] 的 t 字段格式非法: '{t}'（长度不足）。应为 \"YYYYMMDD 时间(秒)\" 形式，如 \"20260624 48600\"。")
        if h < l:
            sys.exit(f"[错误] bars[{idx}] 的 high({h}) < low({l})，价格数据异常，请检查数据源。")
        bars.append({"t": t, "d": t[:8], "o": o, "h": h, "l": l, "c": c})
    bars.sort(key=lambda x: x["t"])
    if len(bars) < 30:
        print(f"[警告] K线仅 {len(bars)} 根，可能不足以形成完整笔/中枢结构，结论参考价值有限。")
    meta = obj.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}
    name = obj.get("name") or meta.get("name") or code
    return name, bars, meta


def build_charts_js(analyzed, bars):
    seq = analyzed["seq"]
    bi = analyzed["bi"]
    cats = [b["t"] for b in bars]
    ohlc = [[b["o"], b["c"], b["l"], b["h"]] for b in bars]
    bips = [{"dir": b[2], "sp": b[3], "ep": b[4],
             "s_idx": analyzed["bi_ext"][bi_idx][0], "e_idx": analyzed["bi_ext"][bi_idx][1]} for bi_idx, b in enumerate(bi)]
    zms = [{"zg": z[2], "zd": z[3],
            "s_idx": analyzed["bi_ext"][z[0]][0], "e_idx": analyzed["bi_ext"][z[4][-1]][1],
            "first_bi": z[0], "last_bi": z[4][-1]} for z in analyzed["zs"]]
    divs = [{"bi": d["bi"], "side": d["side"]} for d in analyzed["divergence"]]
    # 买卖点直接标图上：算到对应笔终点极值的bar坐标
    sig_bi = set()
    sigs = []
    for s in analyzed["signals"]:
        bi_idx = s["bi"]
        if bi_idx >= len(analyzed["bi_ext"]):
            continue
        sigs.append({"type": s["type"], "price": s["price"],
                     "idx": analyzed["bi_ext"][bi_idx][1], "buy": s["type"].endswith("买")})
        sig_bi.add(bi_idx)
    # 背驰点与买卖点同笔时去重（避免重叠），其余保留
    divs2 = []
    for d in analyzed["divergence"]:
        if d["bi"] in sig_bi:
            continue
        divs2.append({"side": d["side"], "price": d["price"],
                      "idx": analyzed["bi_ext"][d["bi"]][1]})
    hist = eng.compute_macd(bars)
    tpl = open(os.path.join(HERE, "charts_template.js"), "r", encoding="utf-8").read()
    tpl = tpl.replace('{"__CATS__"}', json.dumps(cats, ensure_ascii=False))
    tpl = tpl.replace('{"__OHLC__"}', json.dumps(ohlc))
    tpl = tpl.replace('{"__BIPOINTS__"}', json.dumps(bips, ensure_ascii=False))
    tpl = tpl.replace('{"__ZSMARKS__"}', json.dumps(zms, ensure_ascii=False))
    tpl = tpl.replace('{"__DIVERGENCE__"}', json.dumps(divs2, ensure_ascii=False))
    tpl = tpl.replace('{"__SIGPOINTS__"}', json.dumps(sigs, ensure_ascii=False))
    tpl = tpl.replace('{"__MACD__"}', json.dumps([round(v, 4) for v in hist]))
    return tpl


def build_html(analyzed, bars, name, code, period, meta):
    st = analyzed["state"]
    zs = analyzed["zs"]
    bips = analyzed["bi"]
    now = st["now"]
    hi = max(b["h"] for b in bars)
    lo = min(b["l"] for b in bars)
    t0 = bars[0]["t"][:8]; t1 = bars[-1]["t"][:8]
    chg = meta.get("change_pct")
    tot = meta.get("turnover")

    # 最近一笔方向三态：up / down / 无成笔（数据不足或极端行情）
    bi_dir = st.get("last_bi_dir")
    dir_txt = "向上" if bi_dir == "up" else ("向下" if bi_dir == "down" else "无成笔")
    rise_txt = "上涨" if bi_dir == "up" else ("回调" if bi_dir == "down" else "无成笔")

    off = (now - lo) / (hi - lo) * 100 if hi != lo else 0
    off_tag = "上方" if off > 90 else ("下方" if off < 10 else "中部")

    # ---- 结构摘要卡片 ----
    zs_info = ""
    if st.get("last_zs"):
        z = st["last_zs"]
        zs_info = f"最近中枢 {z['zd']}-{z['zg']}({z['range']})"
    cards = f"""
      <div class="summary-item">
        <div class="label">最近一笔</div>
        <div class="value">{dir_txt} <span class="tag {'tag-up' if bi_dir=='up' else ('tag-down' if bi_dir=='down' else 'tag-neutral')}">{'完成' if st['last_bi_done']=='完成' else ('进行中' if st['last_bi_done']=='进行中' else st['last_bi_done'])}</span></div>
        <div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem">{st['last_bi']}</div>
      </div>
      <div class="summary-item">
        <div class="label">区间位置</div>
        <div class="value">{off_tag} <span class="tag tag-neutral">{off:.0f}%</span></div>
        <div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem">现价 {now:.2f} 位于区间 {lo:.2f}-{hi:.2f}</div>
      </div>
      <div class="summary-item">
        <div class="label">中枢数量</div>
        <div class="value">{len(zs)} 个</div>
        <div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem">{zs_info}</div>
      </div>
      <div class="summary-item">
        <div class="label">最近线段</div>
        <div class="value">{rise_txt} <span class="tag tag-neutral">进行中</span></div>
        <div style="font-size:0.78rem;color:var(--muted);margin-top:0.2rem">自 {lo:.2f} 起，当前阶段位</div>
      </div>"""

    # ---- 结构摘要叙述 ----
    if st.get("last_zs"):
        z = st["last_zs"]
        summary_text = (f"区间自 <strong>{hi:.2f}</strong> 起，在 <strong>{lo:.2f}–{hi:.2f}</strong> 区间内震荡，"
                        f"最近中枢为 <strong>{z['range']}</strong>（上沿 ZG={z['zg']:.2f}，下沿 ZD={z['zd']:.2f}），"
                        f"现价 <strong>{now:.2f}</strong> 运行于中枢<strong>{z['pos']}</strong>。"
                        f"最近一笔为{dir_txt}（{st['last_bi']}），当前处于{'阶段高位' if off>70 else ('阶段低位' if off<30 else '区间中部')}。")
    else:
        summary_text = (f"区间自 <strong>{lo:.2f}</strong> 至 <strong>{hi:.2f}</strong>，"
                        f"当前未形成完整中枢，结构尚在构筑中，现价 <strong>{now:.2f}</strong>。")

    # ---- 中枢表 ----
    zrows = ""
    for k, z in enumerate(zs):
        width = abs(z[2] - z[3])
        note = "最近中枢" if k == len(zs) - 1 else "同级别中枢"
        if len(zs) == 1:
            note = "区间内中枢"
        style = ' style="background:var(--accent2);color:var(--bg);"' if k == len(zs) - 1 else ""
        num_style = ' style="color:var(--bg)"' if k == len(zs) - 1 else ""
        mark = " ★" if k == len(zs) - 1 else ""
        zrows += f"""          <tr{style}>
            <td>{k+1}{mark}</td><td>笔 {z[0]}–{z[4][-1]}</td>
            <td class="num"{num_style}>{z[2]:.2f}</td><td class="num"{num_style}>{z[3]:.2f}</td>
            <td class="num">{width:.2f}</td><td>{note}</td>
          </tr>"""

    zs_card = ""
    if st.get("last_zs"):
        z = st["last_zs"]
        zs_card = f"""<div class="card" style="margin-top:0.8rem;">
      <p>最近中枢上沿 <strong style="color:var(--accent)">ZG = {z['zg']:.2f}</strong>，下沿 <strong style="color:var(--accent2)">ZD = {z['zd']:.2f}</strong>，现价 <strong>{now:.2f}</strong> 运行于中枢<strong>{z['pos']}</strong>。</p>
    </div>"""

    # ---- 买卖点清单（与图上标注一一对应，极简）----
    sig_cards = ""
    if analyzed["signals"]:
        rows = []
        for s in sorted(analyzed["signals"], key=lambda x: x["bi"]):
            color = "accent" if s["type"].endswith("买") else "accent2"
            rows.append(f'<span class="tag" style="background:var({color});color:var(--bg)">{s["type"]}</span>'
                        f' <strong style="color:var({color})">{s["price"]:.2f}</strong> · 笔{s["bi"]}')
        sig_cards = ('<div class="card" style="border-color:var(--gold)">'
                     '<p><strong style="color:var(--gold)">买卖点</strong>（与图上标注对应）：'
                     + '　'.join(rows) + '</p></div>')

    # ---- 操作建议 ----
    if st.get("last_zs"):
        z = st["last_zs"]
        if z["pos"] == "下方":
            adv_head = "跌破中枢下沿 · 紧盯反抽确认"
            adv = f"""<li>关键位置 <strong>{z['zd']:.2f}</strong>(中枢下沿)：现价 {now:.2f} 处下沿下方，方向即将明朗。</li>
        <li>已持有者：观察反抽能否重回 <strong>{z['zd']:.2f}</strong> 上方；若放量续跌破位，则需控制风险。</li>
        <li>未入场者：不追高，等待回抽站稳下沿确认企稳，或三卖确认后的后续买点信号。</li>"""
        elif z["pos"] == "上方":
            adv_head = "中枢上方 · 关注回踩确认"
            adv = f"""<li>关键位置 <strong>{z['zg']:.2f}</strong>(中枢上沿)：现价 {now:.2f} 处上沿上方。</li>
        <li>已持有者：可持有，回踩不破 <strong>{z['zg']:.2f}</strong> 则结构偏多；放量跌破则警惕转弱。</li>
        <li>未入场者：等待回踩上沿确认，或三买结构确立后再介入。</li>"""
        else:
            adv_head = "中枢内部 · 等待方向选择"
            adv = f"""<li>关键区间 <strong>{z['zd']:.2f}–{z['zg']:.2f}</strong>(中枢)：现价 {now:.2f} 运行于中枢内部。</li>
        <li>已持有者：区间内可持股，跌破 <strong>{z['zd']:.2f}</strong> 或站上 <strong>{z['zg']:.2f}</strong> 再作方向性判断。</li>
        <li>未入场者：等待价格突破中枢上沿或跌破下沿后的明确方向。</li>"""
    else:
        adv_head = "结构未定 · 等待中枢构筑"
        adv = f"""<li>当前尚未形成完整中枢，方向未明。</li>
        <li>建议观望，等待连续三笔重叠确认中枢后再做判断。</li>"""

    # ---- 背驰卡片 ----
    divs = analyzed["divergence"]
    sig_bi = {s["bi"] for s in analyzed["signals"]}
    if divs:
        has_walk = any(d.get("level") == "走势级别" for d in divs)
        rows = []
        for d in divs:
            if d["bi"] in sig_bi:
                continue
            is_sell = d["side"] == "卖"
            color = "accent2" if is_sell else "accent"
            rows.append(f'<span class="tag" style="background:var({color});color:var(--bg)">{d["side"]}</span>'
                        f' <strong style="color:var({color})">{d.get("level","笔级别")}</strong> {d["price"]:.2f} · 笔{d["bi"]}')
        lvl_note = ("<p style=\"font-size:0.78rem;color:var(--muted);margin-top:0.4rem\">级别说明：图上买卖点均为<b>笔级别</b>盘整背驰结构（未确认离开中枢），只代表次级别转折，<b>非走势级别确认的一买/一卖</b>。</p>"
                    if not has_walk else "")
        list_html = '　'.join(rows) if rows else "（力度衰竭信号均已并入上方买卖点标注）"
        div_html = f"""<div class="card" style="border-color:var(--gold)">
      <p><strong style="color:var(--gold)">背驰</strong>（与图上标注对应）：{list_html}</p>{lvl_note}
    </div>"""
    else:
        div_html = """<div class="card">
      <p>未检测到背驰信号。</p>
    </div>"""

    chg_txt = f" ({chg:+.2f}%)" if chg is not None else ""
    chg_cls = "up" if (chg or 0) >= 0 else "down"
    tot_txt = f"{tot:.2f}%" if tot is not None else "--"

    meta_html = f"""<div class="meta-item">现价 <strong>{now:.2f}</strong> <span class="{chg_cls}">{chg_txt}</span></div>
      <div class="meta-item">区间最高 <strong>{hi:.2f}</strong></div>
      <div class="meta-item">区间最低 <strong>{lo:.2f}</strong></div>
      <div class="meta-item">换手率 <strong>{tot_txt}</strong></div>"""

    tpl = open(os.path.join(HERE, "report_template.html"), "r", encoding="utf-8").read()
    repl = {
        "{{TITLE}}": f"{name} {code} · {PERIOD_LABEL.get(period,'')}缠论结构分析",
        "{{SUBTITLE}}": f"数据源：通达信 MCP · {len(bars)}根{PERIOD_LABEL.get(period,'')}K线（{t0} – {t1}）· 前复权",
        "{{META}}": meta_html,
        "{{SUMMARY_CARDS}}": cards,
        "{{SUMMARY_TEXT}}": summary_text,
        "{{ZS_TABLE}}": zrows,
        "{{ZS_CARD}}": zs_card,
        "{{SIGNALS}}": sig_cards,
        "{{DIVERGENCE}}": div_html,
        "{{ADVICE_HEAD}}": adv_head,
        "{{ADVICE}}": adv,
        "{{FOOTER}}": f"缠论结构分析 · {name} {code} · {PERIOD_LABEL.get(period,'')}级别 · 数据截至 {t1} 收盘",
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


def main():
    if len(sys.argv) < 3:
        print("用法: python analyze.py <code> <period> [name] [--out <dir>]")
        return
    code = sys.argv[1]
    period_raw = sys.argv[2].lower()
    period = PERIOD_ALIAS.get(period_raw, period_raw)
    name = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else None
    out = None
    if "--out" in sys.argv:
        _oi = sys.argv.index("--out")
        if _oi + 1 >= len(sys.argv):
            sys.exit("[错误] --out 后缺少输出目录参数。\n用法: python analyze.py <code> <period> [name] [--out <dir>]")
        out = sys.argv[_oi + 1]

    name, bars, meta = load_data(code, period)
    if not name or name == code:
        name = meta.get("name", code)

    analyzed = eng.analyze(bars)
    seq = analyzed["seq"]

    out_dir = out or os.path.join(OUT_BASE, f"{code}_{period}")
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "_shared", "js"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "_shared", "fonts"), exist_ok=True)

    charts_js = build_charts_js(analyzed, bars)
    with open(os.path.join(out_dir, "assets", "charts.js"), "w", encoding="utf-8") as f:
        f.write(charts_js)

    html = build_html(analyzed, bars, name, code, period, meta)
    html_name = f"chan-{code}-{period}.html"
    with open(os.path.join(out_dir, html_name), "w", encoding="utf-8") as f:
        f.write(html)

    shutil.copy(os.path.join(SHARED_SRC, "js", "echarts.min.js"),
                os.path.join(out_dir, "_shared", "js", "echarts.min.js"))
    # 字体为可选：仅当 _shared/fonts 存在且含字体文件时拷贝（发布版可剔除字体）
    fonts_src = os.path.join(SHARED_SRC, "fonts")
    if os.path.isdir(fonts_src) and [f for f in os.listdir(fonts_src) if f.lower().endswith(('.ttf', '.otf', '.woff'))]:
        for fn in os.listdir(fonts_src):
            shutil.copy(os.path.join(fonts_src, fn),
                        os.path.join(out_dir, "_shared", "fonts", fn))

    # ---- 打印结构摘要 ----
    print(f"\n{name} {code} · {PERIOD_LABEL.get(period,'')} · {len(bi:=analyzed['bi'])} 笔 · {len(analyzed['zs'])} 中枢")
    prev_dir = None
    for k, b in enumerate(bi):
        flag = "  <-- 连续同向!" if b[2] == prev_dir else ""
        print(f"  [{k}] {b[2]:4} {b[3]:6.2f} -> {b[4]:6.2f}  {bars[seq[b[0]][2]]['t'][:8]}..{bars[seq[b[1]][2]]['t'][:8]}{flag}")
        prev_dir = b[2]
    print("  中枢:")
    for k, z in enumerate(analyzed["zs"]):
        print(f"    [{k}] 笔{z[0]}-{z[4][-1]}  ZG={z[2]:.2f} ZD={z[3]:.2f}")
    bd = analyzed['state']['last_bi_dir']
    bd_txt = "向上" if bd == "up" else ("向下" if bd == "down" else "无成笔")
    print(f"  当前: 现价 {analyzed['state']['now']:.2f}  最近一笔 {bd_txt} {analyzed['state']['last_bi']}")
    print(f"\n✔ 已生成报告: {os.path.join(out_dir, html_name)}")
    print(f"✔ 已生成图表: {os.path.join(out_dir, 'assets', 'charts.js')}")


if __name__ == "__main__":
    main()