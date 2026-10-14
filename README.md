# 订单利润核算程序

本目录实现订单、成本、退款、运费、平台扣点、综合税赋与推广费用一体化核算，并输出 Excel 核算底稿和面向运营人员的 HTML 店铺/链接复盘页。

## 当前能力

P1～P12 已实现：

- Excel/CSV 输入契约、编码回退、SHA-256 和源行审计；
- ID、日期、数量、金额的严格标准化；
- 订单清洗、期间过滤和六个互斥分区；
- 原始订单表不要求成本或运费列；成本按商家编码从成本编码表解析，实际运费按主订单编号匹配运费表（取`订单编码`第一个下划线前的订单号，汇总该订单各运单总运费）；未匹配时尝试标准运费，再进入人工补充。详细口径见开发文档第 5.3、7.5 节；成本表支持`编码/成本/运费`和`商家编码/单件成本/单件运费`两组表头；
- 人工补充、成本与实际/标准运费解析；
- 有效退款、平台扣点、综合税赋、正常利润和关闭已发货损失；
- 售后主订单级复核、推广每日/链接汇总、SKU/链接/店铺分析；
- 链接 SABC 分级，默认按含推广经营贡献利润 50%/80% 阈值分为 S/A/B/C/待核算；
- 强制勾稽与 `FAILED / PROVISIONAL / FINAL`；
- Excel 报告、自包含 HTML 运营复盘、原子输出事务；
- Tkinter 本地桌面启动器。

## 安装

建议使用 Python 3.11～3.14。

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
python -m playwright install chromium
pytest
```

HTML 报告回归测试使用 Chromium 执行实际 JavaScript，验证每日图表的单点、缺失值断线及交互行为；浏览器仅用于开发测试，不是运行或打包程序的依赖。

HTML 复盘页采用固定浅色、支持移动端阅读，不提供深色主题或专用打印布局。ECharts 展示利润瀑布、每日趋势、产品排行和链接指标前/后 10 双榜（利润、销售额、推广花费/占比、退款金额/率），Tabulator 提供明细排序与核对；产品/链接默认主要列，可切换成本或完整明细、勾选显示列和打开行详情。全部资源与许可证内嵌，页面完全离线。展示与交互验收规则见[开发文档第 9.2 节](docs/订单利润核算标准化程序开发文档.md)。

报表前端资源位于 `src/order_profit/web/`，固定 ECharts 6.0.0 和 Tabulator 6.3.1 的官方发行文件、许可证与来源校验值。Python wheel 须包含该目录；所有 PyInstaller UI/CLI 构建均须使用 `--collect-data order_profit`，否则独立程序无法生成 HTML。

经营总览提供浅色 BI 看板：产品销售结构、核算完整产品盈利贡献环形图，产品盈亏和成本费用柱图。盈利贡献占比以正利润合计为分母，亏损不混入饼图；已有金额及分母说明保留，暂估数据仍不可视作最终利润。

产品分析默认展示链接数、真实销售额、退款金额、推广投产比等主要指标，搭配产品排行、销售/退款对比、推广投入/归因成交对比及各产品盈利贡献占比图；新增图表随产品搜索与筛选联动。更多销量、SKU、成本与 SABC 指标通过显示列或完整明细查看。

Windows 和 macOS 桌面界面使用 Python 标准库 Tkinter，无额外 Web 服务；打包后的程序不需要用户安装 Python。

## Windows 打包与版本

版本号只在 `src/order_profit/__init__.py` 的 `__version__` 中维护。发布新版本时先修改该值，再在 PowerShell 中运行：

```powershell
.\scripts\build-windows.ps1 -Clean
```

脚本使用 `uv` 安装打包依赖，嵌入 `assets/app-icon.ico`，并生成 `dist/订单利润核算-v0.2.5.exe`。随后调用 `scripts/build-cli-skill.ps1`，生成独立 CLI `dist/order-profit-cli-v0.2.5.exe` 和技能包 `dist/order-profit-cli-skill-v0.2.5.zip`；CLI 与 UI 均须包含 XLS/XLSX 读取依赖、业务时区数据和报表前端资源。`build/`、`dist/` 和 PyInstaller 临时配置均不提交 Git。

Windows 必须在原生 Windows x86_64 环境构建，不在 macOS 上交叉打包。`.github/workflows/package-windows.yml` 提供原生 runner 构建、回归和产物上传；临时 `package-*` 分支可用于打包当前本地源码快照，不改动 `main`，快照不包含 `data/`、`output/` 或 `测试数据/`。发布验收包括实际启动 UI 并检查窗口，以及独立 CLI 和解压技能包运行核算、核对运费场景与输出报告。

`0.2.3` 已在[原生 Windows runner](https://github.com/nascloud/order-profit/actions/runs/38227935758)完成构建与验收：110 项回归通过；UI 通过真实键盘输入生成 `FINAL` 报告，独立 CLI 和解压技能包也生成相同业务金额并通过勾稽。验收使用合成数据，运行环境的 `PATH` 不含 Python；截图、运行清单、包 SHA-256 和结果保存在 `dist/`。

`0.2.4` 已在[原生 Windows runner](https://github.com/nascloud/order-profit/actions/runs/38366585764)完成构建：116 项回归通过，UI 真实输入生成 `FINAL`，独立 CLI 和解压技能包也通过金额与勾稽验收。下载的三个发布包 SHA-256 均与原生验收记录一致。三份新包生成 HTML 经 Chromium 执行，在保留原渲染器的前提下限制为单日及清空每日数组，验证四组图表的有限圆点坐标、空 SVG 零占位和恢复显示；记录为 `dist/windows-v0.2.4-chart-acceptance.json`。

## macOS x86_64 UI、CLI 与技能包打包

支持 Intel Mac 的 `.app` 桌面程序和独立命令行程序，运行时不需要安装 Python。本次发布版本为 `0.2.5`，以 `macos-x86_64` 后缀区分平台；不是 Apple Silicon 原生程序。UI 与 CLI 是独立入口，技能包调用 CLI。

`0.2.5` 合并 ECharts / Tabulator 离线报表重构：BI 总览、利润公式卡片、可选明细列、行详情、产品背靠背排行和链接指标双榜。双平台 UI、CLI 与技能包必须包含 `order_profit/web/`；验收需实际打开独立程序生成的 HTML，验证离线图表和列切换，不只检查源代码测试。

`0.2.3` 纳入规范 `1.2` 的订单号运费汇总匹配，以及混合刷单明细不占实际运费分摊份额的修复。发布验收须覆盖独立 CLI 和解压技能包的实际调用：子母单、同订单混合刷单/普通明细、刷单/关闭已发货明细、纯刷单正常订单；金额口径见[开发文档第 5.3、7.5 节](docs/订单利润核算标准化程序开发文档.md)。

`0.2.4` 增加每日图表单点、孤立有效值的坐标修复，以及空数据时 SVG 不占布局空间的修复。发布验收须通过浏览器实际执行生成报告的 JavaScript，检查单日圆点、缺失值断线与空状态画布隐藏；行为口径见[当前处理逻辑第 9.2 节](docs/当前处理逻辑与流程.md)。

在 macOS x86_64 环境安装 [uv](https://docs.astral.sh/uv/) 后构建：

```bash
bash scripts/build-macos-x86_64.sh --clean
```

脚本创建独立的 `.venv-macos-x86_64`（Python 3.13），不修改 Windows 的 `.venv`；检查宿主、Python 架构和 Tkinter，构建带图标的 `.app`、独立 CLI 及技能包。两种程序均包含 Excel 读取依赖及业务时区数据。不支持从 Windows/Linux 交叉编译。

生成文件：

```text
dist/order-profit-cli-v0.2.5-macos-x86_64
dist/订单利润核算-v0.2.5-macos-x86_64.app
dist/订单利润核算-v0.2.5-macos-x86_64.app.zip
dist/order-profit-cli-skill-v0.2.5-macos-x86_64.zip
```

直接运行：

```bash
./dist/order-profit-cli-v0.2.5-macos-x86_64 --version
./dist/order-profit-cli-v0.2.5-macos-x86_64 run \
  --orders '订单.xlsx' \
  --costs '成本编码表.xlsx' \
  --freight '运费.xls' \
  --start-date 2026-08-01 \
  --end-date 2026-08-07 \
  --platform tmall \
  --output-dir '核算结果'
```

参数和退出码与下面的 Python CLI 相同。技能包解压后，通过 `bash '<skill-dir>/scripts/order-profit.sh'` 传入相同参数即可。

桌面用户解压 `.app.zip` 后双击 `.app`；移动整个 `.app`，不要只复制 `Contents/MacOS` 中的可执行文件。UI 发布验收须实际启动窗口，填写输入与日期并执行核算，核对生成的报告；CLI 与技能包按上述运费场景验收。

若复制或解压后丢失执行权限，执行 `chmod +x '<程序路径>'`。构建产物仅带 ad-hoc 签名，未做 Apple Developer ID 签名或公证；跨机器下载后可能被 Gatekeeper 拦截，仅在确认来源可信后通过 macOS 的隐私与安全性设置允许运行。

已在 macOS x86_64 验证独立程序的 XLS/XLSX 读取、中文及空格路径、内置时区、Excel/HTML 报告生成、人工补充闭环和解压后的技能包调用。

`0.2.3` 已通过上述运费场景验收：独立程序和解压技能包均在项目目录外、`PATH` 不含 Python 的环境运行，生成 `FINAL` 报告并通过金额勾稽；技能包内程序的 SHA-256 与独立程序一致。另用 `测试数据/` 中的 9 月、10 月订单与物流表核对了 1,260 个有实际运费接收方的订单，订单运费合计均守恒；真实样本仍有缺失商家编码或成本/运费，输出为 `PROVISIONAL`，需要按待补清单处理，不能作为完整财务结算结果。

`0.2.3` 的 `.app.zip` 已在解压后通过 LaunchServices 实际启动、填写输入与日期并点击生成，得到 `FINAL` Excel/HTML 报告；子母单、混合刷单/普通、刷单/关闭已发货、纯刷单四类金额均符合规则。该版本 `.app` 的 x86_64 架构、版本元数据和 ad-hoc 签名完整性均已核对，桌面截图保存在 `dist/mac-ui-generated.png`。

`0.2.4` 的 macOS UI、独立 CLI 和解压技能包已实际生成 `FINAL` 报告并通过 46 项勾稽。三份生成 HTML 经 Chromium 执行，四组图表的单日圆点均有有限坐标；空状态通过清空页面的每日数组后调用原渲染器验证，SVG 为 `display: none` 且宽高均为 0，恢复数据后可重新显示。此空状态验证不代表空订单流水线会输出空数组。签名、x86_64 架构及应用版本已核对；验收记录为 `dist/mac-v0.2.4-acceptance.json`，截图为 `dist/mac-v0.2.4-*.png`。

本地 CC Switch 的 `~/.cc-switch/skills/order-profit-cli` 已更新为 `0.2.4`，包含双平台 CLI，并同步内容哈希和更新时间；Claude、Codex、OpenCode 的共享技能入口均实际返回 `0.2.4`。更新后在无 Python `PATH` 下调用已安装技能生成 `FINAL`，46 项勾稽通过，生成 HTML 的 SHA-256 与浏览器验收通过的 macOS 技能报告一致。更新前技能保存在 `~/.cc-switch/skill-backups/`；这些用户目录文件不提交项目 Git。

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
待补成本运费.xlsx     # 仅 PROVISIONAL 时生成
```

### PROVISIONAL 补充闭环

当报告为 `PROVISIONAL` 时：

1. 打开报告目录中的 `待补成本运费.xlsx`。
2. 在第一张`人工补充表`中参考紧跟商品ID展示的`商品标题`、`商品属性`和`用户付款金额`，填写黄色单元格：
   - 原商家编码为空：同时填写该明细的货品成本和运费；
   - 已有商家编码：按缺失项目填写成本和/或运费。
3. 将 `补充状态` 从 `草稿` 改为 `已确认`。
4. 保存，不要修改主订单编号、商品ID、原商家编码和明细序号。
5. 回到桌面端，把该文件选为“人工补充表”，重新生成。程序会把已经确认且已应用的记录保留在新生成的 `待补成本运费.xlsx` 中，因此可以继续使用同一个文件逐轮补充；`manifest.json` 的待补行数只统计仍未完成的草稿，不包括这些已确认留存行。

草稿和作废行不会参与核算。`明细序号`是原订单 Excel 行号，可精确定位基础键重复的订单。新生成的待补表不提供补编码入口：原商家编码为空时，必须同时填写成本和运费，该明细即可直接进入利润核算。已有商家编码的明细只需补齐仍缺失的金额。人工填写的金额只用于参考表无法解析的项目，不会覆盖可以从成本编码表或运费表获得的金额。

报告先在同一文件系统的临时目录生成并校验，再原子替换目标目录。失败不会覆盖上一份成功报告。

常用选项：

- `--platform tmall|taobao`：必需；程序不猜平台。
- `--overwrite-existing`：同一人工补充记录再次导入时，允许新补充值覆盖既有补充值；不会覆盖成本编码表或运费表的可解析结果。
- `--require-complete`：存在成本/运费缺失时返回非零且不发布正式报告。
- `--timezone Asia/Shanghai`：配置业务时区。
- `--sabc-config sabc.json`：可选；自定义 S/A 分级阈值，未指定时使用 50%/80%。

## 报告状态

- `FINAL`：有效正常及关闭订单成本/运费完整；无商家编码订单已通过人工补充完整成本和运费；全部勾稽通过。
- `PROVISIONAL`：流水线及勾稽通过，但仍有成本/运费或商家编码缺失；同时生成待补表。
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
- SABC 使用链接含推广经营贡献利润分级，不按销售额分级；详见 `docs/SABC分级规则说明.md`。
- HTML 动作标签只作运营复盘提示，不自动修改推广计划。

## 文档

- `AGENTS.md`：项目级开发规则与资料优先、TDD、最小实现、最终核对的开发周期。

- `docs/当前处理逻辑与流程.md`：当前版本完整处理流程。
- `docs/处理规则.md`：核心业务口径速查。
- `docs/SABC分级规则说明.md`：链接 SABC 分级规则。
