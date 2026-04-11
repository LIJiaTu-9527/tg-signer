import json
import os
from pathlib import Path
from typing import Callable, Dict

from nicegui import app, ui
from pydantic import TypeAdapter

from tg_signer import __version__
from tg_signer.ai_tools import DEFAULT_MODEL
from tg_signer.core import DICE_EMOJIS
from tg_signer.webui.data import (
    CONFIG_META,
    DEFAULT_LOG_FILE,
    DEFAULT_WORKDIR,
    ConfigKind,
    delete_config,
    get_workdir,
    list_log_files,
    list_task_names,
    load_config,
    load_llm_config,
    load_logs,
    load_sign_records,
    load_user_infos,
    save_config,
    save_llm_config,
)
from tg_signer.webui.interactive import InteractiveSignerConfig
from tg_signer.webui.pages import (
    ImmediateOpsPanel,
    LLMConfigPanel,
    LoginPanel,
    RunConfigPanel,
)
from tg_signer.webui.runtime import TGWebRuntime
from tg_signer.webui.schema_utils import clean_schema

SIGNER_TEMPLATE: Dict[str, object] = {
    "chats": [
        {
            "chat_id": "@bot_or_user",
            "name": "示例签到",
            "delete_after": None,
            "actions": [{"action": 1, "text": "签到"}],
            "action_interval": 1,
        }
    ],
    "sign_at": "0 6 * * *",
    "random_seconds": 0,
    "sign_interval": 1,
}

MONITOR_TEMPLATE: Dict[str, object] = {
    "match_cfgs": [
        {
            "chat_id": "@channel_or_user",
            "rule": "contains",
            "rule_value": "关键词",
            "from_user_ids": None,
            "always_ignore_me": False,
            "default_send_text": "自动回复",
            "ai_reply": False,
            "ai_prompt": None,
            "send_text_search_regex": None,
            "delete_after": None,
            "ignore_case": True,
            "forward_to_chat_id": None,
            "external_forwards": None,
            "push_via_server_chan": False,
            "server_chan_send_key": None,
        }
    ]
}

AUTH_CODE_ENV = "TG_SIGNER_GUI_AUTHCODE"
AUTH_STORAGE_KEY = "tg_signer_gui_auth_code"


class UIState:
    def __init__(self) -> None:
        self.workdir: Path = get_workdir(DEFAULT_WORKDIR)
        self.log_path: Path = DEFAULT_LOG_FILE
        self.log_limit: int = 200
        self.record_filter: str = ""

    def set_workdir(self, path_str: str) -> None:
        self.workdir = get_workdir(Path(path_str).expanduser())

    def set_log_path(self, path_str: str) -> None:
        self.log_path = Path(path_str).expanduser()


state = UIState()
runtime = TGWebRuntime()


def pretty_json(data: Dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def notify_error(exc: Exception) -> None:
    ui.notify(str(exc), type="negative")


def normalize_chat_target(value: str) -> int | str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("请输入 chat_id 或 @username")
    if raw.startswith("@"):
        return raw[1:]
    try:
        return int(raw)
    except ValueError:
        return raw


def comma_items(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


class BaseConfigBlock:
    def __init__(self, kind: ConfigKind, template: Dict[str, object]):
        self.kind = kind
        self.template = template
        self.root_dir, self.cfg_cls = CONFIG_META[kind]
        self.selected_name: dict[str, str] = {"value": ""}
        title = "签到配置" if kind == "signer" else "监控配置"

        with ui.card().classes("w-full shadow-sm"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0"):
                    ui.label(f"{title} ({kind})").classes("text-lg font-semibold")
                    ui.label(f"目录: {self.root_dir}/<name>/config.json").classes(
                        "text-sm text-gray-500"
                    )
                self.setup_toolbar()

            with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                self.select = ui.select(
                    label="选择配置",
                    options=[],
                    with_input=True,
                    on_change=self.load_current,
                ).classes("min-w-[240px]")
                self.name_input = ui.input(
                    label="保存为 / 新建名称",
                    placeholder="my_task",
                ).classes("min-w-[220px]")
                ui.button("重置", on_click=self.clear_selection).props("outline")
                ui.button("使用示例", on_click=self.fill_template).props("outline")
                ui.button("导出 JSON", on_click=self.open_export_dialog).props(
                    "outline"
                )
                ui.button("导入 JSON", on_click=self.open_import_dialog).props(
                    "outline"
                )

            schema = TypeAdapter(self.cfg_cls | None).json_schema()
            if self.kind == "monitor":
                schema = clean_schema(schema)

            def on_change(e):
                self.editor.properties["content"] = e.content

            self.editor = ui.json_editor(
                {"content": {"json": None}},
                schema=schema,
                on_change=on_change,
            )

            with ui.row().classes("gap-2 items-center mt-2"):
                ui.button("刷新列表", on_click=self.refresh_options)
                ui.button("加载", on_click=self.load_current)
                ui.button("保存", color="primary", on_click=self.save_current)
                ui.button("删除", color="negative", on_click=self.delete_current)
            self.setup_footer()

    def setup_toolbar(self) -> None:
        pass

    def setup_footer(self) -> None:
        pass

    def __call__(self, *args, **kwargs):
        self.refresh_options()

    def clear_selection(self) -> None:
        self.select.value = None
        self.select.update()
        self.name_input.value = ""
        self.name_input.update()
        self.selected_name["value"] = ""
        self.fill_template()

    def refresh_options(self) -> None:
        self.select.options = list_task_names(self.kind, state.workdir)
        self.select.update()

    def load_current(self) -> None:
        target = (self.select.value or "").strip()
        if not target:
            return
        try:
            entry = load_config(self.kind, target, workdir=state.workdir)
            self.editor.properties["content"]["json"] = entry.payload
            self.editor.update()
            self.editor.run_editor_method(":expand", "[]", "path => true")
            self.name_input.value = entry.name
            self.name_input.update()
            self.selected_name["value"] = target
            self.on_loaded(target)
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    def on_loaded(self, target: str) -> None:
        del target

    def save_current(self) -> None:
        target = (self.name_input.value or self.select.value or "").strip()
        if not target:
            ui.notify("请先填写配置名称", type="warning")
            return
        try:
            save_config(
                self.kind,
                target,
                self.editor.properties["content"]["json"] or "{}",
                workdir=state.workdir,
            )
            self.refresh_options()
            self.select.value = target
            self.select.update()
            self.selected_name["value"] = target
            ui.notify("保存成功", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    def fill_template(self) -> None:
        self.editor.properties["content"]["json"] = json.loads(
            json.dumps(self.template, ensure_ascii=False)
        )
        self.editor.update()

    def delete_current(self) -> None:
        target = (self.select.value or self.name_input.value or "").strip()
        if not target:
            ui.notify("请先选择要删除的配置", type="warning")
            return
        try:
            delete_config(self.kind, target, workdir=state.workdir)
            self.refresh_options()
            self.clear_selection()
            ui.notify("删除成功", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    def open_export_dialog(self) -> None:
        content = self.editor.properties["content"].get("json")
        if not content:
            ui.notify("当前没有可导出的配置内容", type="warning")
            return

        with ui.dialog() as dialog, ui.card().classes("w-[900px] max-w-full"):
            ui.label("导出 JSON").classes("text-lg font-semibold")
            export_area = ui.textarea(
                value=pretty_json(content),
                label="配置内容",
            ).classes("w-full")
            export_area.props("readonly autogrow")
            with ui.row().classes("w-full justify-end"):
                ui.button("关闭", on_click=dialog.close)
        dialog.open()

    def open_import_dialog(self) -> None:
        with ui.dialog() as dialog, ui.card().classes("w-[900px] max-w-full"):
            ui.label("导入 JSON").classes("text-lg font-semibold")
            textarea = ui.textarea(
                label="粘贴配置 JSON",
                placeholder='{"_version": 3, "...": "..."}',
            ).classes("w-full")
            ui.label("导入只会写入编辑器；点击“保存”后才会落盘。").classes(
                "text-sm text-gray-500"
            )

            def confirm() -> None:
                try:
                    payload = json.loads(textarea.value or "")
                    self.editor.properties["content"]["json"] = payload
                    self.editor.update()
                    dialog.close()
                    ui.notify("已导入到编辑器，请确认后保存", type="positive")
                except Exception as exc:  # noqa: BLE001
                    notify_error(exc)

            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("取消", on_click=dialog.close).props("flat")
                ui.button("导入", color="primary", on_click=confirm)
        dialog.open()


class SignerBlock(BaseConfigBlock):
    def __init__(
        self,
        template: Dict[str, object],
        *,
        goto_records: Callable[[str], None] = lambda _task: None,
    ):
        self._goto_records = goto_records
        self.record_btn = None
        self.record_hint = None
        super().__init__("signer", template)

    def setup_toolbar(self) -> None:
        ui.button("交互式配置", on_click=self.open_interactive).props("outline")

    def setup_footer(self) -> None:
        self.record_hint = ui.label("").classes("text-sm text-primary")
        self.record_btn = ui.button(
            "查看签到记录",
            color="primary",
            on_click=self.goto_records,
        )
        self.record_btn.disable()

    def on_loaded(self, target: str) -> None:
        records = load_sign_records(state.workdir)
        has_record = any(record.task == target for record in records)
        if has_record:
            self.record_btn.enable()
            self.record_hint.text = f"已发现 {target} 的签到记录"
        else:
            self.record_btn.disable()
            self.record_hint.text = "当前任务还没有签到记录"
        self.record_hint.update()
        self.record_btn.update()

    def goto_records(self) -> None:
        self._goto_records(self.selected_name["value"])

    def open_interactive(self) -> None:
        initial_config = self.editor.properties["content"].get("json")
        initial_name = self.name_input.value or self.select.value or ""

        def on_complete() -> None:
            self.refresh_options()
            if self.select.value:
                self.load_current()

        InteractiveSignerConfig(
            state.workdir,
            on_complete=on_complete,
            initial_config=initial_config,
            initial_name=initial_name,
        ).open()


class MonitorBlock(BaseConfigBlock):
    def __init__(self, template: Dict[str, object]):
        super().__init__("monitor", template)


def user_info_block() -> Callable[[], None]:
    container = ui.column().classes("w-full gap-3")

    def refresh() -> None:
        container.clear()
        entries = load_user_infos(state.workdir)
        with container:
            if not entries:
                ui.label("当前工作目录下还没有用户资料。").classes("text-gray-500")
                return
            for entry in entries:
                name = entry.data.get("first_name") or entry.data.get("username") or ""
                header = f"{entry.user_id} {name}".strip()
                with ui.expansion(header, icon="person").classes("w-full shadow-sm"):
                    ui.label(f"文件: {entry.path}").classes("text-sm text-gray-500")
                    ui.code(pretty_json(entry.data), language="json").classes("w-full")

                    if entry.latest_chats:
                        rows = []
                        for chat in entry.latest_chats:
                            rows.append(
                                {
                                    "id": chat.get("id"),
                                    "title": chat.get("title")
                                    or chat.get("first_name")
                                    or "N/A",
                                    "type": str(chat.get("type")),
                                    "username": chat.get("username") or "",
                                }
                            )
                        ui.table(
                            columns=[
                                {
                                    "name": "id",
                                    "label": "ID",
                                    "field": "id",
                                    "align": "left",
                                },
                                {
                                    "name": "title",
                                    "label": "名称",
                                    "field": "title",
                                    "align": "left",
                                },
                                {
                                    "name": "type",
                                    "label": "类型",
                                    "field": "type",
                                    "align": "left",
                                },
                                {
                                    "name": "username",
                                    "label": "用户名",
                                    "field": "username",
                                    "align": "left",
                                },
                            ],
                            rows=rows,
                            pagination=10,
                        ).classes("w-full").props("flat dense")
                    else:
                        ui.label("还没有 recent chats 记录。").classes(
                            "text-sm text-gray-500"
                        )

    return refresh


class SignRecordBlock:
    def __init__(self):
        self.container = ui.column().classes("w-full gap-3")
        with ui.row().classes("items-end gap-3"):
            self.filter_input = ui.input(
                label="筛选任务 / 用户",
                placeholder="输入任务名或用户 ID",
                value=state.record_filter,
                on_change=lambda e: self._update_filter(e.value),
            ).classes("w-full")
            ui.button("清除筛选", on_click=lambda: self._update_filter("")).props(
                "outline"
            )
        self.status = ui.label("").classes("text-sm text-gray-500")

    def _update_filter(self, value: str) -> None:
        state.record_filter = value or ""
        self.refresh()

    def refresh(self) -> None:
        self.container.clear()
        records = load_sign_records(state.workdir)
        keyword = (state.record_filter or "").lower().strip()
        if keyword:
            records = [
                record
                for record in records
                if keyword in record.task.lower()
                or (record.user_id and keyword in str(record.user_id).lower())
            ]
        with self.container:
            if not records:
                self.status.text = (
                    "没有找到匹配的签到记录" if keyword else "当前还没有签到记录"
                )
                self.status.update()
                return
            self.status.text = f"共 {len(records)} 组记录"
            self.status.update()
            for record in records:
                owner = record.user_id or "default"
                header = f"{record.task} / {owner}（{len(record.records)} 条）"
                with ui.expansion(header, icon="event").classes("w-full shadow-sm"):
                    ui.label(f"文件: {record.path}").classes("text-sm text-gray-500")
                    rows = [
                        {"date": date_text, "time": time_text}
                        for date_text, time_text in record.records
                    ]
                    ui.table(
                        columns=[
                            {"name": "date", "label": "日期", "field": "date"},
                            {"name": "time", "label": "时间", "field": "time"},
                        ],
                        rows=rows,
                    ).classes("w-full").props("flat dense")

    def __call__(self, *args, **kwargs):
        self.refresh()


def log_block() -> Callable[[], None]:
    with ui.card().classes("w-full shadow-sm"):
        ui.label("日志查看").classes("text-lg font-semibold")
        ui.label("查看日志文件最新内容，可切换文件与显示行数。").classes(
            "text-sm text-gray-500"
        )

        with ui.row().classes("items-end w-full gap-3 flex-wrap"):
            limit_input = ui.number(
                label="显示行数",
                value=state.log_limit,
                min=10,
                max=2000,
                format="%d",
            ).classes("w-32")
            log_select = ui.select(
                label="日志文件",
                options=[],
                on_change=lambda e: select_log_file(e.value),
            ).classes("min-w-[240px]")
            log_path_input = ui.input(
                label="日志路径",
                value=str(state.log_path),
            ).classes("w-full")

        log_area = ui.textarea(label="日志内容", value="").classes("w-full")
        log_area.props("readonly autogrow")
        status = ui.label("").classes("text-xs text-gray-500")

        def refresh_log_options() -> None:
            options = [str(path) for path in list_log_files(runtime.settings.log_dir)]
            current_path = str(log_path_input.value or state.log_path)
            if current_path and current_path not in options:
                options.insert(0, current_path)
            log_select.options = options
            log_select.value = current_path
            log_select.update()

        def select_log_file(path_value: str | None) -> None:
            if not path_value:
                return
            log_path_input.value = path_value
            log_path_input.update()
            refresh()

        def refresh() -> None:
            refresh_log_options()
            try:
                state.log_limit = int(limit_input.value or state.log_limit)
            except ValueError:
                state.log_limit = 200
            state.set_log_path(log_path_input.value or str(DEFAULT_LOG_FILE))
            path, lines = load_logs(state.log_limit, log_path_input.value)
            log_area.value = "\n".join(lines)
            log_area.update()
            if lines:
                status.text = f"文件: {path} | 显示最新 {len(lines)} 行"
            else:
                status.text = f"未找到日志文件: {path}"
            status.update()

        with ui.row().classes("gap-2"):
            ui.button("刷新日志", on_click=refresh)

        refresh_log_options()
        return refresh


class OperationsPanel:
    def __init__(self, on_global_refresh: Callable[[], None]):
        self.on_global_refresh = on_global_refresh
        self.auth_status = None
        self.pending_status = None
        self.jobs_container = None
        self.events_area = None
        self.logs_area = None
        self.members_table = None
        self.schedule_table = None
        self.signer_tasks_hint = None
        self.monitor_tasks_hint = None
        self.llm_status = None
        self._build()
        ui.timer(1.0, self.refresh_runtime_views)

    def __call__(self, *args, **kwargs):
        self.refresh()

    def _build(self) -> None:
        with ui.column().classes("w-full gap-4"):
            self._build_runtime_settings()
            self._build_auth_card()
            self._build_actions_card()
            self._build_scheduler_card()
            self._build_jobs_card()
            self._build_llm_card()

    def _build_runtime_settings(self) -> None:
        with ui.card().classes("w-full shadow-sm"):
            ui.label("运行时设置").classes("text-lg font-semibold")
            ui.label("这里控制当前 Web 页面使用的账号、session、日志与代理设置。").classes(
                "text-sm text-gray-500"
            )
            with ui.grid(columns=2).classes("w-full gap-4"):
                self.account_input = ui.input(
                    label="账号名",
                    value=runtime.settings.account,
                ).props("outlined")
                self.session_dir_input = ui.input(
                    label="Session 目录",
                    value=str(runtime.settings.session_dir),
                ).props("outlined")
                self.proxy_input = ui.input(
                    label="代理",
                    value=runtime.settings.proxy,
                    placeholder="socks5://127.0.0.1:7890",
                ).props("outlined")
                self.num_dialogs_input = ui.number(
                    label="最近对话数量",
                    value=runtime.settings.num_of_dialogs,
                    min=1,
                    format="%d",
                ).props("outlined")
                self.log_level_input = ui.select(
                    label="日志级别",
                    options=["DEBUG", "INFO", "WARN", "ERROR"],
                    value=runtime.settings.log_level,
                ).props("outlined")
                self.log_dir_input = ui.input(
                    label="日志目录",
                    value=str(runtime.settings.log_dir),
                ).props("outlined")
                self.log_file_input = ui.input(
                    label="日志文件",
                    value=str(runtime.settings.log_file),
                ).props("outlined")
                self.in_memory_input = ui.checkbox(
                    "Session 仅保存在内存",
                    value=runtime.settings.in_memory,
                )

            with ui.expansion("高级设置").classes("w-full"):
                self.session_string_input = ui.textarea(
                    label="Session String",
                    value=runtime.settings.session_string,
                    placeholder="可选，用于覆盖本地 session 文件",
                ).classes("w-full")

            with ui.row().classes("w-full justify-end"):
                ui.button("应用设置", color="primary", on_click=self.apply_runtime)

    def _build_auth_card(self) -> None:
        with ui.card().classes("w-full shadow-sm"):
            ui.label("账号登录").classes("text-lg font-semibold")
            self.auth_status = ui.label("尚未检查当前账号状态").classes(
                "text-sm text-gray-600"
            )
            self.pending_status = ui.label("").classes("text-sm text-primary")
            with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                self.phone_input = ui.input(
                    label="手机号",
                    placeholder="+8613800000000",
                ).classes("min-w-[240px]")
                ui.button("检查状态", on_click=self.check_auth_status).props("outline")
                ui.button("发送验证码", color="primary", on_click=self.begin_login)
                ui.button("退出登录", color="negative", on_click=self.logout)
            with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                self.code_input = ui.input(
                    label="验证码",
                    placeholder="12345",
                ).classes("min-w-[240px]")
                ui.button("提交验证码", on_click=self.submit_code)
            with ui.row().classes("w-full items-end gap-3 flex-wrap"):
                self.password_input = ui.input(
                    label="二步验证密码",
                    password=True,
                    password_toggle_button=True,
                ).classes("min-w-[240px]")
                ui.button("提交二步验证", on_click=self.submit_password)

    def _build_actions_card(self) -> None:
        with ui.card().classes("w-full shadow-sm"):
            ui.label("即时操作").classes("text-lg font-semibold")
            with ui.tabs().classes("w-full") as tabs:
                tab_send = ui.tab("发送消息")
                tab_members = ui.tab("成员查询")
            with ui.tab_panels(tabs, value=tab_send).classes("w-full"):
                with ui.tab_panel(tab_send):
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        self.send_chat_input = ui.input(
                            label="目标 chat_id / @username"
                        ).props("outlined")
                        self.send_delete_after_input = ui.number(
                            label="删除延迟（秒，可空）",
                            value=None,
                            format="%d",
                        ).props("outlined")
                    self.send_text_input = ui.textarea(
                        label="发送文本",
                        placeholder="/checkin",
                    ).classes("w-full")
                    with ui.row().classes("items-end gap-3 flex-wrap"):
                        ui.button("发送文本", color="primary", on_click=self.send_text)
                        self.dice_select = ui.select(
                            label="Dice Emoji",
                            options=list(DICE_EMOJIS),
                            value=DICE_EMOJIS[0],
                        ).classes("min-w-[180px]")
                        ui.button("发送 Dice", on_click=self.send_dice)

                with ui.tab_panel(tab_members):
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        self.members_chat_input = ui.input(
                            label="聊天 ID / @username"
                        ).props("outlined")
                        self.members_query_input = ui.input(
                            label="搜索关键词（管理员模式可留空）"
                        ).props("outlined")
                        self.members_limit_input = ui.number(
                            label="数量限制",
                            value=10,
                            min=1,
                            format="%d",
                        ).props("outlined")
                        self.members_admin_input = ui.checkbox("只看管理员", value=False)
                    ui.button("查询成员", color="primary", on_click=self.load_members)
                    self.members_table = ui.table(
                        columns=[
                            {"name": "id", "label": "ID", "field": "id"},
                            {"name": "username", "label": "用户名", "field": "username"},
                            {
                                "name": "first_name",
                                "label": "First Name",
                                "field": "first_name",
                            },
                            {
                                "name": "last_name",
                                "label": "Last Name",
                                "field": "last_name",
                            },
                            {"name": "status", "label": "状态", "field": "status"},
                            {"name": "is_bot", "label": "Bot", "field": "is_bot"},
                        ],
                        rows=[],
                        pagination=10,
                    ).classes("w-full").props("flat dense")

    def _build_scheduler_card(self) -> None:
        with ui.card().classes("w-full shadow-sm"):
            ui.label("定时消息").classes("text-lg font-semibold")
            with ui.tabs().classes("w-full") as tabs:
                tab_create = ui.tab("批量创建")
                tab_list = ui.tab("查看已配置")
            with ui.tab_panels(tabs, value=tab_create).classes("w-full"):
                with ui.tab_panel(tab_create):
                    with ui.grid(columns=2).classes("w-full gap-4"):
                        self.schedule_chat_input = ui.input(
                            label="聊天 ID / @username"
                        ).props("outlined")
                        self.schedule_crontab_input = ui.input(
                            label="Crontab",
                            value="0 6 * * *",
                        ).props("outlined")
                        self.schedule_next_input = ui.number(
                            label="生成次数",
                            value=1,
                            min=1,
                            format="%d",
                        ).props("outlined")
                        self.schedule_random_input = ui.number(
                            label="随机秒数",
                            value=0,
                            min=0,
                            format="%d",
                        ).props("outlined")
                    self.schedule_text_input = ui.textarea(
                        label="消息内容",
                        placeholder="hello",
                    ).classes("w-full")
                    ui.button(
                        "创建定时消息",
                        color="primary",
                        on_click=self.create_schedule,
                    )
                with ui.tab_panel(tab_list):
                    with ui.row().classes("items-end gap-3 flex-wrap"):
                        self.schedule_list_chat_input = ui.input(
                            label="聊天 ID / @username"
                        ).props("outlined")
                        ui.button(
                            "加载已配置消息",
                            color="primary",
                            on_click=self.load_schedules,
                        )
                    self.schedule_table = ui.table(
                        columns=[
                            {
                                "name": "message_id",
                                "label": "Message ID",
                                "field": "message_id",
                            },
                            {"name": "date", "label": "发送时间", "field": "date"},
                            {"name": "text", "label": "内容", "field": "text"},
                        ],
                        rows=[],
                        pagination=10,
                    ).classes("w-full").props("flat dense")

    def _build_jobs_card(self) -> None:
        with ui.card().classes("w-full shadow-sm"):
            ui.label("任务运行").classes("text-lg font-semibold")
            ui.label("可以从 Web 启动 signer、run-once、monitor 和 multi-run。").classes(
                "text-sm text-gray-500"
            )
            with ui.grid(columns=2).classes("w-full gap-4"):
                self.signer_tasks_input = ui.input(
                    label="Signer 任务（逗号分隔）",
                    placeholder="my_sign, second_sign",
                ).props("outlined")
                self.monitor_task_input = ui.input(
                    label="Monitor 任务",
                    placeholder="my_monitor",
                ).props("outlined")
                self.multi_run_task_input = ui.input(
                    label="Multi-run 的 Signer 任务",
                    placeholder="my_sign",
                ).props("outlined")
                self.multi_accounts_input = ui.input(
                    label="账号列表（逗号分隔）",
                    placeholder="account_a, account_b",
                ).props("outlined")
            self.signer_tasks_hint = ui.label("").classes("text-sm text-gray-500")
            self.monitor_tasks_hint = ui.label("").classes("text-sm text-gray-500")
            with ui.row().classes("gap-2 flex-wrap"):
                ui.button("启动 Signer 持续运行", on_click=self.start_signer_job)
                ui.button("执行 Signer Run Once", on_click=self.start_signer_once)
                ui.button("启动 Monitor", on_click=self.start_monitor_job)
                ui.button("启动 Multi-run", on_click=self.start_multi_run_job)

            ui.separator()
            ui.label("后台任务").classes("text-md font-semibold")
            self.jobs_container = ui.column().classes("w-full gap-3")

            ui.separator()
            with ui.grid(columns=2).classes("w-full gap-4"):
                self.events_area = ui.textarea(label="运行事件", value="").classes(
                    "w-full"
                )
                self.events_area.props("readonly autogrow")
                self.logs_area = ui.textarea(label="捕获日志", value="").classes(
                    "w-full"
                )
                self.logs_area.props("readonly autogrow")

    def _build_llm_card(self) -> None:
        with ui.card().classes("w-full shadow-sm"):
            ui.label("LLM 配置").classes("text-lg font-semibold")
            self.llm_status = ui.label("").classes("text-sm text-gray-500")
            with ui.grid(columns=2).classes("w-full gap-4"):
                self.llm_api_key_input = ui.input(
                    label="OPENAI_API_KEY",
                    password=True,
                    password_toggle_button=True,
                ).props("outlined")
                self.llm_base_url_input = ui.input(
                    label="OPENAI_BASE_URL",
                ).props("outlined")
                self.llm_model_input = ui.input(
                    label="OPENAI_MODEL",
                    value=DEFAULT_MODEL,
                ).props("outlined")
            with ui.row().classes("gap-2"):
                ui.button("加载当前配置", on_click=self.load_llm)
                ui.button("保存配置", color="primary", on_click=self.save_llm)

    def refresh(self) -> None:
        self.refresh_task_hints()
        self.load_llm()
        self.refresh_runtime_views()

    def refresh_task_hints(self) -> None:
        signer_tasks = ", ".join(list_task_names("signer", state.workdir)) or "暂无"
        monitor_tasks = ", ".join(list_task_names("monitor", state.workdir)) or "暂无"
        self.signer_tasks_hint.text = f"当前 signer 任务: {signer_tasks}"
        self.monitor_tasks_hint.text = f"当前 monitor 任务: {monitor_tasks}"
        self.signer_tasks_hint.update()
        self.monitor_tasks_hint.update()

    def refresh_runtime_views(self) -> None:
        pending = runtime.pending_login_status()
        if pending == "code_sent":
            self.pending_status.text = "当前账号有待提交的验证码。"
        elif pending == "password_required":
            self.pending_status.text = "当前账号需要提交二步验证密码。"
        else:
            self.pending_status.text = ""
        self.pending_status.update()
        self.refresh_jobs()
        self.events_area.value = "\n".join(runtime.recent_events())
        self.events_area.update()
        self.logs_area.value = "\n".join(runtime.recent_logs())
        self.logs_area.update()

    def refresh_jobs(self) -> None:
        self.jobs_container.clear()
        jobs = runtime.list_jobs()
        with self.jobs_container:
            if not jobs:
                ui.label("当前没有后台任务。").classes("text-sm text-gray-500")
                return
            for job in jobs:
                with ui.card().classes("w-full shadow-sm"):
                    with ui.row().classes("w-full items-start justify-between"):
                        with ui.column().classes("gap-1"):
                            ui.label(job.label).classes("font-semibold")
                            ui.label(
                                f"状态: {job.status} | 账号: {', '.join(job.accounts)}"
                            ).classes("text-sm text-gray-600")
                            ui.label(
                                f"任务: {', '.join(job.task_names)} | 开始: {job.started_at:%Y-%m-%d %H:%M:%S}"
                            ).classes("text-sm text-gray-600")
                            if job.finished_at:
                                ui.label(
                                    f"结束: {job.finished_at:%Y-%m-%d %H:%M:%S}"
                                ).classes("text-sm text-gray-600")
                            if job.error:
                                ui.label(f"错误: {job.error}").classes(
                                    "text-sm text-negative"
                                )
                        if job.status == "running":
                            async def stop_current(job_id=job.job_id):
                                await self.stop_job(job_id)

                            ui.button(
                                "停止",
                                color="negative",
                                on_click=stop_current,
                            )

    def apply_runtime(self) -> None:
        try:
            runtime.apply_settings(
                account=self.account_input.value,
                session_dir=self.session_dir_input.value,
                proxy=self.proxy_input.value,
                session_string=self.session_string_input.value,
                in_memory=self.in_memory_input.value,
                num_of_dialogs=int(self.num_dialogs_input.value or 20),
                log_level=self.log_level_input.value,
                log_dir=self.log_dir_input.value,
                log_file=self.log_file_input.value,
            )
            state.set_log_path(self.log_file_input.value or str(DEFAULT_LOG_FILE))
            ui.notify("运行时设置已更新", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def check_auth_status(self) -> None:
        try:
            status = await runtime.fetch_account_status(state.workdir)
            if status["authorized"]:
                user_label = status.get("username") or status.get("first_name") or ""
                self.auth_status.text = (
                    f"已登录: {status['user_id']} {user_label}".strip()
                )
            else:
                self.auth_status.text = "当前账号未登录"
            self.auth_status.update()
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def begin_login(self) -> None:
        try:
            result = await runtime.begin_login(state.workdir, self.phone_input.value)
            if result["status"] == "authorized":
                self.auth_status.text = (
                    f"已登录: {result['user_id']} {result.get('username') or result.get('first_name') or ''}".strip()
                )
            else:
                self.auth_status.text = "验证码已发送，请继续提交验证码"
            self.auth_status.update()
            ui.notify("登录流程已开始", type="positive")
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def submit_code(self) -> None:
        try:
            result = await runtime.verify_login_code(self.code_input.value)
            if result["status"] == "password_required":
                self.auth_status.text = "需要二步验证密码"
            else:
                self.auth_status.text = (
                    f"已登录: {result['user_id']} {result.get('username') or result.get('first_name') or ''}".strip()
                )
            self.auth_status.update()
            ui.notify("验证码已提交", type="positive")
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def submit_password(self) -> None:
        try:
            result = await runtime.submit_password(self.password_input.value)
            self.auth_status.text = (
                f"已登录: {result['user_id']} {result.get('username') or result.get('first_name') or ''}".strip()
            )
            self.auth_status.update()
            ui.notify("二步验证完成", type="positive")
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def logout(self) -> None:
        try:
            await runtime.logout(state.workdir)
            self.auth_status.text = "当前账号已退出登录"
            self.auth_status.update()
            ui.notify("已退出登录", type="positive")
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def send_text(self) -> None:
        try:
            chat_id = normalize_chat_target(self.send_chat_input.value)
            await runtime.send_text(
                state.workdir,
                chat_id,
                self.send_text_input.value or "",
                delete_after=optional_int(self.send_delete_after_input.value),
            )
            ui.notify("文本已发送", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def send_dice(self) -> None:
        try:
            chat_id = normalize_chat_target(self.send_chat_input.value)
            await runtime.send_dice(
                state.workdir,
                chat_id,
                self.dice_select.value,
                delete_after=optional_int(self.send_delete_after_input.value),
            )
            ui.notify("Dice 已发送", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def load_members(self) -> None:
        try:
            rows = await runtime.list_members(
                state.workdir,
                normalize_chat_target(self.members_chat_input.value),
                query=self.members_query_input.value or "",
                admin=bool(self.members_admin_input.value),
                limit=int(self.members_limit_input.value or 10),
            )
            self.members_table.rows = rows
            self.members_table.update()
            ui.notify(f"共加载 {len(rows)} 条成员记录", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def create_schedule(self) -> None:
        try:
            rows = await runtime.schedule_messages(
                state.workdir,
                normalize_chat_target(self.schedule_chat_input.value),
                self.schedule_text_input.value or "",
                self.schedule_crontab_input.value or "",
                next_times=int(self.schedule_next_input.value or 1),
                random_seconds=int(self.schedule_random_input.value or 0),
            )
            self.schedule_table.rows = [
                {"message_id": "-", "date": row["at"], "text": row["text"]}
                for row in rows
            ]
            self.schedule_table.update()
            ui.notify(f"已创建 {len(rows)} 条定时消息", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def load_schedules(self) -> None:
        try:
            rows = await runtime.list_scheduled_messages(
                state.workdir,
                normalize_chat_target(self.schedule_list_chat_input.value),
            )
            self.schedule_table.rows = rows
            self.schedule_table.update()
            ui.notify(f"加载到 {len(rows)} 条已配置消息", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def start_signer_job(self) -> None:
        try:
            runtime.start_signer_job(
                state.workdir,
                comma_items(self.signer_tasks_input.value),
                only_once=False,
            )
            ui.notify("Signer 持续任务已启动", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def start_signer_once(self) -> None:
        try:
            runtime.start_signer_job(
                state.workdir,
                comma_items(self.signer_tasks_input.value),
                only_once=True,
                force_rerun=True,
            )
            ui.notify("Signer run-once 已加入后台任务", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def start_monitor_job(self) -> None:
        try:
            runtime.start_monitor_job(state.workdir, self.monitor_task_input.value or "")
            ui.notify("Monitor 已启动", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def start_multi_run_job(self) -> None:
        try:
            runtime.start_multi_run_job(
                state.workdir,
                self.multi_run_task_input.value or "",
                comma_items(self.multi_accounts_input.value),
            )
            ui.notify("Multi-run 已启动", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    async def stop_job(self, job_id: str) -> None:
        try:
            await runtime.stop_job(job_id)
            ui.notify("后台任务已停止", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)

    def load_llm(self) -> None:
        cfg = load_llm_config(state.workdir)
        if not cfg:
            self.llm_api_key_input.value = ""
            self.llm_base_url_input.value = ""
            self.llm_model_input.value = DEFAULT_MODEL
            self.llm_status.text = "当前工作目录下还没有 LLM 配置文件。"
        else:
            self.llm_api_key_input.value = cfg.api_key
            self.llm_base_url_input.value = cfg.base_url or ""
            self.llm_model_input.value = cfg.model or DEFAULT_MODEL
            source = "环境变量" if cfg.from_env else "本地配置文件"
            self.llm_status.text = f"已加载 {source} 中的 LLM 配置。"
        self.llm_api_key_input.update()
        self.llm_base_url_input.update()
        self.llm_model_input.update()
        self.llm_status.update()

    def save_llm(self) -> None:
        try:
            if not (self.llm_api_key_input.value or "").strip():
                raise ValueError("OPENAI_API_KEY 不能为空")
            path = save_llm_config(
                self.llm_api_key_input.value or "",
                base_url=self.llm_base_url_input.value or None,
                model=self.llm_model_input.value or DEFAULT_MODEL,
                workdir=state.workdir,
            )
            self.llm_status.text = f"LLM 配置已保存到 {path}"
            self.llm_status.update()
            ui.notify("LLM 配置已保存", type="positive")
        except Exception as exc:  # noqa: BLE001
            notify_error(exc)


def top_controls(on_refresh: Callable[[], None]) -> None:
    with ui.card().classes("w-full shadow-sm"):
        ui.label("基础设置").classes("text-lg font-semibold")
        with ui.row().classes("items-end w-full gap-3 flex-wrap"):
            workdir_input = ui.input(
                label="工作目录",
                value=str(state.workdir),
                placeholder=".signer",
            ).classes("w-full")

            def apply() -> None:
                try:
                    state.set_workdir(workdir_input.value or str(DEFAULT_WORKDIR))
                    ui.notify(f"工作目录已切换到 {state.workdir}", type="positive")
                    on_refresh()
                except Exception as exc:  # noqa: BLE001
                    notify_error(exc)

            ui.button("应用并刷新", color="primary", on_click=apply)


def _build_dashboard(container) -> None:
    with container:
        ui.label("TG Signer Web 控制台").classes("text-2xl font-semibold")
        ui.label(f"Version {__version__}").classes("text-sm text-gray-500")

        refreshers: list[Callable[[], None]] = []
        refresh_records: SignRecordBlock

        def refresh_all() -> None:
            for refresh in refreshers:
                refresh()

        top_controls(refresh_all)

        with ui.tabs().classes("w-full") as tabs:
            tab_login = ui.tab("登录")
            tab_run_cfg = ui.tab("运行配置")
            tab_ops = ui.tab("即时操作")
            tab_llm = ui.tab("LLM配置")
            tab_configs = ui.tab("配置")
            tab_users = ui.tab("用户")
            tab_records = ui.tab("记录")
            tab_logs = ui.tab("日志")

        def goto_records(task_name: str) -> None:
            tabs.value = tab_records
            tabs.update()
            refresh_records.filter_input.set_value(task_name)

        with ui.tab_panels(tabs, value=tab_login).classes("w-full"):
            with ui.tab_panel(tab_login):
                login_panel = LoginPanel(state, runtime, notify_error, refresh_all)
                refreshers.append(login_panel)

            with ui.tab_panel(tab_run_cfg):
                run_cfg_panel = RunConfigPanel(state, runtime, notify_error, refresh_all)
                refreshers.append(run_cfg_panel)

            with ui.tab_panel(tab_ops):
                ops_panel = ImmediateOpsPanel(state, runtime, notify_error)
                refreshers.append(ops_panel)

            with ui.tab_panel(tab_llm):
                llm_panel = LLMConfigPanel(state, notify_error, refresh_all)
                refreshers.append(llm_panel)

            with ui.tab_panel(tab_configs):
                ui.label("在页面中直接管理 signer / monitor 配置。").classes(
                    "text-gray-600"
                )
                with ui.tabs().classes("mt-2") as sub_tabs:
                    tab_signer = ui.tab("Signer")
                    tab_monitor = ui.tab("Monitor")
                with ui.tab_panels(sub_tabs, value=tab_signer).classes("w-full"):
                    with ui.tab_panel(tab_signer):
                        refreshers.append(
                            SignerBlock(SIGNER_TEMPLATE, goto_records=goto_records)
                        )
                    with ui.tab_panel(tab_monitor):
                        refreshers.append(MonitorBlock(MONITOR_TEMPLATE))

            with ui.tab_panel(tab_users):
                ui.label("显示当前工作目录下已缓存的用户信息和 recent chats。").classes(
                    "text-gray-600"
                )
                refreshers.append(user_info_block())

            with ui.tab_panel(tab_records):
                ui.label("显示 signs/*/sign_record.json 中的签到记录。").classes(
                    "text-gray-600"
                )
                refresh_records = SignRecordBlock()
                refreshers.append(refresh_records)

            with ui.tab_panel(tab_logs):
                ui.label("查看日志文件中的最新输出。").classes("text-gray-600")
                refreshers.append(log_block())

        refresh_all()


def _auth_gate(container, auth_code: str, on_success: Callable[[], None]) -> None:
    with container:
        ui.label("TG Signer Web 控制台").classes("text-2xl font-semibold")
        ui.label("当前已启用访问码保护，请先输入 Auth Code。").classes(
            "text-gray-600"
        )
        with ui.card().classes("w-full max-w-xl shadow-md"):
            ui.label("Auth Code 验证").classes("text-lg font-semibold")
            code_input = ui.input(
                label="Auth Code",
                password=True,
                password_toggle_button=True,
            ).classes("w-full")
            status = ui.label("").classes("text-sm text-negative")

            def verify() -> None:
                code = (code_input.value or "").strip()
                if not code:
                    ui.notify("请输入 Auth Code", type="warning")
                    return
                if code != auth_code:
                    status.text = "Auth Code 错误，请重试。"
                    status.update()
                    code_input.set_value("")
                    ui.notify("认证失败", type="negative")
                    return
                app.storage.user[AUTH_STORAGE_KEY] = auth_code
                container.clear()
                on_success()

            ui.button("验证并进入", color="primary", on_click=verify).classes(
                "w-full mt-2"
            )


def build_ui(auth_code: str = None) -> None:
    ui.page_title("TG Signer Web Console")
    root = ui.column().classes("w-full gap-3")

    def render_dashboard() -> None:
        root.clear()
        _build_dashboard(root)

    auth_code = auth_code or (os.environ.get(AUTH_CODE_ENV) or "").strip()
    if not auth_code:
        render_dashboard()
        return

    if app.storage.user.get(AUTH_STORAGE_KEY) == auth_code:
        render_dashboard()
        return

    root.clear()
    _auth_gate(root, auth_code, render_dashboard)


def main(host: str = None, port: int = None, storage_secret: str = None) -> None:
    ui.run(
        build_ui,
        title="TG Signer WebUI",
        reload=False,
        host=host,
        port=port,
        show=False,
        storage_secret=storage_secret or os.urandom(10).hex(),
    )
