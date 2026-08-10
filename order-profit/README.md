# 订单利润核算程序

本目录用于实现《订单利润核算标准化程序开发文档》定义的订单、成本、退款、运费与推广费用一体化核算流程。

## 当前状态

P1～P3 已实现：运行配置与结构化错误、输入文件契约、SHA-256/manifest、ID/日期/数量/金额标准化及表内冲突校验。P4 之后的清洗、成本运费匹配、利润、汇总和报表尚未实现，因此 `run` 子命令会主动拒绝运行，防止误交付。

可先执行输入校验：

```bash
python -m order_profit validate-inputs \
  --orders ExportOrderList.xlsx \
  --start-date 2026-08-01 \
  --end-date 2026-08-07 \
  --platform tmall \
  --output-dir output
```

成功后生成 `validation-manifest.json`；该状态仅表示 P1～P3 通过，不代表利润已核算。

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

## 开发环境

建议使用 Python 3.11–3.14。当前机器为 Python 3.14.3，项目骨架可直接运行；安装 pandas、openpyxl 等完整依赖时仍应以锁定后的 CI 测试结果为准。

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
pytest
```

## 设计原则

- 金额计算以整数“分”或 `Decimal` 为权威口径，不使用二进制浮点数核算。
- 未知成本和运费保持缺失，不以 0 代替。
- 原始输入不可变，所有排除、覆盖和计算必须留有审计字段。
- Python 内存结果是报表事实来源；Excel 公式只用于展示或复核，不作为唯一核算引擎。
