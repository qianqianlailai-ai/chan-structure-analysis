# -*- coding: utf-8 -*-
"""缠论结构分析 · 固定算法引擎
================================
纯算法模块，不含任何 IO。输入 K 线列表，输出笔序列、中枢、买卖点与当前状态。
承载每次校准沉淀的全部规则：
  - K线包含合并 / 分型识别·合并·确认 / 严格成笔(MIN_GAP=3)
  - 内部极值矫正(含过近极值忽略) / 跨界延伸
  - 中枢构建 + 连接段排除
  - 买卖点检测(三买/三卖严格定义，一买/二买结构近似)

本文件是"固定逻辑"，除 MIN_GAP 等参数外无需改动。
"""
import json

MIN_GAP = 3  # 顶底分型之间至少间隔的合并K线数


# ---------------------------------------------------------------- K线合并
def merge_bars(bars):
    """原始K线 -> 合并K线序列 seq。每项 [high, low, 原始bar序号]"""
    def contains(a, b):
        return (a[0] >= b[0] and a[1] <= b[1]) or (b[0] >= a[0] and b[1] <= a[1])
    seq = []
    for i, b in enumerate(bars):
        h, l = b["h"], b["l"]
        if seq:
            prev = seq[-1]
            if contains(prev, (h, l, 0)):
                up = seq[-1][0] > seq[-2][0] if len(seq) >= 2 else True
                if up:
                    seq[-1] = [max(prev[0], h), max(prev[1], l), prev[2]]
                else:
                    seq[-1] = [min(prev[0], h), min(prev[1], l), prev[2]]
            else:
                seq.append([h, l, i])
        else:
            seq.append([h, l, i])
    return seq


# ---------------------------------------------------------------- 分型
def find_fractals(seq):
    fr = []
    for i in range(1, len(seq) - 1):
        h_p, h_c, h_n = seq[i - 1][0], seq[i][0], seq[i + 1][0]
        l_p, l_c, l_n = seq[i - 1][1], seq[i][1], seq[i + 1][1]
        if h_c > h_p and h_c > h_n:
            fr.append((i, "top", h_c))
        elif l_c < l_p and l_c < l_n:
            fr.append((i, "bottom", l_c))
    return fr


def merge_fractals(fractals):
    merged = []
    for f in fractals:
        if merged and merged[-1][1] == f[1]:
            if (f[1] == "top" and f[2] > merged[-1][2]) or (f[1] == "bottom" and f[2] < merged[-1][2]):
                merged[-1] = f
        else:
            merged.append(f)
    return merged


def confirm_fractals(seq, merged):
    n = len(seq)
    confirmed = []
    for fi, typ, price in merged:
        if fi + 1 >= n:
            continue
        if typ == "top":
            confirm_val = seq[fi + 1][1]
        else:
            confirm_val = seq[fi + 1][0]
        ok = False
        j = fi + 2
        while j < n:
            if typ == "top":
                if seq[j][1] < confirm_val:
                    ok = True; break
            else:
                if seq[j][0] > confirm_val:
                    ok = True; break
            if j + 1 < n:
                h_p, h_c, h_n_ = seq[j - 1][0], seq[j][0], seq[j + 1][0]
                l_p, l_c, l_n_ = seq[j - 1][1], seq[j][1], seq[j + 1][1]
                if typ == "top" and l_c < l_p and l_c < l_n_:
                    break
                if typ == "bottom" and h_c > h_p and h_c > h_n_:
                    break
            j += 1
        if ok:
            confirmed.append((fi, typ, price))
    return confirmed


def _confirmed(seq, fractals):
    merged = merge_fractals(fractals)
    return merge_fractals(confirm_fractals(seq, merged))


# ---------------------------------------------------------------- 成笔
def build_bi(seq, fractals):
    confirmed = _confirmed(seq, fractals)
    bi = []
    n = len(confirmed)
    if n < 2:
        return bi
    start = confirmed[0]
    end = None
    i = 1
    while i < n:
        f = confirmed[i]
        if end is None:
            end = f
        elif f[1] == end[1]:
            if (f[1] == "top" and f[2] > end[2]) or (f[1] == "bottom" and f[2] < end[2]):
                end = f
        else:
            if end[0] - start[0] >= MIN_GAP and f[0] - end[0] >= MIN_GAP:
                bi.append([start[0], end[0], "up" if start[1] == "bottom" else "down", start[2], end[2]])
                start = end
                end = f
            else:
                if (f[1] == "top" and f[2] > start[2]) or (f[1] == "bottom" and f[2] < start[2]):
                    start = f
                    end = None
        i += 1
    if end is not None and end[0] - start[0] >= MIN_GAP:
        bi.append([start[0], end[0], "up" if start[1] == "bottom" else "down", start[2], end[2]])
    return bi


# ---------------------------------------------------------------- 第二遍矫正
def correct_interior_extreme(seq, fractals, bi):
    """终点矫正：向上笔终点取区间内最高顶分型、向下笔取区间内最低底分型，
    并级联更新后续笔起点。过近极值(距起点<MIN_GAP)忽略。
    另含跨界延伸：若下一笔起点同方向比本笔终点更极端，本笔终点延伸到下一笔起点。"""
    confirmed = _confirmed(seq, fractals)
    bi = [list(b) for b in bi]
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False
        guard += 1
        for i in range(len(bi)):
            s, e, d, sp, ep = bi[i]
            interior = [f for f in confirmed if s < f[0] < e and f[0] - s >= MIN_GAP]
            new_end = None
            if d == "up":
                tops = [f for f in interior if f[1] == "top"]
                if tops:
                    mx = max(tops, key=lambda f: f[2])
                    if mx[2] > ep:
                        new_end = mx
            else:
                bots = [f for f in interior if f[1] == "bottom"]
                if bots:
                    mn = min(bots, key=lambda f: f[2])
                    if mn[2] < ep:
                        new_end = mn
            if new_end is not None:
                bi[i][1] = new_end[0]
                bi[i][4] = new_end[2]
                if i + 1 < len(bi):
                    bi[i + 1][0] = new_end[0]
                    bi[i + 1][3] = new_end[2]
                changed = True
            # 跨界延伸：下一笔起点在同方向比本笔终点更极端
            if i + 1 < len(bi):
                nxt = bi[i + 1]
                if d == "up" and nxt[3] > ep and s < nxt[0] and nxt[0] - s >= MIN_GAP and nxt[2] == "down":
                    bi[i][1] = nxt[0]
                    bi[i][4] = nxt[3]
                    changed = True
                elif d == "down" and nxt[3] < ep and s < nxt[0] and nxt[0] - s >= MIN_GAP and nxt[2] == "up":
                    bi[i][1] = nxt[0]
                    bi[i][4] = nxt[3]
                    changed = True
    return bi


# ---------------------------------------------------------------- K线极值贴合
def _bar_to_grp(seq, bar_idx):
    """把原始 bar 序号映射到其所属合并K线组 seq 下标。"""
    for g in range(len(seq)):
        gs = seq[g][2]
        ge = seq[g + 1][2] - 1 if g + 1 < len(seq) else 10 ** 9
        if gs <= bar_idx <= ge:
            return g
    return len(seq) - 1


def fit_extreme_to_kline(bars, seq, bi, tol=0.01):
    """把笔终点贴合到该笔覆盖 K 线区间内的真实极值。

    问题：分型确认用合并K线值，可能让笔终点落在分型值上，而同一笔区间内
    某些原始 K 线的真实低/高更极端（如 5.42 之后还有 5.40、5.22 之后还有
    5.20、5.20 之前还有 5.17），但这些 K 线未形成独立底分型，传统极值矫正
    抓不到。这里对每笔（含最后一笔）扫描其完整 K 线区间，向更极端贴合，
    并级联更新下一笔起点，使低点/高点贴合肉眼所见 K 线极值。

    约束：不侵入下一笔（极值不越过下一笔终点组）、极值组距笔起点 >= MIN_GAP。
    """
    bi = [list(b) for b in bi]
    n = len(bi)
    for i in range(n):
        s, e, d, sp, ep = bi[i]
        lo = seq[s][2]                                  # 本笔起点 bar
        hi = seq[bi[i + 1][1]][2] if i + 1 < n else len(bars) - 1
        if hi <= lo:
            continue
        if d == "down":
            best = min(range(lo, hi + 1), key=lambda k: bars[k]["l"])
            val = bars[best]["l"]
            if val < ep - tol:
                grp = _bar_to_grp(seq, best)
                if grp - s >= MIN_GAP and (i + 1 >= n or grp < bi[i + 1][1]):
                    bi[i][1] = grp
                    bi[i][4] = round(val, 2)
                    if i + 1 < n:
                        bi[i + 1][0] = grp
                        bi[i + 1][3] = round(val, 2)
        else:
            best = max(range(lo, hi + 1), key=lambda k: bars[k]["h"])
            val = bars[best]["h"]
            if val > ep + tol:
                grp = _bar_to_grp(seq, best)
                if grp - s >= MIN_GAP and (i + 1 >= n or grp < bi[i + 1][1]):
                    bi[i][1] = grp
                    bi[i][4] = round(val, 2)
                    if i + 1 < n:
                        bi[i + 1][0] = grp
                        bi[i + 1][3] = round(val, 2)
    return bi


# ---------------------------------------------------------------- 中枢
def build_zhongshu(bi):
    """连续三笔重叠成中枢，延伸后再按连接段排除确定下一中枢起始笔。"""
    zs = []
    i = 0
    while i <= len(bi) - 3:
        b1, b2, b3 = bi[i], bi[i + 1], bi[i + 2]
        max_low = max(min(b1[3], b1[4]), min(b2[3], b2[4]), min(b3[3], b3[4]))
        min_high = min(max(b1[3], b1[4]), max(b2[3], b2[4]), max(b3[3], b3[4]))
        if max_low < min_high:
            j = i + 3
            while j < len(bi):
                bh = max(bi[j][3], bi[j][4]); bl = min(bi[j][3], bi[j][4])
                if bh > max_low and bl < min_high:
                    j += 1
                else:
                    break
            zs.append([i, j - 1, min_high, max_low, list(range(i, j))])
            last_ep = bi[j - 1][4]
            if last_ep < max_low or last_ep > min_high:
                i = j + 1
            else:
                i = j
        else:
            i += 1
    return zs


# ---------------------------------------------------------------- 买卖点检测
def detect_signals(bi, zs):
    """确定性买卖点检测。返回信号列表，每项 dict。
    三买：向上笔突破中枢上沿ZG后，回踩笔低点仍>ZG。
    三卖：向下笔跌破中枢下沿ZD后，反抽笔高点仍<ZD。
    一买：区间最低点(结构近似)；二买：一买后回调不创新低的次低点。
    """
    signals = []
    # 三买/三卖：只检测中枢结束处的第一段离开 + 紧邻回踩/反抽确认
    for zi, z in enumerate(zs):
        zg, zd = z[2], z[3]
        last = z[4][-1]
        # 找第一根离开中枢的笔（向上突破上沿 / 向下跌破下沿）
        leave = None
        for i in range(last, len(bi)):
            if bi[i][2] == "up" and bi[i][4] > zg:
                leave = (i, "up"); break
            if bi[i][2] == "down" and bi[i][4] < zd:
                leave = (i, "down"); break
        if leave is None:
            continue
        li, ld = leave
        # 离开笔之后第一根反向笔确认（回踩不破上沿 → 三买；反抽不破下沿 → 三卖）
        for j in range(li + 1, len(bi)):
            if bi[j][2] == ("down" if ld == "up" else "up"):
                if ld == "up" and bi[j][4] > zg:
                    signals.append({"type": "3买", "price": round(bi[j][4], 2), "bi": j,
                                    "about": f"突破中枢{zi}上沿{zg:.2f}后回踩不破，低点{bi[j][4]:.2f}仍在上沿上方"})
                elif ld == "down" and bi[j][4] < zd:
                    signals.append({"type": "3卖", "price": round(bi[j][4], 2), "bi": j,
                                    "about": f"跌破中枢{zi}下沿{zd:.2f}后反抽不破，高点{bi[j][4]:.2f}仍在下沿下方"})
                break
    # 一买/二买：区间最低点与次低点（结构近似）。
    # 排除最后一笔：它是当前进行中/最近的一笔，端点未经后续走势确认，
    # 若把"下跌未走完的瞬低点"标成 1 买会误导（可能继续创新低）。
    done = bi[:-1]
    prices = [min(b[3], b[4]) for b in done]
    if prices:
        min_p = min(prices)
        min_i = prices.index(min_p)
        # 一旦区间内已出现更低价格（通常落在未确认的末笔上），该"最低点"即被破坏：
        # 一买只作为历史结构痕迹保留，降级标注为失效，不再当有效买点。
        global_min = min(min(b[3], b[4]) for b in bi)
        broken = global_min < min_p - 1e-9
        signals.append({"type": "1买", "status": "broken" if broken else "normal",
                        "price": min_p, "bi": min_i,
                        "about": (f"潜在一买(已完成笔最低点{min_p:.2f})，但已被后创新低 {global_min:.2f} 破坏，仅历史结构痕迹、不作有效买点"
                                  if broken else
                                  f"已完成笔中的最低点{min_p:.2f}(结构近似，下跌背驰后的阶段低点)")})
        # 二买：一买之后向下笔不创新低（同样只限已完成笔）；一买若已破坏则一并降级失效
        for i in range(min_i + 1, len(done)):
            if done[i][2] == "down" and min(done[i][3], done[i][4]) > min_p and min(done[i][3], done[i][4]) < max(done[min_i][3], done[min_i][4]):
                signals.append({"type": "2买", "status": "broken" if broken else "normal",
                                "price": round(min(done[i][3], done[i][4]), 2),
                                "bi": i, "about": (f"回调低点{min(done[i][3],done[i][4]):.2f}本可为二买，但因一买已被 {global_min:.2f} 创新低破坏而失效"
                                                   if broken else
                                                   f"一买后回调未创新低，次低点{min(done[i][3],done[i][4]):.2f}")})
                break
    # 中枢上沿遇阻（减仓）：向上笔触及中枢上沿ZG却未能有效脱离，随即受压回落。
    # 该类笔未创新高、未确认离开中枢（否则为三买/离开段），只标"上沿压力/减仓"。
    for z in zs:
        zg, zd = z[2], z[3]
        tol = max(0.1 * (zg - zd), 1e-9)
        for i in range(z[0], len(bi)):
            b = bi[i]
            if b[2] == "up" and zg - 1e-9 <= b[4] <= zg + tol:
                if i + 1 < len(bi) and bi[i + 1][2] == "down":
                    signals.append({"type": "减仓", "status": "resistance", "price": round(b[4], 2), "bi": i,
                                    "about": f"反弹触及中枢上沿ZG={zg:.2f}遇阻回落，中枢上沿压力/减仓点"})
                    break  # 每中枢只标第一个触上沿的向上笔
    return signals


# ---------------------------------------------------------------- 当前状态
def current_state(bi, zs, bars, seq):
    """最近一笔方向/状态、最近中枢、现价相对最近中枢位置。"""
    if not bi:
        # 无成笔（极端行情/数据过少）：返回明确状态而非崩溃
        now = round(bars[-1]["c"], 2) if bars else None
        return {"last_bi_dir": None, "last_bi": "无成笔", "last_bi_done": "-",
                "last_bi_time": "", "now": now}
    last = bi[-1]
    s_idx = seq[last[0]][2]  # 原始bar序号
    e_idx = seq[last[1]][2]
    last_bar = bars[-1]
    now = last_bar["c"]
    state = {"last_bi_dir": last[2],
             "last_bi": f"{last[3]:.2f} → {last[4]:.2f}",
             "last_bi_done": "完成" if e_idx < len(bars) - 1 else "进行中",
             "last_bi_time": f"{bars[s_idx]['t'][:8]}..{bars[e_idx]['t'][:8]}"}
    if zs:
        z = zs[-1]
        zg, zd = z[2], z[3]
        if now > zg:
            pos = "上方"
        elif now < zd:
            pos = "下方"
        else:
            pos = "内部"
        state["last_zs"] = {"zg": round(zg, 2), "zd": round(zd, 2),
                            "range": f"笔{z[0]}-{z[4][-1]}", "pos": pos}
    state["now"] = round(now, 2)
    return state


# ---------------------------------------------------------------- 背驰（MACD）
def compute_macd(bars):
    """标准 MACD：DIF=EMA12-EMA26，DEA=EMA9(DIF)，柱=2*(DIF-DEA)。返回 hist 数组(与 bars 等长)。"""
    closes = [b["c"] for b in bars]
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    hist = [2 * (a - b) for a, b in zip(dif, dea)]
    return hist


def ema(series, n):
    k = 2.0 / (n + 1)
    out = [series[0]]
    for v in series[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def pen_areas(bi, seq, hist):
    """每笔区间内 MACD 柱面积。区分多空：向上笔累加柱>0，向下笔累加柱<0 的绝对值。"""
    areas = []
    for b in bi:
        s_bar = seq[b[0]][2]   # 原始bar序号
        e_bar = seq[b[1]][2]
        acc = 0.0
        for i in range(s_bar, e_bar + 1):
            v = hist[i]
            if b[2] == "up" and v > 0:
                acc += v
            elif b[2] == "down" and v < 0:
                acc += -v
        areas.append(acc)
    return areas


def zs_direction(bi, z):
    """中枢方向：离开段(中枢最后一笔后面与中枢同级别的第一笔)方向。
    找中枢 last_bi 之后的第一笔，作为离开方向。"""
    last = z[4][-1]
    if last + 1 < len(bi):
        return bi[last + 1][2]
    return bi[last][2]


def _seg_after(bi, i, direction):
    """中枢末笔 i 之后，第一个与 direction 同向的已完成笔；无则返回 -1。"""
    for j in range(i + 1, len(bi)):
        if bi[j][2] == direction:
            return j
    return -1


def _seg_before(bi, i, direction):
    """中枢首笔 i 之前，第一个与 direction 同向的笔；无则返回 -1。"""
    for j in range(i - 1, -1, -1):
        if bi[j][2] == direction:
            return j
    return -1


def _adj_same(bi, i):
    """笔 i 之前最近的一根同向笔；无则返回 None。"""
    for j in range(i - 1, -1, -1):
        if bi[j][2] == bi[i][2]:
            return j
    return None


def _confirm_leave(bi, zs, i):
    """笔 i 是否"确认离开"其所属中枢：突破边界后，紧邻反向笔不回破中枢（=三买/三卖确认）。
    只有确认离开的笔才构成"离开段"；否则它只是中枢内部的一段。"""
    b = bi[i]
    for z in zs:
        if z[0] <= i <= z[4][-1]:
            zg, zd = z[2], z[3]
            if b[2] == "up" and b[4] > zg:
                if i + 1 < len(bi) and bi[i + 1][2] == "down" and bi[i + 1][4] > zg:
                    return True
            if b[2] == "down" and b[4] < zd:
                if i + 1 < len(bi) and bi[i + 1][2] == "up" and bi[i + 1][4] < zd:
                    return True
    return False


def _enter_seg(bi, zs, i, direction):
    """中枢进入段：笔 i 所属中枢首笔之前，最近一根同向笔；无则取中枢首笔本身。"""
    for z in zs:
        if z[0] <= i <= z[4][-1]:
            first = z[0]
            for j in range(first - 1, -1, -1):
                if bi[j][2] == direction:
                    return j
            return first
    return None


def detect_divergence(bi, zs, areas):
    """背驰判定（中枢感知 + 终端极值过滤）。

    两个比较模式：
    - 趋势背驰：笔"确认离开"中枢（突破边界后回踩/反抽不破，=三买/三卖）后，
      与该中枢的进入段（中枢首笔之前的同向段）比较力度；
    - 盘整背驰：中枢内部创新高/新低的笔（未确认离开），只与紧邻的同向笔比较力度。

    这样避免两类误判：
    ① 把"被后创新高超越的中间高点/低点"误标（如4.18/4.50 被5.70超越后不再标注）；
    ② 把"未确认离开中枢的末笔"直接与远离的中枢启动大段比较（如6.07 与4.16→5.70
       大上升段比，级别不对等、产生背驰错觉）—— 未确认离开的笔只与紧邻同向段比，
       避免跨度过大的级别错配。
    """
    divs = []
    n = len(bi)
    for d in ("up", "down"):
        same = [i for i in range(n) if bi[i][2] == d]
        # 里程碑：逐次创新高/新低
        milestones = []
        best = None
        for i in same:
            ext = bi[i][4]
            if best is None or (d == "up" and ext > best) or (d == "down" and ext < best):
                milestones.append(i)
                best = ext
        if len(milestones) < 2:
            continue
        cur = milestones[-1]
        side = "买" if d == "down" else "卖"
        if _confirm_leave(bi, zs, cur):
            # 走势级别·趋势背驰：与中枢进入段比较，可确认一买/一卖
            base = _enter_seg(bi, zs, cur, d)
            if base is None or areas[cur] >= areas[base]:
                continue
            kind, level, comp = "趋势", "走势级别", base
            tail = f"，力度衰竭→{'一买' if d=='down' else '一卖'}确认"
        else:
            # 笔级别·盘整背驰：与紧邻同向笔比较，仅次级别转折，非走势级别买卖点
            adj = _adj_same(bi, cur)
            if adj is None or areas[cur] >= areas[adj]:
                continue
            kind, level, comp = "盘整", "笔级别", adj
            tail = "，力度衰竭→笔级别盘整背驰转折（非走势级别买卖点）"
        divs.append({"kind": kind, "side": side, "level": level, "bi": cur,
                     "in_seg": comp, "out_seg": cur,
                     "price": round(bi[cur][4], 2),
                     "desc": f"{level}·{kind}背驰：{'下跌' if d=='down' else '上涨'}段{bi[cur][3]:.2f}→{bi[cur][4]:.2f} 创新{'低' if d=='down' else '高'}，MACD面积({areas[cur]:.3f})<前段({areas[comp]:.3f}){tail}"})
    return divs


# ---------------------------------------------------------------- 主入口
def pen_extreme_bars(bars, seq, bi):
    """每笔起点/终点极值实际出现的原始bar序号。
    起点: 向上笔=区间最低low的bar, 向下笔=区间最高high的bar
    终点: 向上笔=区间最高high的bar, 向下笔=区间最低low的bar
    用于图表标注，避免合并K线组内极值位置偏移（如低点实际在组内后一根bar）。"""
    n = len(seq)
    def group_end(m):
        return seq[m + 1][2] - 1 if m + 1 < n else len(bars) - 1
    out = []
    for b in bi:
        s_m, e_m = b[0], b[1]
        s_start, s_end = seq[s_m][2], group_end(s_m)
        e_start, e_end = seq[e_m][2], group_end(e_m)
        if b[2] == "up":
            s_ext = min(range(s_start, s_end + 1), key=lambda i: bars[i]["l"])
            e_ext = max(range(e_start, e_end + 1), key=lambda i: bars[i]["h"])
        else:
            s_ext = max(range(s_start, s_end + 1), key=lambda i: bars[i]["h"])
            e_ext = min(range(e_start, e_end + 1), key=lambda i: bars[i]["l"])
        out.append([s_ext, e_ext])
    return out


def analyze(bars):
    """输入 bars(升序, 前复权)，输出完整结构 dict。"""
    seq = merge_bars(bars)
    fractals = find_fractals(seq)
    bi = build_bi(seq, fractals)
    bi = correct_interior_extreme(seq, fractals, bi)
    bi = fit_extreme_to_kline(bars, seq, bi)
    zs = build_zhongshu(bi)
    signals = detect_signals(bi, zs)
    hist = compute_macd(bars)
    areas = pen_areas(bi, seq, hist)
    divs = detect_divergence(bi, zs, areas)
    state = current_state(bi, zs, bars, seq)
    # 附加原始bar索引映射，供图表与报告使用
    bi_idx = [[seq[b[0]][2], seq[b[1]][2]] for b in bi]  # 原始bar序号
    bi_ext = pen_extreme_bars(bars, seq, bi)  # 极值实际bar序号
    return {
        "seq": seq, "bi": bi, "bi_idx": bi_idx, "bi_ext": bi_ext, "zs": zs,
        "signals": signals, "state": state, "divergence": divs, "areas": areas,
    }


def result_to_json(analyzed, bars):
    """把 analyze 输出转成便于生成报告的纯 JSON 结构。"""
    seq, bi = analyzed["seq"], analyzed["bi"]
    bips = [{"dir": b[2], "sp": b[3], "ep": b[4],
             "s_idx": seq[b[0]][2], "e_idx": seq[b[1]][2]} for b in bi]
    zms = [{"zg": z[2], "zd": z[3], "s_idx": seq[bi[z[0]][0]][2], "e_idx": seq[bi[z[1]][1]][2],
            "first_bi": z[0], "last_bi": z[4][-1]} for z in analyzed["zs"]]
    divs = [{"kind": d["kind"], "side": d["side"], "level": d["level"], "bi": d["bi"],
             "price": d["price"], "desc": d["desc"]} for d in analyzed["divergence"]]
    return {
        "bi_points": bips,
        "zs_marks": zms,
        "signals": analyzed["signals"],
        "state": analyzed["state"],
        "divergence": divs,
    }