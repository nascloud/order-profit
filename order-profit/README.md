# 订单利润核算程序

本目录实现订单、成本、退款、运费、平台扣点、综合税赋与推广费用一体化核算，并输出 Excel 核算底稿和面向运营人员的 HTML 店铺/链接复盘页。

## 当前能力

P1～P12 已实现：

- Excel/CSV 输入契约、编码回退、SHA-256 和源行审计；
- ID、日期、数量、金额的严格标准化；
- 订单清洗、期间过滤和六个互斥分区；
- 人工补充、成本与实际/标准运费优先级；
- 有效退款、平台扣点、综合税赋、正常利润和关闭已发货损失；
- 售后主订单级复核、推广每日/链接汇总、SKU/链接/店铺分析；
- 强制勾稽与 `FAILED / PROVISIONAL / FINAL`；
- Excel 报告、自包含 HTML 运营复盘、原子输出事务；
- Tkinter 本地桌面启动器。

## 安装

建议使用 Python 3.11～3.14。

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
```

Windows 桌面界面使用 Python 标准库 Tkinter，无额外 Web 服务。

## 桌面启动器

安装项目后运行：

```bash
order-profit-gui
```

未安装为命令时可双击：

```text
启动订单利润核算.bat
```

或运行：

```bash
python -m order_profit.desktop
```

界面支持选择订单、成本、运费、售后、推广和人工补充文件，设置日期、平台、覆盖策略与输出目录。运算在后台线程执行，界面不会在读取大文件时卡死。

## 命令行

### 输入、内存核算与勾稽

```bash
python -m order_profit validate-inputs \
  --orders ExportOrderList.xlsx \
  --costs 成本编码表.xlsx \
  --freight 运费表.xls \
  --after-sales 售后表.xlsx \
  --promotion 商品推广报表.csv \
  --supplements 成本运费补充.xlsx \
  --start-date 2026-08-01 \
  --end-date 2026-08-07 \
  --platform tmall \
  --output-dir output/validation
```

输出 `validation-manifest.json`，包含订单分区、成本/运费、经营汇总和逐项勾稽结果。

### 生成正式报告

```bash
python -m order_profit run \
  --orders ExportOrderList.xlsx \
  --costs 成本编码表.xlsx \
  --freight 运费表.xls \
  --after-sales 售后表.xlsx \
  --promotion 商品推广报表.csv \
  --start-date 2026-08-01 \
  --end-date 2026-08-07 \
  --platform tmall \
  --output-dir output/2026-08-01_2026-08-07
```

输出：

```text
订单成本利润分析.xlsx
店铺经营复盘.html
manifest.json
```

报告先在同一文件系统的临时目录生成并校验，再原子替换目标目录。失败不会覆盖上一份成功报告。

常用选项：

- `--platform tmall|taobao`：必需；程序不猜平台。
- `--overwrite-existing`：人工补充允许覆盖订单已有成本或运费。
- `--require-complete`：存在成本/运费缺失时返回非零且不发布正式报告。
- `--timezone Asia/Shanghai`：配置业务时区。

## 报告状态

- `FINAL`：有效正常及关闭订单成本/运费完整，全部勾稽通过。
- `PROVISIONAL`：流水线及勾稽通过，但仍有成本/运费缺失；HTML 必须按暂算使用。
- `FAILED`：输入、唯一性、标准化、核算、勾稽或输出失败。

## 当前真实样本注意事项

根目录 `0.1成本编码表.xlsx` 的 Excel 第 173 行存在有金额但编码为空的孤立记录：

```text
编码：空
成本：12.52
运费：空
```

程序会返回 `INPUT_KEY_EMPTY`。需要补齐编码和运费，或确认该行无效后删除，才能加载这份成本表生成完整 `FINAL` 报告。程序不会猜测归属或静默忽略。

## 目录

```text
order-profit/
├─ pyproject.toml
├─ src/order_profit/   # 应用代码
├─ tests/              # 自动化测试
├─ docs/               # 技术决策与审查报告
├─ data/raw/           # 本地输入数据，不提交 Git
├─ data/supplements/   # 本地人工补充数据，不提交 Git
└─ output/             # 生成结果，不提交 Git
```

## 设计原则

- 金额计算以整数“分”为权威口径，不使用二进制浮点数核算。
- 未知成本和运费保持缺失，不以 0 代替。
- 原始输入只读，所有排除、覆盖和计算保留审计字段。
- Python `PipelineResult` 是 Excel 和 HTML 的共同事实来源。
- 推广归因成交金额只用于投产分析，不重复计入订单销售额。
- HTML 动作标签只作运营复盘提示，不自动修改推广计划。
