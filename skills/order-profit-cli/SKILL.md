---
name: order-profit-cli
description: "Use the bundled Windows CLI to validate and calculate Tmall or Taobao order profit from order XLSX, cost XLSX, freight XLS/XLSX, after-sales XLSX, promotion CSV, and supplement XLSX files. Trigger for 电商订单利润核算、天猫/淘宝经营复盘、成本运费待补、退款与推广利润分析、生成订单成本利润分析.xlsx or 店铺经营复盘.html."
---

# 订单利润核算 CLI

使用 `scripts/order-profit.ps1` 调用技能包内置的 Windows CLI，不安装 Python 依赖。

## 工作流

1. 检查输入文件表头，匹配订单、成本、运费、售后、推广和人工补充文件。
2. 平台必须使用用户明确说明的 `tmall` 或 `taobao`；不得仅凭文件名猜测。
3. 日期使用用户要求的闭区间 `YYYY-MM-DD`。
4. 直接运行 `run`；程序自身会执行输入校验和勾稽。
5. 读取输出目录的 `manifest.json`，报告 `FINAL`/`PROVISIONAL`、待补行数、利润和利润率。
6. `PROVISIONAL` 时只补有明确依据的数据，不猜成本；确认后用 `--supplements` 重算。

## PowerShell 调用

执行前统一设置 UTF-8：

```powershell
$utf8 = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = $utf8; [Console]::InputEncoding = $utf8; [Console]::OutputEncoding = $utf8; $env:PYTHONIOENCODING = 'utf-8';
```

命令模板：

```powershell
& '<skill-dir>\scripts\order-profit.ps1' run `
  --orders '订单.xlsx' `
  --costs '成本编码表.xlsx' `
  --freight '运费.xls' `
  --after-sales '售后.xlsx' `
  --promotion '推广.csv' `
  --supplements '待补成本运费_已补.xlsx' `
  --start-date 2026-08-01 `
  --end-date 2026-08-15 `
  --platform tmall `
  --output-dir '核算结果' `
  --overwrite-existing `
  --recalculation auto
```

仅传入实际存在的可选文件。人工补充表不要放在将被覆盖的输出目录内；先复制到同级输入目录再重算。

## 输出

- `订单成本利润分析.xlsx`
- `店铺经营复盘.html`
- `manifest.json`
- `待补成本运费.xlsx`：仅 `PROVISIONAL` 时生成

刷单按实收金额计入刷单成本，不需要补货品成本或运费。
