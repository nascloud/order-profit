/* Official ECharts and Tabulator; project-specific presentation, no business recalculation. */
(() => {
  'use strict';
  const DATA = JSON.parse(document.querySelector('#reportData').textContent);
  const S = DATA.summary;
  const $ = selector => document.querySelector(selector);
  const profitTitle = DATA.provisional ? '已核算部分经营贡献利润' : '含推广经营贡献利润';
  const money = value => value == null ? '暂无' : '¥' + (value / 100).toLocaleString('zh-CN', {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  });
  const pct = value => value == null ? '暂无比例' : (value * 100).toFixed(2) + '%';
  const number = value => value == null ? '暂无' : Number(value).toLocaleString('zh-CN');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const share = (value, base, label) => `占${label} ${pct(
    finite(value) && finite(base) && base !== 0 ? value / base : null
  )}`;
  const ratioFields = new Set(['经营贡献利润率', '退款率', '销售贡献率', '盈利贡献率', '亏损占比',
    '店铺盈利贡献率', '占期间销售比例', '核算覆盖率', '平台费率', '税费率', '推广费率',
    '成本率', '运费率', '点击率']);
  const titles = { '含推广经营贡献利润_分': '经营贡献利润', '订单批次成功退款_分': '订单批次退款',
    '经营贡献利润率状态': '核算/利润率状态', 'SABC等级': 'SABC', '已付款主订单数': '主订单数',
    '商品链接数': '链接数' };
  const fieldTitle = field => titles[field] || field.replace(/_分$/, '');
  const fieldText = (field, value, row = {}) => {
    if (field === '经营贡献利润率' && row['经营贡献利润率状态'] &&
        row['经营贡献利润率状态'] !== '已核算') return row['经营贡献利润率状态'];
    if (field.endsWith('_分')) return money(value);
    if (ratioFields.has(field)) return pct(value);
    if (field === '推广投产比') return value == null ? '暂无' : Number(value).toFixed(2) + 'x';
    if (typeof value === 'number') return number(value);
    return value == null || value === '' ? '暂无' : String(value);
  };
  const showError = error => {
    $('#reportError').hidden = false;
    $('#reportError').textContent = '报告显示异常，请查看同目录 Excel 核算底稿。' + error.message;
  };
  const values = (target, items) => {
    $(target).innerHTML = items.map(([label, value, format = money, note = '']) =>
      `<div class="value"><span>${esc(label)}</span>` +
      `<b class="${value < 0 ? 'negative' : ''}">${esc(format(value))}</b>` +
      `${note ? `<small>${esc(note)}</small>` : ''}</div>`
    ).join('');
  };
  const charts = new Map();
  const grids = new Map();
  const readyGrids = new Set();
  const observer = new ResizeObserver(entries => {
    for (const {target} of entries) {
      if (!target.getBoundingClientRect().width) continue;
      const instance = charts.get(target.id);
      if (instance) instance.resize();
      const view = target.id.replace(/Grid$/, '');
      if (readyGrids.has(view)) grids.get(view).redraw(true);
    }
  });
  const chartBase = {
    animation: false, aria: {enabled: true},
    textStyle: {fontFamily: '-apple-system, "Microsoft YaHei", sans-serif', color: '#55656f'},
    tooltip: {trigger: 'axis', renderMode: 'richText', confine: true},
    grid: {left: 70, right: 32, top: 50, bottom: 54, containLabel: true}
  };
  const setChart = (id, option, empty, click) => {
    const node = $('#' + id);
    const emptyNode = $('#' + id + 'Empty');
    node.hidden = empty;
    if (emptyNode) emptyNode.hidden = !empty;
    if (empty) return null;
    let instance = charts.get(id);
    if (!instance) {
      instance = echarts.init(node, null, {renderer: 'svg'});
      charts.set(id, instance);
      observer.observe(node);
      if (click) instance.on('click', click);
    }
    instance.setOption({...chartBase, ...option}, true);
    instance.resize();
    return instance;
  };

  const buildOverview = () => {
    const keys = [['真实销售额', S['真实销售额_分'], money],
      [profitTitle, S['含推广经营贡献利润_分'], money],
      ['经营贡献利润率', S['经营贡献利润率'], pct],
      ['销售额核算覆盖率', S['销售额核算覆盖率'], pct]];
    $('#keyMetrics').innerHTML = keys.map(([label, value, format], i) =>
      `<div class="metric${i === 1 ? ' primary' : ''}"><span>${esc(label)}</span>` +
      `<b class="${value < 0 ? 'negative' : ''}">${esc(format(value))}</b></div>`
    ).join('');
    const paid = S['已付款销售额_分'];
    const accounted = S['已核算销售额_分'];
    const refund = S['已核算订单批次成功退款_分'];
    const net = finite(accounted) && finite(refund) ? accounted - refund : null;
    values('#salesValues', [['已付款销售额', paid],
      ['减：刷单金额', S['刷单金额_分']],
      ['减：全部订单批次退款', S['订单批次成功退款金额_分']],
      ['真实销售额', S['真实销售额_分']]]
      .map(([label, value]) => [label, value, money, share(value, paid, '已付款销售额')]));
    const costs = [['订单批次退款', '已核算订单批次成功退款_分'],
      ['货品成本', '已核算货品成本_分'], ['运费', '已核算运费_分'],
      ['刷单成本', '已核算刷单成本_分'], ['平台扣点（估算）', '已核算平台扣点_分'],
      ['综合税赋（估算）', '已核算综合税赋_分'], ['关闭已发货损失', '关闭已发货损失_分'],
      ['推广花费', '推广花费_分']];
    renderOverviewInsights(costs.slice(1), net);
    const profitNotes = [share(accounted, paid, '已付款销售额'),
      ...costs.map(([, field], i) => share(S[field], i === 0 ? accounted : net,
        i === 0 ? '已核算销售额' : '已核算净销售额')),
      `利润率 ${pct(S['经营贡献利润率'])}`];
    const formulaItems = [[profitTitle, S['含推广经营贡献利润_分'], money, profitNotes.at(-1)],
      ['已核算销售额', accounted, money, profitNotes[0]],
      ...costs.map(([label, field], i) => [label, S[field], money, profitNotes[i + 1]])];
    $('#profitFormula').innerHTML = formulaItems.map((_, i) =>
      `<div class="formula-unit${i === 0 ? ' formula-result' : ''}">` +
      (i > 0 ? `<span class="formula-operator">${i === 1 ? '=' : '-'}</span>` : '') +
      `<div id="formulaTerm${i}" class="formula-term"></div></div>`
    ).join('');
    formulaItems.forEach((item, i) => values('#formulaTerm' + i, [item]));
    $('#formulaTerm0 .value').classList.add('primary');
    values('#profitNet', [['已核算净销售额', net, money,
      '已核算销售额减订单批次退款；仅作为费用占比基数，不重复扣减']]);
    $('#summaryMetrics').innerHTML =
      '<section><h3>退款与关闭</h3><div id="refundMetrics" class="value-grid"></div></section>' +
      '<section><h3>推广归因</h3><div id="promotionMetrics" class="value-grid"></div></section>';
    values('#refundMetrics', [['期间退款完结金额', S['期间退款完结金额_分'], money,
      '按退款完结日期统计，不与订单批次退款叠加'],
      ['退款订单率', S['退款订单率'], pct, '主订单口径'],
      ['付款后关闭率', S['付款后关闭率'], pct, '主订单口径'],
      ['关闭已发货率', S['关闭已发货率'], pct, '主订单口径']]);
    values('#promotionMetrics', [['推广花费', S['推广花费_分'], money,
      share(S['推广花费_分'], net, '已核算净销售额')],
      ['推广归因成交金额', S['推广归因成交金额_分'], money,
        `推广投产比 ${fieldText('推广投产比', S['推广投产比'])}；不计入订单销售额`]]);
    const incompleteLinks = DATA.links.filter(r => r['核算状态'] !== '已核算').length;
    $('#coverageValues').innerHTML = '<div id="coverageHealth" class="coverage-health"></div>' +
      '<div id="coverageDistribution" class="value-grid"></div>';
    values('#coverageHealth', [['总链接', DATA.links.length, number],
      ['已核算链接', DATA.links.length - incompleteLinks, number, '成本与运费完整'],
      ['成本/运费缺失链接', incompleteLinks, number, '优先补齐后重新生成报告']]);
    if (incompleteLinks) $('#coverageHealth .value:last-child').classList.add('attention');
    values('#coverageDistribution', [
      ...['订单+推广', '仅订单', '仅推广'].map(label =>
        [label, DATA.links.filter(row => row['数据覆盖'] === label).length, number]),
      ['已核算亏损链接', DATA.links.filter(r => r['核算状态'] === '已核算' &&
        r['含推广经营贡献利润_分'] < 0).length, number]]);
    const start = S['已核算销售额_分'];
    const result = S['含推广经营贡献利润_分'];
    const complete = finite(start) && finite(result) && costs.every(([, field]) => finite(S[field]));
    let remaining = start;
    const segments = [[0, 0, start / 100, start / 100]];
    costs.forEach(([, field], i) => {
      const next = remaining - S[field];
      segments.push([i + 1, remaining / 100, next / 100, -S[field] / 100]);
      remaining = next;
    });
    segments.push([costs.length + 1, 0, result / 100, result / 100]);
    const valid = complete && remaining === result;
    $('#profitChartEmpty').textContent = complete
      ? '利润链路与核算结果不一致，请核对 Excel 底稿。' : '利润链路数据不完整，暂无可绘制的瀑布图。';
    setChart('profitChart', {
      tooltip: {trigger: 'item', renderMode: 'richText', confine: true,
        formatter: p => `${p.name}\n${money(p.value[3] * 100)}\n${profitNotes[p.dataIndex]}`},
      xAxis: {type: 'category', data: ['已核算销售额', ...costs.map(c => c[0]), '经营贡献利润'],
        axisLabel: {interval: 0, rotate: 25, fontSize: 11}},
      yAxis: {type: 'value', name: '金额（元）', min: v => Math.min(0, v.min)},
      series: [{type: 'custom', encode: {x: 0, y: [1, 2]}, data: segments,
        renderItem: (params, api) => {
          const x = api.value(0), from = api.coord([x, api.value(1)]), to = api.coord([x, api.value(2)]);
          const width = api.size([1, 0])[0] * .58;
          const shape = echarts.graphic.clipRectByRect({x: from[0] - width / 2,
            y: Math.min(from[1], to[1]), width, height: Math.max(1, Math.abs(to[1] - from[1]))},
          params.coordSys);
          return shape && {type: 'rect', shape, style: {fill:
            x === 0 || x === costs.length + 1 ? (api.value(3) < 0 ? '#b42318' : '#14634f') : '#925000'}};
        }}]
    }, !valid);
  };

  const renderProductMix = (id, noteId, source, field, profit) => {
    // These groups summarize existing amounts for display only; they do not calculate profits.
    const productName = row => String(row['产品名称'] || '未归类');
    const palette = ['#14634f', '#38836e', '#527c91', '#708c9c', '#8caaa1', '#b1c5bf', '#d0dad7'];
    const compareNames = (a, b) => productName(a).localeCompare(productName(b));
    const rows = source.filter(row => finite(row[field]) && row[field] > 0 &&
      (!profit || row['经营贡献利润率状态'] === '已核算'))
      .sort((a, b) => b[field] - a[field] || compareNames(a, b));
    const total = rows.reduce((sum, row) => sum + row[field], 0);
    const items = rows.slice(0, 6).map(row => ({name: productName(row), value: row[field] / 100}));
    if (rows.length > 6) items.push({name: `其余 ${rows.length - 6} 个产品`,
      value: rows.slice(6).reduce((sum, row) => sum + row[field], 0) / 100});
    $('#' + noteId).textContent = profit
      ? `核算完整产品正利润合计 ${money(total)}；排除 ${source.length - rows.length} 个待核算、非盈利或数值缺失产品。不是店铺净利润占比。`
      : `正销售额合计 ${money(total)}；排除 ${source.length - rows.length} 个非正销售额或数值缺失产品。`;
    setChart(id, {
      color: palette,
      title: {text: profit ? '盈利贡献' : '销售结构', left: 'center', top: '35%',
        textStyle: {fontSize: 15, fontWeight: 500, color: '#1d2b32'}},
      legend: {type: 'scroll', selectedMode: false, bottom: 0, left: 'center',
        textStyle: {color: '#55656f'},
        formatter: name => {
          const item = items.find(row => row.name === name);
          return `${name}  ${pct(item.value * 100 / total)}`;
        }},
      tooltip: {trigger: 'item', renderMode: 'richText', confine: true,
        formatter: p => `${p.name}\n${money(p.value * 100)}\n占比 ${pct(p.value * 100 / total)}`},
      series: [{type: 'pie', radius: ['44%', '66%'], center: ['50%', '40%'],
        avoidLabelOverlap: true,
        label: {show: true, position: 'inside', formatter: p =>
          p.value * 100 / total >= .08 ? pct(p.value * 100 / total) : '', fontSize: 11, color: '#1d2b32',
          backgroundColor: '#fdfefe', padding: [2, 4], borderRadius: 4},
        itemStyle: {borderColor: '#fdfefe', borderWidth: 2},
        emphasis: {scale: false}, data: items.map(item => ({...item,
          label: {show: item.value * 100 / total >= .08}}))}]
    }, !rows.length);
  };
  const renderOverviewInsights = (costs, net) => {
    renderProductMix('salesMixChart', 'salesMixNote', DATA.products, '销售额_分', false);
    renderProductMix('profitMixChart', 'profitMixNote', DATA.products, '含推广经营贡献利润_分', true);
    const productName = row => String(row['产品名称'] || '未归类');
    const compareNames = (a, b) => productName(a).localeCompare(productName(b));
    const completeProducts = DATA.products.filter(row =>
      row['经营贡献利润率状态'] === '已核算' && finite(row['含推广经营贡献利润_分']));
    const ranked = [...completeProducts].sort((a, b) =>
      Math.abs(b['含推广经营贡献利润_分']) - Math.abs(a['含推广经营贡献利润_分']) ||
      compareNames(a, b)).slice(0, 10);
    $('#productProfitNote').textContent = `核算完整产品按利润绝对值展示前 10；排除 ${DATA.products.length - completeProducts.length} 个待核算或利润缺失产品。绿色盈利，红色亏损。`;
    const barOption = (rows, label) => ({
      grid: {left: 8, right: 90, top: 20, bottom: 32, containLabel: true},
      tooltip: {trigger: 'item', renderMode: 'richText', confine: true,
        formatter: p => `${p.name}\n${label} ${money(p.value * 100)}${p.data.note ? '\n' + p.data.note : ''}`},
      xAxis: {type: 'value', name: '元', axisLabel: {fontSize: 11}},
      yAxis: {type: 'category', inverse: true, data: rows.map(row => row.name),
        axisLabel: {width: 90, overflow: 'truncate', fontSize: 11}},
      series: [{type: 'bar', barMaxWidth: 22,
        label: {show: true, position: 'right', fontSize: 11, formatter: p => money(p.value * 100)},
        data: rows.map(row => ({...row, itemStyle: {color: row.value < 0 ? '#b42318' : '#14634f'}}))}]
    });
    setChart('productProfitChart', barOption(ranked.map(row => ({name: productName(row),
      value: row['含推广经营贡献利润_分'] / 100})), profitTitle), !ranked.length);
    const knownCosts = costs.filter(([, field]) => finite(S[field]));
    const costRows = knownCosts.map(([name, field]) => ({name, value: S[field] / 100,
      note: share(S[field], net, '已核算净销售额')})).sort((a, b) => b.value - a.value);
    $('#costNote').textContent = `货品、物流、刷单、平台、税赋、关闭损失与推广分项展示；缺失 ${costs.length - knownCosts.length} 项。平台扣点与税赋为估算值。`;
    setChart('costChart', barOption(costRows, '费用'), !costRows.some(row => row.value !== 0));
  };

  const dailyGroups = {
    sales: ['销售表现', [['销售额_分', '销售额'], ['真实销售额_分', '真实销售额'],
      ['刷单金额_分', '刷单金额']]],
    profit: ['经营利润', [['含推广经营贡献利润_分', profitTitle],
      ['关闭已发货损失_分', '关闭已发货损失']]],
    promotion: ['推广表现', [['推广花费_分', '推广花费'],
      ['推广归因成交金额_分', '推广归因成交金额']]],
    orders: ['订单与退款', [['已付款主订单数', '主订单数', 'bar'],
      ['订单批次成功退款_分', '订单批次退款'], ['期间退款完结金额_分', '期间退款完结']]]
  };
  const dailyRows = [...DATA.daily].sort((a, b) => String(a['日期']).localeCompare(String(b['日期'])));
  let dailyKey = 'sales', dailyIndex = 0;
  const dailyReadout = index => {
    if (!dailyRows.length) return;
    dailyIndex = Math.max(0, Math.min(dailyRows.length - 1, index));
    const row = dailyRows[dailyIndex];
    $('#dailyChartReadout').textContent = row['日期'] + '　' + dailyGroups[dailyKey][1]
      .map(([field, label]) => `${label} ${fieldText(field, row[field])}`).join('　');
  };
  const renderDaily = () => {
    const [title, fields] = dailyGroups[dailyKey];
    $('#dailyChartTitle').textContent = title;
    $('#dailyChartPeriod').textContent = dailyRows.length
      ? `${dailyRows[0]['日期']} 至 ${dailyRows.at(-1)['日期']}` : '暂无数据';
    document.querySelectorAll('[data-daily-chart]').forEach(button => {
      const active = button.dataset.dailyChart === dailyKey;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const instance = setChart('dailyChart', {
      legend: {top: 0, type: 'scroll'},
      xAxis: {type: 'category', data: dailyRows.map(r => r['日期'])},
      yAxis: dailyKey === 'orders'
        ? [{type: 'value', name: '订单（单）', minInterval: 1}, {type: 'value', name: '退款金额（元）'}]
        : {type: 'value', name: '金额（元）'},
      dataZoom: [{type: 'inside'}, {type: 'slider', height: 18, bottom: 0}],
      color: ['#14634f', '#527c91', '#925000'],
      series: fields.map(([field, label, type]) => ({name: label, type: type || 'line',
        yAxisIndex: dailyKey === 'orders' && field.endsWith('_分') ? 1 : 0,
        connectNulls: false, showSymbol: true, symbolSize: 6,
        data: dailyRows.map(r => finite(r[field]) ? r[field] / (field.endsWith('_分') ? 100 : 1) : null)}))
    }, !dailyRows.length);
    if (instance && !instance.__readoutBound) {
      instance.on('updateAxisPointer', event => {
        const index = event.axesInfo?.find(axis => axis.axisDim === 'x')?.value;
        if (Number.isInteger(index)) dailyReadout(index);
      });
      instance.__readoutBound = true;
    }
    dailyReadout(dailyRows.length - 1);
  };
  $('[data-daily-chart="sales"]').parentElement.addEventListener('click', event => {
    if (event.target.dataset.dailyChart) { dailyKey = event.target.dataset.dailyChart; renderDaily(); }
  });
  $('#dailyChart').addEventListener('keydown', event => {
    const actions = {ArrowLeft: dailyIndex - 1, ArrowRight: dailyIndex + 1, Home: 0,
      End: dailyRows.length - 1};
    if (event.key in actions) { event.preventDefault(); dailyReadout(actions[event.key]); }
  });

  const coreMoney = ['销售额_分', '订单批次成功退款_分', '货品成本_分', '运费_分', '刷单成本_分',
    '平台扣点_分', '综合税赋_分', '关闭已发货损失_分', '推广花费_分', '含推广经营贡献利润_分'];
  const overview = {
    daily: ['日期', '销售额_分', '真实销售额_分', '订单批次成功退款_分', '推广花费_分',
      '含推广经营贡献利润_分', '经营贡献利润率', '核算覆盖率'],
    products: ['产品名称', '商品链接数', '销售额_分', '真实销售额_分', '订单批次成功退款_分',
      '退款率', '推广花费_分', '推广投产比', '含推广经营贡献利润_分',
      '经营贡献利润率', '经营贡献利润率状态'],
    links: ['商品ID', 'SABC等级', '销售额_分', '退款率', '推广花费_分', '含推广经营贡献利润_分',
      '经营贡献利润率', '核算状态', '运营动作']
  };
  const identity = {daily: '日期', products: '产品名称', links: '商品ID'};
  const statusField = {daily: '核算覆盖率', products: '经营贡献利润率状态', links: '核算状态'};
  const taobaoLink = value => {
    const link = document.createElement('a');
    link.textContent = String(value);
    link.href = 'https://item.taobao.com/item.htm?id=' + encodeURIComponent(value);
    link.target = '_blank'; link.rel = 'noopener noreferrer';
    link.addEventListener('click', event => event.stopPropagation());
    return link;
  };
  const extraFields = {
    daily: ['日期', ...coreMoney, ...overview.daily],
    products: ['产品名称', ...coreMoney, ...overview.products, 'SKU数', '商品链接数'],
    links: ['商品ID', '商品标题', '产品名称', ...coreMoney, ...overview.links, '刷单金额_分']
  };
  const detail = $('#rowDetail');
  const openDetail = (view, row) => {
    $('#detailTitle').textContent = `${view === 'links' ? '链接' : view === 'products' ? '产品' : '每日'}完整明细`;
    $('#detailFields').replaceChildren();
    for (const [field, value] of Object.entries(row)) {
      const block = document.createElement('div'), title = document.createElement('dt');
      const text = document.createElement('dd');
      title.textContent = fieldTitle(field);
      text.textContent = fieldText(field, value, row);
      if (field === '商品ID') text.replaceChildren(taobaoLink(value));
      block.append(title, text); $('#detailFields').append(block);
    }
    detail.showModal();
  };
  $('#closeDetail').addEventListener('click', () => detail.close());
  document.addEventListener('pointerdown', event => {
    document.querySelectorAll('.column-picker[open]').forEach(picker => {
      if (!picker.contains(event.target)) picker.open = false;
    });
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') document.querySelectorAll('.column-picker[open]')
      .forEach(picker => { picker.open = false; });
  });
  const datasetFor = view => view === 'daily' ? dailyRows : DATA[view];
  const buildGrid = view => {
    if (grids.has(view)) { grids.get(view).redraw(true); return; }
    const rows = datasetFor(view);
    const fields = [...new Set([...overview[view], ...extraFields[view],
      ...rows.flatMap(row => Object.keys(row))])];
    const formatter = field => cell => {
      const node = document.createElement('span'), row = cell.getRow().getData();
      if (field === '商品ID' && cell.getValue() != null) return taobaoLink(cell.getValue());
      node.textContent = fieldText(field, cell.getValue(), row);
      if (cell.getValue() < 0 && (field.endsWith('_分') || ratioFields.has(field))) {
        node.className = 'negative';
      }
      return node;
    };
    const grid = new Tabulator('#' + view + 'Grid', {
      data: rows, layout: 'fitColumns', height: 540,
      pagination: true, paginationSize: 30, paginationSizeSelector: [30, 60, 100],
      placeholder: view === 'links' ? '没有匹配的链接，请调整或重置筛选条件。'
        : view === 'products' ? '本期暂无产品数据或没有匹配产品' : '本期暂无每日数据',
      locale: 'zh-cn', langs: {'zh-cn': {pagination: {page_size: '每页', first: '首页',
        first_title: '首页', last: '末页', last_title: '末页', prev: '上一页', prev_title: '上一页',
        next: '下一页', next_title: '下一页', all: '全部'}}},
      initialSort: [{column: view === 'daily' ? '日期' : '含推广经营贡献利润_分',
        dir: view === 'daily' ? 'asc' : 'desc'}],
      columns: [...fields.map(field => ({title: fieldTitle(field), field,
        visible: overview[view].includes(field), formatter: formatter(field),
        sorter: field.endsWith('_分') || ratioFields.has(field) || rows.some(r =>
          typeof r[field] === 'number') ? 'number' : 'string',
        minWidth: field === '商品ID' || field === '运营动作' ? 145
          : field.endsWith('_分') ? 110 : 92,
        widthGrow: field === identity[view] || field === '商品标题' || field === '运营动作' ? 2 : 1,
        headerWordWrap: true, hozAlign: field.endsWith('_分') || ratioFields.has(field) ? 'right' : 'left',
        cssClass: ['产品名称', '商品标题', '运营动作', '核算状态', '经营贡献利润率状态']
          .includes(field) ? 'wrap' : '', variableHeight: true})),
      {title: '详情', field: '_detail', width: 65, headerSort: false,
        formatter: cell => {
          const button = document.createElement('button');
          button.textContent = '详情'; button.type = 'button';
          button.addEventListener('click', event => {
            event.stopPropagation(); openDetail(view, cell.getRow().getData());
          });
          return button;
        }}]
    });
    grids.set(view, grid);
    grid.on('rowClick', (_, row) => openDetail(view, row.getData()));
    grid.on('tableBuilt', () => {
      readyGrids.add(view);
      observer.observe($('#' + view + 'Grid'));
      if (view === 'links') filterLinks();
      if (view === 'products') filterProducts();
    });
    const container = $('#' + view + 'Columns');
    for (const field of fields) {
      const label = document.createElement('label'), input = document.createElement('input');
      input.type = 'checkbox'; input.value = field; input.checked = overview[view].includes(field);
      if (field === identity[view] || field === statusField[view]) input.disabled = true;
      input.addEventListener('change', () => {
        input.checked ? grid.showColumn(field) : grid.hideColumn(field);
        document.querySelectorAll(`#${view} [data-preset]`).forEach(b => {
          b.classList.remove('active'); b.setAttribute('aria-pressed', 'false');
        });
      });
      label.append(input, document.createTextNode(fieldTitle(field))); container.append(label);
    }
    document.querySelectorAll(`#${view} [data-preset]`).forEach(button => {
      button.addEventListener('click', () => {
        const selected = button.dataset.preset;
        const visible = selected === 'all' ? fields : selected === 'overview' ? overview[view]
          : [identity[view], ...coreMoney, view === 'products' ? '经营贡献利润率状态'
            : view === 'links' ? '核算状态' : '核算覆盖率'];
        for (const field of fields) visible.includes(field) ? grid.showColumn(field) : grid.hideColumn(field);
        container.querySelectorAll('input').forEach(input => { input.checked = visible.includes(input.value); });
        document.querySelectorAll(`#${view} [data-preset]`).forEach(b => {
          b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button));
        });
      });
    });
  };

  let productExact = '', linkExact = '', rankedProducts = [];
  const productMatch = row => (!productExact || row['产品名称'] === productExact) &&
    String(row['产品名称'] || '').toLowerCase().includes($('#productSearch').value.toLowerCase());
  const filterProducts = () => {
    if (readyGrids.has('products')) grids.get('products').setFilter(productMatch);
    const rows = DATA.products.filter(productMatch);
    $('#productCount').textContent = `匹配 ${rows.length} / ${DATA.products.length} 个产品`;
    renderProductInsights(rows);
  };
  const renderProductInsights = rows => {
    $('#productInsightNote').textContent = `当前筛选 ${rows.length} 个产品；销售/退款、推广和盈利贡献图随筛选更新。`;
    for (const [id, fields, names, colors] of [
      ['productSalesChart', ['销售额_分', '订单批次成功退款_分'], ['销售额', '订单批次退款'],
        ['#14634f', '#b42318']],
      ['productPromotionChart', ['推广花费_分', '推广归因成交金额_分'], ['推广花费', '推广归因成交金额'],
        ['#14634f', '#527c91']]
    ]) {
      const ranked = rows.filter(row => fields.some(field => finite(row[field])))
        .sort((a, b) => (finite(b[fields[0]]) ? b[fields[0]] : -Infinity) -
          (finite(a[fields[0]]) ? a[fields[0]] : -Infinity) ||
          String(a['产品名称']).localeCompare(String(b['产品名称']))).slice(0, 10);
      setChart(id, {
        color: colors,
        legend: {top: 0, type: 'scroll'},
        grid: {left: 8, right: 30, top: 40, bottom: 24, containLabel: true},
        xAxis: {type: 'value', name: '元'},
        yAxis: {type: 'category', inverse: true, data: ranked.map(row => row['产品名称']),
          axisLabel: {width: 90, overflow: 'truncate', fontSize: 11}},
        tooltip: {trigger: 'axis', renderMode: 'richText', confine: true,
          formatter: params => {
            const row = ranked[params[0]?.dataIndex];
            return row ? `${row['产品名称']}\n` + fields.map((field, i) =>
              `${names[i]} ${money(row[field])}`).join('\n') : '';
          }},
        series: fields.map((field, i) => ({name: names[i], type: 'bar', barMaxWidth: 12,
          data: ranked.map(row => finite(row[field]) ? row[field] / 100 : null)}))
      }, !ranked.length);
    }
    renderProductMix('productShareChart', 'productShareNote', rows, '含推广经营贡献利润_分', true);
  };
  const renderProducts = () => {
    const key = $('#productRank').value === 'sales' ? '销售额_分' : '含推广经营贡献利润_分';
    rankedProducts = DATA.products.filter(r => finite(r[key]) &&
      (key === '销售额_分' || r['经营贡献利润率状态'] === '已核算'))
      .sort((a, b) => b[key] - a[key] ||
        String(a['产品名称']).localeCompare(String(b['产品名称']))).slice(0, 10);
    const profitValues = rankedProducts.map(row => row['经营贡献利润率状态'] === '已核算' &&
      finite(row['含推广经营贡献利润_分']) ? row['含推广经营贡献利润_分'] : null);
    const names = rankedProducts.map(row => row['产品名称']);
    $('#productRankNote').textContent = '前 10 个产品：左侧利润（绿色盈利、红色亏损），右侧销售额。' +
      '利润柱长按绝对值；左右独立刻度，不按跨轴柱长比较金额。未完整核算利润和负销售额留空，点击条形筛选明细。';
    setChart('productChart', {
      grid: [{left: 90, right: '50%', top: 15, bottom: 40,
        containLabel: false, outerBoundsMode: 'none'},
        {left: '50%', right: 24, top: 15, bottom: 40,
          containLabel: false, outerBoundsMode: 'none'}],
      tooltip: {trigger: 'item', renderMode: 'richText', confine: true,
        formatter: p => {
          const row = rankedProducts[p.dataIndex];
          return `${row['产品名称']}\n经营贡献利润 ${profitValues[p.dataIndex] == null
            ? row['经营贡献利润率状态'] || '暂无' : money(profitValues[p.dataIndex])}` +
            `\n销售额 ${money(row['销售额_分'])}`;
        }},
      xAxis: [
        {type: 'value', gridIndex: 0, inverse: true, min: 0, name: '利润（元，绝对值）',
          nameLocation: 'middle', nameGap: 26,
          axisLabel: {fontSize: 10, formatter: value => value === 0 ? '' : number(value)},
          max: value => value.max ? value.max * 1.35 : 1},
        {type: 'value', gridIndex: 1, min: 0, name: '销售额（元）',
          nameLocation: 'middle', nameGap: 26, axisLabel: {fontSize: 10},
          max: value => value.max ? value.max * 1.35 : 1}
      ],
      yAxis: [
        {type: 'category', gridIndex: 0, inverse: true, position: 'left', data: names,
          axisLine: {onZero: false},
          axisLabel: {width: 70, overflow: 'truncate', fontSize: 11}, axisTick: {show: false}},
        {type: 'category', gridIndex: 1, inverse: true, data: names, show: false}
      ],
      series: [
        {name: '经营贡献利润', type: 'bar', xAxisIndex: 0, yAxisIndex: 0, barMaxWidth: 20,
          label: {show: true, position: 'left', fontSize: 10,
            formatter: p => profitValues[p.dataIndex] == null ? '' : money(profitValues[p.dataIndex])},
          data: profitValues.map(value => ({value: value == null ? null : Math.abs(value) / 100,
            itemStyle: {color: value < 0 ? '#b42318' : '#14634f'}}))},
        {name: '销售额', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, barMaxWidth: 20,
          label: {show: true, position: 'right', fontSize: 10,
            formatter: p => p.value == null ? '' : money(rankedProducts[p.dataIndex]['销售额_分'])},
          data: rankedProducts.map(row => ({value: finite(row['销售额_分']) && row['销售额_分'] >= 0
            ? row['销售额_分'] / 100 : null, itemStyle: {color: '#527c91'}}))}
      ]
    }, !rankedProducts.length, event => {
      productExact = rankedProducts[event.dataIndex]?.['产品名称'] || '';
      $('#productSearch').value = productExact; filterProducts();
    });
  };
  $('#productRank').addEventListener('change', renderProducts);
  $('#productSearch').addEventListener('input', () => { productExact = ''; filterProducts(); });
  $('#resetProducts').addEventListener('click', () => {
    productExact = ''; $('#productSearch').value = ''; filterProducts();
  });
  const linkControls = ['search', 'productFilter', 'sabc', 'profit', 'coverage', 'accounting'];
  for (const [id, field] of [['productFilter', '产品名称'], ['sabc', 'SABC等级']]) {
    [...new Set(DATA.links.map(row => row[field]).filter(Boolean))].sort()
      .forEach(value => $('#' + id).add(new Option(value, value)));
  }
  const linkMatch = row => {
    const search = $('#search').value.toLowerCase();
    return (!linkExact || row['商品ID'] === linkExact) &&
      `${row['商品ID']} ${row['商品标题']}`.toLowerCase().includes(search) &&
      [['productFilter', '产品名称'], ['sabc', 'SABC等级'], ['profit', '盈利状态'],
        ['coverage', '数据覆盖'], ['accounting', '核算状态']].every(([id, field]) =>
        !$('#' + id).value || $('#' + id).value === row[field]);
  };
  const linkMetrics = {
    profit: ['含推广经营贡献利润_分', profitTitle, '仅包含核算完整链接。'],
    sales: ['销售额_分', '销售额', '按订单付款日期归属。'],
    spend: ['推广花费_分', '推广花费', '推广报表花费口径。'],
    spendShare: ['推广费率', '推广占比', '推广花费 ÷ 已核算净销售额。'],
    refund: ['订单批次成功退款_分', '退款金额', '订单批次成功退款口径。'],
    refundRate: ['退款率', '退款率', '订单批次成功退款 ÷ 销售额。']
  };
  const renderLinkRanks = rows => {
    const key = $('#linkRank').value;
    const [field, label, note] = linkMetrics[key];
    const ratio = ratioFields.has(field);
    const scale = ratio ? .01 : 100;
    const formatValue = value => ratio ? pct(value / 100) : money(value * 100);
    const valid = rows.filter(row => finite(row[field]) &&
      (key !== 'profit' || row['核算状态'] === '已核算'));
    $('#linkRankNote').textContent = `${label}：${note}当前排除 ${rows.length - valid.length} 个核算不完整或指标缺失链接。` +
      `有效链接 ${valid.length} 个，不足 20 个时双榜可能重叠。点击条形筛选链接明细。`;
    for (const [id, direction] of [['linkTopChart', -1], ['linkBottomChart', 1]]) {
      const ranked = [...valid].sort((a, b) => (a[field] - b[field]) * direction ||
        String(a['商品ID']).localeCompare(String(b['商品ID']))).slice(0, 10);
      setChart(id, {
        grid: {left: 8, right: 90, top: 15, bottom: 32, containLabel: true},
        xAxis: {type: 'value', name: ratio ? '%' : '元'},
        yAxis: {type: 'category', inverse: true, data: ranked.map(row => String(row['商品ID'])),
          axisLabel: {fontSize: 11}},
        tooltip: {trigger: 'item', renderMode: 'richText', confine: true,
          formatter: p => `${p.data.linkId}\n${p.data.title}\n${label} ${formatValue(p.value)}` +
            `\n核算状态 ${p.data.status}`},
        series: [{type: 'bar', barMaxWidth: 24,
          label: {show: true, position: 'right', fontSize: 11,
            formatter: p => formatValue(p.value)},
          data: ranked.map(row => ({value: row[field] / scale, linkId: row['商品ID'],
            title: row['商品标题'] || '', status: row['核算状态'] || '暂无',
            itemStyle: {color: row[field] < 0 ? '#b42318' : '#14634f'}}))}]
      }, !ranked.length, event => {
        linkExact = event.data.linkId; $('#search').value = linkExact; filterLinks();
      });
    }
  };
  const filterLinks = () => {
    if (readyGrids.has('links')) grids.get('links').setFilter(linkMatch);
    const rows = DATA.links.filter(linkMatch);
    $('#linkCount').textContent = `匹配 ${rows.length} / ${DATA.links.length} 个链接`;
    renderLinkRanks(rows);
  };
  $('#linkRank').addEventListener('change', () => renderLinkRanks(DATA.links.filter(linkMatch)));
  linkControls.forEach(id => $('#' + id).addEventListener('input', () => { linkExact = ''; filterLinks(); }));
  $('#sort').addEventListener('change', () => grids.get('links')?.setSort($('#sort').value, 'desc'));
  $('#resetFilters').addEventListener('click', () => {
    linkExact = ''; linkControls.forEach(id => { $('#' + id).value = ''; });
    $('#sort').value = '含推广经营贡献利润_分';
    grids.get('links')?.setSort($('#sort').value, 'desc'); filterLinks();
  });
  const activate = view => {
    document.querySelectorAll('nav [data-view]').forEach(button => {
      const active = button.dataset.view === view;
      button.classList.toggle('active', active); button.setAttribute('aria-pressed', String(active));
    });
    document.querySelectorAll('.view').forEach(node => { node.hidden = node.id !== view; });
    try {
      if (view === 'overview') { charts.get('profitChart')?.resize(); return; }
      buildGrid(view);
      if (view === 'daily') renderDaily();
      if (view === 'products') renderProducts();
      if (view === 'links') filterLinks();
    } catch (error) { showError(error); }
  };
  document.querySelectorAll('nav [data-view]').forEach(b =>
    b.addEventListener('click', () => activate(b.dataset.view)));
  try { buildOverview(); } catch (error) { showError(error); }
})();
