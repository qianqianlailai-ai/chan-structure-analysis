/* 缠论结构分析 · 图表模板（自动注入数据） */
(function() {
  var $style = getComputedStyle(document.documentElement);
  var accent = $style.getPropertyValue('--accent').trim();
  var accent2 = $style.getPropertyValue('--accent2').trim();
  var ink = $style.getPropertyValue('--ink').trim();
  var muted = $style.getPropertyValue('--muted').trim();
  var rule = $style.getPropertyValue('--rule').trim();

  var cats = {"__CATS__"};

  var ohlc = {"__OHLC__"};

  var biPoints = {"__BIPOINTS__"};

  var zsMarks = {"__ZSMARKS__"};

  var divergence = {"__DIVERGENCE__"};

  var macdHist = {"__MACD__"};

  var biLines = biPoints.map(function(p) {
    return [
      {coord: [p.s_idx, p.sp], symbol: 'circle', symbolSize: 5},
      {coord: [p.e_idx, p.ep], symbol: 'arrow', symbolSize: 7}
    ];
  });

  var zsKeyPoints = [];
  zsMarks.forEach(function(z) {
    var fb = z.first_bi;
    var pens = [biPoints[fb], biPoints[fb+1], biPoints[fb+2]];
    var penHighs = pens.map(function(p) {
      return {idx: p.sp > p.ep ? p.s_idx : p.e_idx, val: Math.max(p.sp, p.ep)};
    });
    var zgPt = penHighs.reduce(function(m, p) { return p.val < m.val ? p : m; });
    var penLows = pens.map(function(p) {
      return {idx: p.sp < p.ep ? p.s_idx : p.e_idx, val: Math.min(p.sp, p.ep)};
    });
    var zdPt = penLows.reduce(function(m, p) { return p.val > m.val ? p : m; });
    zsKeyPoints.push({
      coord: [zgPt.idx, zgPt.val], value: zgPt.val.toFixed(2),
      itemStyle: {color: accent, borderColor: '#fff', borderWidth: 1},
      symbol: 'circle', symbolSize: 9,
      label: {show: true, position: 'top', color: accent, fontSize: 10, fontWeight: 700,
              backgroundColor: 'rgba(13,17,23,0.85)', padding: [2,4], borderRadius: 3,
              formatter: 'ZG {c}'}
    });
    zsKeyPoints.push({
      coord: [zdPt.idx, zdPt.val], value: zdPt.val.toFixed(2),
      itemStyle: {color: accent2, borderColor: '#fff', borderWidth: 1},
      symbol: 'circle', symbolSize: 9,
      label: {show: true, position: 'bottom', color: accent2, fontSize: 10, fontWeight: 700,
              backgroundColor: 'rgba(13,17,23,0.85)', padding: [2,4], borderRadius: 3,
              formatter: 'ZD {c}'}
    });
  });

  // 背驰点：卖(顶背驰)在笔终点上方标注，买(底背驰)在笔终点下方标注
  var divPoints = divergence.map(function(d) {
    var isSell = d.side === '卖';
    return {
      coord: [d.idx, d.price],
      value: (isSell ? '顶背驰 ' : '底背驰 ') + d.price.toFixed(2),
      itemStyle: {color: isSell ? accent2 : accent, borderColor: '#fff', borderWidth: 1},
      symbol: isSell ? 'triangle' : 'pin', symbolSize: isSell ? 13 : 15,
      label: {show: true, position: isSell ? 'top' : 'bottom',
              color: isSell ? accent2 : accent, fontSize: 10, fontWeight: 700,
              backgroundColor: 'rgba(13,17,23,0.85)', padding: [2,4], borderRadius: 3,
              formatter: (isSell ? '顶背驰 ' : '底背驰 ') + d.price.toFixed(2)}
    };
  });

  // 买卖点：买(3买/1买/2买)在笔终点下方、卖(3卖)在笔终点上方标注
  var sigPoints = {"__SIGPOINTS__"};
  var sigMarks = sigPoints.map(function(s) {
    var isBuy = s.buy;
    return {
      coord: [s.idx, s.price],
      value: s.type + ' ' + s.price.toFixed(2),
      itemStyle: {color: isBuy ? accent : accent2, borderColor: '#fff', borderWidth: 1},
      symbol: isBuy ? 'pin' : 'triangle', symbolSize: isBuy ? 16 : 14,
      label: {show: true, position: isBuy ? 'bottom' : 'top',
              color: isBuy ? accent : accent2, fontSize: 11, fontWeight: 700,
              backgroundColor: 'rgba(13,17,23,0.85)', padding: [2,4], borderRadius: 3,
              formatter: s.type + ' ' + s.price.toFixed(2)}
    };
  });

  var zsAreas = zsMarks.map(function(z) {
    return [
      {
        xAxis: z.s_idx,
        itemStyle: {color: accent + '18', borderColor: accent + '50', borderWidth: 1},
        label: {
          show: true, position: 'insideTop', color: ink, fontSize: 10, fontWeight: 700,
          backgroundColor: 'rgba(13,17,23,0.75)', padding: [2, 6], borderRadius: 3,
          formatter: '中枢 笔' + z.first_bi + '-' + z.last_bi + '[' + z.zd.toFixed(2) + '~' + z.zg.toFixed(2) + ']'
        }
      },
      {xAxis: z.e_idx}
    ];
  });

  var macdBars = macdHist.map(function(v) {
    return {value: v, itemStyle: {color: v >= 0 ? accent : accent2}};
  });

  var chart = echarts.init(document.getElementById('chart-kline'), null, {renderer: 'svg'});
  chart.setOption({
    animation: false,
    tooltip: {trigger: 'axis', axisPointer: {type: 'cross'}, appendToBody: true},
    legend: {data: ['K线', '笔', '中枢', '买卖点', '背驰', 'MACD'], textStyle: {color: muted}, top: 5},
    axisPointer: {link: [{xAxisIndex: 'all'}]},
    grid: [
      {left: '8%', right: '4%', top: '10%', height: '52%'},
      {left: '8%', right: '4%', top: '70%', height: '18%'}
    ],
    xAxis: [
      {
        type: 'category', data: cats, scale: true, boundaryGap: true,
        axisLine: {lineStyle: {color: rule}},
        axisLabel: {show: false},
        splitLine: {show: false}
      },
      {
        type: 'category', data: cats, scale: true, boundaryGap: true,
        gridIndex: 1,
        axisLine: {lineStyle: {color: rule}},
        axisLabel: {color: muted, fontSize: 10, interval: Math.floor(cats.length/6)},
        splitLine: {show: false}
      }
    ],
    yAxis: [
      {
        scale: true, axisLine: {lineStyle: {color: rule}},
        axisLabel: {color: muted, fontSize: 10},
        splitLine: {lineStyle: {color: rule, type: 'dashed', opacity: 0.4}}
      },
      {
        scale: true, gridIndex: 1, axisLine: {lineStyle: {color: rule}},
        axisLabel: {color: muted, fontSize: 10},
        splitLine: {show: false}
      }
    ],
    dataZoom: [
      {type: 'inside', xAxisIndex: [0, 1], start: 40, end: 100},
      {type: 'slider', xAxisIndex: [0, 1], start: 40, end: 100, height: 20, bottom: 5, borderColor: rule, textStyle: {color: muted}}
    ],
    series: [
      {
        name: 'K线', type: 'candlestick', data: ohlc,
        itemStyle: {color: accent, color0: accent2, borderColor: accent, borderColor0: accent2},
        markArea: {silent: true, data: zsAreas.length ? zsAreas : []},
        markPoint: {data: zsKeyPoints.concat(sigMarks, divPoints), animation: false}
      },
      {
        name: '笔', type: 'lines', coordinateSystem: 'cartesian2d', polyline: false,
        lineStyle: {color: ink, width: 1.5}, data: biLines, symbol: ['none', 'none'], z: 10
      },
      {
        name: 'MACD', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: macdBars,
        barWidth: '60%'
      }
    ]
  });
  window.addEventListener('resize', function() { chart.resize(); });
})();
