"""面向运营人员的本地 Tkinter 启动器。"""

from __future__ import annotations

import queue
import threading
import traceback
from datetime import date
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox, ttk
from typing import Any

from order_profit.config import Platform, RunConfig
from order_profit.errors import OrderProfitError
from order_profit.reporting import PublishedReports, execute_run


INPUT_KEY_LABELS = {
    "orders": "订单表",
    "costs": "成本编码表",
    "freight": "运费表",
    "after_sales": "售后表",
    "promotion": "推广报表",
    "supplements": "人工补充表",
}


def format_desktop_error(exc: Exception) -> str:
    """把结构化业务异常转换为运营人员可直接处理的中文提示。"""

    if not isinstance(exc, OrderProfitError):
        return str(exc)
    lines = [f"错误代码：{exc.code}", "", exc.message]
    for issue in exc.issues:
        location = issue.location
        details = []
        if location.file:
            details.append(f"文件：{location.file}")
        if location.sheet:
            details.append(f"工作表：{location.sheet}")
        if location.row is not None:
            details.append(f"Excel 行号：{location.row}")
        if location.field:
            details.append(f"字段：{location.field}")
        if details:
            lines.extend(["", *details])
        if issue.raw_value not in (None, "", [], {}):
            lines.append(f"原始值：{issue.raw_value}")
        if issue.suggestion:
            lines.extend(["", f"处理建议：{issue.suggestion}"])
    if exc.code == "INPUT_KEY_EMPTY":
        lines.extend(
            [
                "",
                "如需正式核算：请补齐该行编码及运费，或确认无效后删除整行。",
                "如需先看暂算报告：清空界面中的“成本编码表”后重新生成。",
            ]
        )
    return "\n".join(lines)


class DesktopApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("订单利润核算｜店铺经营复盘")
        self.root.geometry("920x760")
        self.root.minsize(760, 680)
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.paths = {
            "orders": StringVar(),
            "costs": StringVar(),
            "freight": StringVar(),
            "after_sales": StringVar(),
            "promotion": StringVar(),
            "supplements": StringVar(),
            "output_dir": StringVar(value=str(Path.cwd() / "output")),
        }
        self.start_date = StringVar(value=date.today().replace(day=1).isoformat())
        self.end_date = StringVar(value=date.today().isoformat())
        self.platform = StringVar(value=Platform.TMALL.value)
        self.overwrite = BooleanVar(value=False)
        self.require_complete = BooleanVar(value=False)
        self.status = StringVar(value="请选择文件并设置核算期间")
        self._build()
        self.root.after(120, self._poll_messages)

    def _build(self) -> None:
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Section.TLabel", font=("Microsoft YaHei UI", 11, "bold"))
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="店铺经营复盘生成器", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="选择经营数据，一键生成 Excel 核算表和可搜索 HTML 运营复盘。",
        ).pack(anchor="w", pady=(4, 18))

        files = ttk.LabelFrame(outer, text="输入文件", padding=14)
        files.pack(fill="x")
        fields = [
            ("orders", "订单表 *", (("Excel", "*.xlsx"),)),
            ("costs", "成本编码表", (("Excel", "*.xlsx"),)),
            ("freight", "运费表", (("Excel", "*.xls *.xlsx"),)),
            ("after_sales", "售后表", (("Excel", "*.xlsx"),)),
            ("promotion", "推广报表", (("CSV", "*.csv"),)),
            ("supplements", "人工补充表", (("Excel", "*.xlsx"),)),
        ]
        for row, (key, label, filetypes) in enumerate(fields):
            ttk.Label(files, text=label, width=13).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(files, textvariable=self.paths[key]).grid(
                row=row, column=1, sticky="ew", padx=(6, 8), pady=4
            )
            ttk.Button(
                files,
                text="选择",
                command=lambda k=key, f=filetypes: self._choose_file(k, f),
            ).grid(row=row, column=2, pady=4)
        files.columnconfigure(1, weight=1)

        settings = ttk.LabelFrame(outer, text="核算设置", padding=14)
        settings.pack(fill="x", pady=14)
        ttk.Label(settings, text="开始日期").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.start_date, width=16).grid(
            row=0, column=1, sticky="w", padx=(6, 20)
        )
        ttk.Label(settings, text="结束日期").grid(row=0, column=2, sticky="w")
        ttk.Entry(settings, textvariable=self.end_date, width=16).grid(
            row=0, column=3, sticky="w", padx=(6, 20)
        )
        ttk.Label(settings, text="平台").grid(row=0, column=4, sticky="w")
        ttk.Combobox(
            settings,
            textvariable=self.platform,
            values=[Platform.TMALL.value, Platform.TAOBAO.value],
            state="readonly",
            width=12,
        ).grid(row=0, column=5, sticky="w", padx=(6, 0))
        ttk.Checkbutton(
            settings,
            text="人工补充覆盖订单已有值",
            variable=self.overwrite,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Checkbutton(
            settings,
            text="存在成本/运费缺失时停止交付",
            variable=self.require_complete,
        ).grid(row=1, column=3, columnspan=3, sticky="w", pady=(12, 0))

        output = ttk.LabelFrame(outer, text="输出位置", padding=14)
        output.pack(fill="x")
        ttk.Entry(output, textvariable=self.paths["output_dir"]).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(output, text="选择目录", command=self._choose_output).pack(
            side="left", padx=(8, 0)
        )

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=16)
        self.run_button = ttk.Button(actions, text="生成经营复盘", command=self._start_run)
        self.run_button.pack(side="left")
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=220)
        self.progress.pack(side="left", padx=14)
        ttk.Label(actions, textvariable=self.status).pack(side="left", fill="x", expand=True)

        note = ttk.LabelFrame(outer, text="口径提示", padding=12)
        note.pack(fill="both", expand=True)
        ttk.Label(
            note,
            wraplength=820,
            justify="left",
            text=(
                "扣点：天猫 6%，淘宝 0.6%；综合税赋 2.3%。费用按“实收－退款”逐行分币。\n"
                "推广归因成交不计入销售额；PROVISIONAL 为暂算，补齐成本/运费后再作为最终利润。"
            ),
        ).pack(anchor="w")

    def _choose_file(self, key: str, filetypes: tuple[tuple[str, str], ...]) -> None:
        selected = filedialog.askopenfilename(filetypes=filetypes + (("所有文件", "*.*"),))
        if selected:
            self.paths[key].set(selected)

    def _choose_output(self) -> None:
        selected = filedialog.askdirectory()
        if selected:
            self.paths["output_dir"].set(selected)

    def _build_config(self) -> RunConfig:
        if not self.paths["orders"].get().strip():
            raise ValueError("请选择订单表")
        if not self.paths["output_dir"].get().strip():
            raise ValueError("请选择输出目录")

        def optional(key: str) -> Path | None:
            value = self.paths[key].get().strip()
            return Path(value) if value else None

        return RunConfig(
            orders=Path(self.paths["orders"].get().strip()),
            costs=optional("costs"),
            freight=optional("freight"),
            after_sales=optional("after_sales"),
            promotion=optional("promotion"),
            supplements=optional("supplements"),
            start_date=date.fromisoformat(self.start_date.get().strip()),
            end_date=date.fromisoformat(self.end_date.get().strip()),
            platform=Platform(self.platform.get()),
            output_dir=Path(self.paths["output_dir"].get().strip()),
            overwrite_existing=self.overwrite.get(),
            require_complete=self.require_complete.get(),
        )

    def _start_run(self) -> None:
        try:
            config = self._build_config()
        except (ValueError, OrderProfitError) as exc:
            messagebox.showerror("无法开始", str(exc))
            return
        self.run_button.configure(state="disabled")
        self.progress.start(10)
        self.status.set("正在读取并核算，请勿关闭窗口…")
        threading.Thread(target=self._run_worker, args=(config,), daemon=True).start()

    def _run_worker(self, config: RunConfig) -> None:
        try:
            outcome = execute_run(config)
            self.messages.put(
                ("success", (outcome.result.reconciliation.status.value, outcome.reports))
            )
        except Exception as exc:
            detail = traceback.format_exc() if not isinstance(exc, (OrderProfitError, ValueError)) else ""
            self.messages.put(("error", (format_desktop_error(exc), detail)))

    def _poll_messages(self) -> None:
        try:
            kind, payload = self.messages.get_nowait()
        except queue.Empty:
            self.root.after(120, self._poll_messages)
            return
        self.progress.stop()
        self.run_button.configure(state="normal")
        if kind == "success":
            status, reports = payload
            assert isinstance(reports, PublishedReports)
            self.status.set(f"已生成：{status}")
            messagebox.showinfo(
                "经营复盘已生成",
                f"状态：{status}\n\nExcel：{reports.excel}\n\nHTML：{reports.html}",
            )
        else:
            message, detail = payload
            self.status.set("运行失败，请按提示修正")
            messagebox.showerror("生成失败", message + (f"\n\n{detail}" if detail else ""))
        self.root.after(120, self._poll_messages)


def main() -> int:
    root = Tk()
    DesktopApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
