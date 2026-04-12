from typing import Callable

from nicegui import ui

from tg_signer.ai_tools import DEFAULT_MODEL
from tg_signer.core import DICE_EMOJIS
from tg_signer.webui.data import (
    load_keepalive_config,
    load_llm_config,
    list_session_accounts,
    list_task_names,
    save_keepalive_config,
    save_llm_config,
)


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


def optional_int(value) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


class LoginPanel:
    def __init__(self, state, runtime, notify_error, on_global_refresh: Callable[[], None]):
        self.state = state
        self.runtime = runtime
        self.notify_error = notify_error
        self.on_global_refresh = on_global_refresh
        self.account_select = None
        self.account_hint = None
        self.auth_status = None
        self.pending_status = None
        self._build()
        ui.timer(1.0, self.refresh_status_only)

    def __call__(self, *args, **kwargs):
        self.refresh()

    def _build(self) -> None:
        initial_account = (self.runtime.settings.account or "my_account").strip() or "my_account"
        with ui.card().classes("w-full shadow-sm"):
            ui.label("登录").classes("text-lg font-semibold")
            ui.label("这里只负责账号登录、session 目录和登录相关设置。").classes(
                "text-sm text-gray-500"
            )
            with ui.grid(columns=2).classes("w-full gap-4"):
                self.account_select = ui.input(
                    label="账号",
                    placeholder="例如 xiaohao",
                    value=initial_account,
                ).props("outlined")
                self.session_dir_input = ui.input(
                    label="Session 目录",
                    value=str(self.runtime.settings.session_dir),
                ).props("outlined")
                self.proxy_input = ui.input(
                    label="代理",
                    value=self.runtime.settings.proxy,
                    placeholder="socks5://127.0.0.1:7890",
                ).props("outlined")
                self.num_dialogs_input = ui.number(
                    label="最近对话数量",
                    value=self.runtime.settings.num_of_dialogs,
                    min=1,
                    format="%d",
                ).props("outlined")
                self.in_memory_input = ui.checkbox(
                    "Session 仅保存在内存",
                    value=self.runtime.settings.in_memory,
                )
            with ui.expansion("高级登录设置").classes("w-full"):
                self.account_hint = ui.label("").classes("text-xs text-gray-500")
                self.session_string_input = ui.textarea(
                    label="Session String",
                    value=self.runtime.settings.session_string,
                    placeholder="可选，用于覆盖本地 session 文件",
                ).classes("w-full")

            with ui.row().classes("w-full justify-end"):
                ui.button("应用登录设置", color="primary", on_click=self.apply_settings)

            self.auth_status = ui.label("尚未检查账号状态").classes(
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

    def refresh(self) -> None:
        accounts = list_session_accounts(self.session_dir_input.value)
        current = (self.account_select.value or self.runtime.settings.account or "").strip()
        self.account_select.value = current or (accounts[0] if accounts else "my_account")
        self.account_select.update()
        existing = ", ".join(accounts) if accounts else "暂无"
        self.account_hint.text = (
            f"这里填写你自定义的账号别名，会生成对应的 session 文件，例如 xiaohao.session。当前已存在账号: {existing}"
        )
        self.account_hint.update()
        self.refresh_status_only()

    def refresh_status_only(self) -> None:
        pending = self.runtime.pending_login_status()
        if pending == "code_sent":
            self.pending_status.text = "当前账号有待提交的验证码。"
        elif pending == "password_required":
            self.pending_status.text = "当前账号需要提交二步验证密码。"
        else:
            self.pending_status.text = ""
        self.pending_status.update()

    def apply_settings(self) -> None:
        try:
            self.runtime.apply_settings(
                account=self.account_select.value,
                session_dir=self.session_dir_input.value,
                proxy=self.proxy_input.value,
                session_string=self.session_string_input.value,
                in_memory=self.in_memory_input.value,
                num_of_dialogs=int(self.num_dialogs_input.value or 20),
            )
            ui.notify("登录设置已更新", type="positive")
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def check_auth_status(self) -> None:
        try:
            self.apply_settings()
            status = await self.runtime.fetch_account_status(self.state.workdir)
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
            self.notify_error(exc)

    async def begin_login(self) -> None:
        try:
            self.apply_settings()
            result = await self.runtime.begin_login(self.state.workdir, self.phone_input.value)
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
            self.notify_error(exc)

    async def submit_code(self) -> None:
        try:
            result = await self.runtime.verify_login_code(self.code_input.value)
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
            self.notify_error(exc)

    async def submit_password(self) -> None:
        try:
            result = await self.runtime.submit_password(self.password_input.value)
            self.auth_status.text = (
                f"已登录: {result['user_id']} {result.get('username') or result.get('first_name') or ''}".strip()
            )
            self.auth_status.update()
            ui.notify("二步验证完成", type="positive")
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def logout(self) -> None:
        try:
            self.apply_settings()
            await self.runtime.logout(self.state.workdir)
            self.auth_status.text = "当前账号已退出登录"
            self.auth_status.update()
            ui.notify("已退出登录", type="positive")
            self.on_global_refresh()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)


class RunConfigPanel:
    def __init__(self, state, runtime, notify_error, on_global_refresh: Callable[[], None]):
        self.state = state
        self.runtime = runtime
        self.notify_error = notify_error
        self.on_global_refresh = on_global_refresh
        self.account_select = None
        self.signer_select = None
        self.monitor_select = None
        self.status_label = None
        self.running_label = None
        self.save_button = None
        self.start_all_button = None
        self.start_signer_button = None
        self.start_monitor_button = None
        self.stop_button = None
        self.jobs_container = None
        self.events_area = None
        self.logs_area = None
        self._build()
        ui.timer(1.0, self.refresh_runtime_views)

    def __call__(self, *args, **kwargs):
        self.refresh()

    def _build(self) -> None:
        initial_account = (self.runtime.settings.account or "my_account").strip() or "my_account"
        with ui.card().classes("w-full shadow-sm"):
            ui.label("运行配置").classes("text-lg font-semibold")
            ui.label("这里只选择运行账号，以及这个账号需要保活运行哪些 signer / monitor 配置。").classes(
                "text-sm text-gray-500"
            )
            self.status_label = ui.label("").classes("text-sm text-primary")
            self.running_label = ui.label("").classes("text-sm text-gray-600")
            with ui.grid(columns=1).classes("w-full gap-4"):
                self.account_select = ui.select(
                    label="运行账号",
                    options=[initial_account],
                    with_input=True,
                    new_value_mode="add-unique",
                    clearable=True,
                    value=initial_account,
                ).props("outlined")
                self.signer_select = ui.select(
                    label="保活运行的 Signer 配置",
                    options=[],
                    multiple=True,
                ).props("outlined use-chips")
                self.monitor_select = ui.select(
                    label="保活运行的 Monitor 配置",
                    options=[],
                    multiple=True,
                ).props("outlined use-chips")
            with ui.row().classes("gap-2 flex-wrap"):
                ui.button("读取已保存运行配置", on_click=self.load_saved)
                self.save_button = ui.button(
                    "保存保活运行配置", color="primary", on_click=self.save_current
                )
                self.start_signer_button = ui.button(
                    "只启动签到配置",
                    color="primary",
                    on_click=self.start_signer_keepalive,
                )
                self.start_monitor_button = ui.button(
                    "只启动监控配置",
                    color="primary",
                    on_click=self.start_monitor_keepalive,
                )
                self.start_all_button = ui.button(
                    "启动全部选中配置",
                    color="primary",
                    on_click=self.start_keepalive,
                )
                self.stop_button = ui.button(
                    "停止当前账号保活任务",
                    color="negative",
                    on_click=self.stop_keepalive_jobs,
                )

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

    def refresh(self) -> None:
        accounts = list_session_accounts(self.runtime.settings.session_dir)
        current_account = (self.account_select.value or self.runtime.settings.account or "").strip()
        if current_account and current_account not in accounts:
            accounts.insert(0, current_account)
        self.account_select.options = accounts
        self.account_select.value = current_account or (accounts[0] if accounts else "my_account")
        self.account_select.update()

        signer_options = list_task_names("signer", self.state.workdir)
        self.signer_select.options = signer_options
        self.signer_select.value = [
            task for task in (self.signer_select.value or []) if task in signer_options
        ]
        self.signer_select.update()
        monitor_options = list_task_names("monitor", self.state.workdir)
        self.monitor_select.options = monitor_options
        self.monitor_select.value = [
            task
            for task in (self.monitor_select.value or [])
            if task in monitor_options
        ]
        self.monitor_select.update()
        self.refresh_runtime_views()

    def load_saved(self) -> None:
        saved = load_keepalive_config(self.state.workdir)
        if not saved:
            self.status_label.text = "当前工作目录还没有保存过保活运行配置。"
            self.status_label.update()
            return
        options = list(self.account_select.options or [])
        if saved.account and saved.account not in options:
            options.insert(0, saved.account)
            self.account_select.options = options
        signer_options = list_task_names("signer", self.state.workdir)
        monitor_options = list_task_names("monitor", self.state.workdir)
        self.signer_select.options = signer_options
        self.monitor_select.options = monitor_options
        self.account_select.value = saved.account
        self.signer_select.value = [
            task for task in saved.signer_tasks if task in signer_options
        ]
        self.monitor_select.value = [
            task for task in saved.monitor_tasks if task in monitor_options
        ]
        self.account_select.update()
        self.signer_select.update()
        self.monitor_select.update()
        self.status_label.text = "已读取保存的保活运行配置。"
        self.status_label.update()

    def save_current(self) -> None:
        try:
            path = save_keepalive_config(
                account=self.account_select.value or "",
                signer_tasks=list(self.signer_select.value or []),
                monitor_tasks=list(self.monitor_select.value or []),
                workdir=self.state.workdir,
            )
            self.status_label.text = f"保活运行配置已保存到 {path}"
            self.status_label.update()
            ui.notify("保活运行配置已保存", type="positive")
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def start_keepalive(self) -> None:
        try:
            self.runtime.start_keepalive_job(
                self.state.workdir,
                account=self.account_select.value or "",
                signer_tasks=list(self.signer_select.value or []),
                monitor_tasks=list(self.monitor_select.value or []),
            )
            ui.notify("保活运行任务已启动", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def start_signer_keepalive(self) -> None:
        try:
            signer_tasks = list(self.signer_select.value or [])
            if not signer_tasks:
                raise ValueError("请至少选择一个签到配置")
            self.runtime.start_keepalive_job(
                self.state.workdir,
                account=self.account_select.value or "",
                signer_tasks=signer_tasks,
                monitor_tasks=[],
            )
            ui.notify("签到保活任务已启动", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def start_monitor_keepalive(self) -> None:
        try:
            monitor_tasks = list(self.monitor_select.value or [])
            if not monitor_tasks:
                raise ValueError("请至少选择一个监控配置")
            self.runtime.start_keepalive_job(
                self.state.workdir,
                account=self.account_select.value or "",
                signer_tasks=[],
                monitor_tasks=monitor_tasks,
            )
            ui.notify("监控保活任务已启动", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def stop_keepalive_jobs(self) -> None:
        try:
            target_account = (self.account_select.value or "").strip()
            keepalive_jobs = [
                job for job in self.runtime.list_jobs() if job.kind == "keepalive"
            ]
            for job in keepalive_jobs:
                if job.status == "running" and (
                    not target_account or target_account in job.accounts
                ):
                    await self.runtime.stop_job(job.job_id)
            ui.notify("当前账号的保活运行任务已停止", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def stop_single_job(self, job_id: str) -> None:
        try:
            await self.runtime.stop_job(job_id)
            ui.notify("后台任务已停止", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def delete_single_job(self, job_id: str) -> None:
        try:
            await self.runtime.delete_job(job_id)
            ui.notify("后台任务已删除", type="positive")
            self.refresh_runtime_views()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    def refresh_runtime_views(self) -> None:
        running = self.runtime.get_running_keepalive_configs(
            self.account_select.value or ""
        )
        signer_text = ", ".join(running["signer_tasks"]) or "无"
        monitor_text = ", ".join(running["monitor_tasks"]) or "无"
        self.running_label.text = (
            f"当前账号正在运行的签到配置: {signer_text} | 监控配置: {monitor_text}"
        )
        self.running_label.update()
        self.events_area.value = "\n".join(self.runtime.recent_events())
        self.events_area.update()
        self.logs_area.value = "\n".join(self.runtime.recent_logs())
        self.logs_area.update()
        self.jobs_container.clear()
        jobs = self.runtime.list_jobs()
        with self.jobs_container:
            if not jobs:
                ui.label("当前没有后台任务。").classes("text-sm text-gray-500")
                return
            for job in jobs:
                with ui.card().classes("w-full shadow-sm"):
                    with ui.column().classes("gap-1"):
                        ui.label(job.label).classes("font-semibold")
                        ui.label(
                            f"状态: {job.status} | 账号: {', '.join(job.accounts)}"
                        ).classes("text-sm text-gray-600")
                        ui.label(
                            f"配置: {', '.join(job.task_names)} | 开始: {job.started_at:%Y-%m-%d %H:%M:%S}"
                        ).classes("text-sm text-gray-600")
                        if job.finished_at:
                            ui.label(
                                f"结束: {job.finished_at:%Y-%m-%d %H:%M:%S}"
                            ).classes("text-sm text-gray-600")
                        if job.error:
                            ui.label(f"错误: {job.error}").classes(
                                "text-sm text-negative"
                            )


                        with ui.row().classes("gap-2 pt-2"):
                            if job.status == "running":
                                ui.button(
                                    "停止",
                                    color="warning",
                                    on_click=lambda job_id=job.job_id: self.stop_single_job(job_id),
                                )
                            ui.button(
                                "删除",
                                color="negative",
                                on_click=lambda job_id=job.job_id: self.delete_single_job(job_id),
                            )


class ImmediateOpsPanel:
    def __init__(self, state, runtime, notify_error):
        self.state = state
        self.runtime = runtime
        self.notify_error = notify_error
        self.account_select = None
        self.members_table = None
        self.schedule_table = None
        self.action_buttons = []
        self.notice = None
        self._build()

    def __call__(self, *args, **kwargs):
        self.refresh()

    def _build(self) -> None:
        initial_account = (self.runtime.settings.account or "my_account").strip() or "my_account"
        with ui.card().classes("w-full shadow-sm"):
            ui.label("即时操作").classes("text-lg font-semibold")
            self.notice = ui.label("").classes("text-sm text-primary")
            self.account_select = ui.select(
                label="使用账号",
                options=[initial_account],
                with_input=True,
                new_value_mode="add-unique",
                clearable=True,
                value=initial_account,
            ).props("outlined").classes("w-full max-w-sm")
            with ui.tabs().classes("w-full") as tabs:
                tab_send = ui.tab("发送消息")
                tab_members = ui.tab("成员查询")
                tab_schedule = ui.tab("定时消息")
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
                        btn_text = ui.button(
                            "发送文本", color="primary", on_click=self.send_text
                        )
                        self.action_buttons.append(btn_text)
                        self.dice_select = ui.select(
                            label="Dice Emoji",
                            options=list(DICE_EMOJIS),
                            value=DICE_EMOJIS[0],
                        ).classes("min-w-[180px]")
                        btn_dice = ui.button("发送 Dice", on_click=self.send_dice)
                        self.action_buttons.append(btn_dice)

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
                    btn_members = ui.button(
                        "查询成员", color="primary", on_click=self.load_members
                    )
                    self.action_buttons.append(btn_members)
                    self.members_table = ui.table(
                        columns=[
                            {"name": "id", "label": "ID", "field": "id"},
                            {"name": "username", "label": "用户名", "field": "username"},
                            {"name": "first_name", "label": "First Name", "field": "first_name"},
                            {"name": "last_name", "label": "Last Name", "field": "last_name"},
                            {"name": "status", "label": "状态", "field": "status"},
                            {"name": "is_bot", "label": "Bot", "field": "is_bot"},
                        ],
                        rows=[],
                        pagination=10,
                    ).classes("w-full").props("flat dense")

                with ui.tab_panel(tab_schedule):
                    with ui.tabs().classes("w-full") as sub_tabs:
                        tab_create = ui.tab("批量创建")
                        tab_list = ui.tab("查看已配置")
                    with ui.tab_panels(sub_tabs, value=tab_create).classes("w-full"):
                        with ui.tab_panel(tab_create):
                            with ui.grid(columns=2).classes("w-full gap-4"):
                                self.schedule_chat_input = ui.input(
                                    label="聊天 ID / @username"
                                ).props("outlined")
                                self.schedule_crontab_input = ui.input(
                                    label="Crontab", value="0 6 * * *"
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
                            btn_create = ui.button(
                                "创建定时消息",
                                color="primary",
                                on_click=self.create_schedule,
                            )
                            self.action_buttons.append(btn_create)
                        with ui.tab_panel(tab_list):
                            with ui.row().classes("items-end gap-3 flex-wrap"):
                                self.schedule_list_chat_input = ui.input(
                                    label="聊天 ID / @username"
                                ).props("outlined")
                                btn_list = ui.button(
                                    "加载已配置消息",
                                    color="primary",
                                    on_click=self.load_schedules,
                                )
                                self.action_buttons.append(btn_list)
                            self.schedule_table = ui.table(
                                columns=[
                                    {"name": "message_id", "label": "Message ID", "field": "message_id"},
                                    {"name": "date", "label": "发送时间", "field": "date"},
                                    {"name": "text", "label": "内容", "field": "text"},
                                ],
                                rows=[],
                                pagination=10,
                            ).classes("w-full").props("flat dense")

    def refresh(self) -> None:
        accounts = list_session_accounts(self.runtime.settings.session_dir)
        current_account = (self.account_select.value or self.runtime.settings.account or "").strip()
        if current_account and current_account not in accounts:
            accounts.insert(0, current_account)
        self.account_select.options = accounts
        self.account_select.value = current_account or (accounts[0] if accounts else "my_account")
        self.account_select.update()

        cfg = load_llm_config(self.state.workdir)
        ready = bool(cfg and (cfg.api_key or "").strip())
        self.notice.text = (
            "当前未配置 LLM。普通即时操作仍可使用，只有 AI 相关能力不可用。"
            if not ready
            else "当前已配置 LLM。"
        )
        self.notice.update()
        for button in self.action_buttons:
            button.enable()
            button.update()

    async def send_text(self) -> None:
        try:
            await self.runtime.send_text(
                self.state.workdir,
                normalize_chat_target(self.send_chat_input.value),
                self.send_text_input.value or "",
                delete_after=optional_int(self.send_delete_after_input.value),
                account=self.account_select.value or "",
            )
            ui.notify("文本已发送", type="positive")
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def send_dice(self) -> None:
        try:
            await self.runtime.send_dice(
                self.state.workdir,
                normalize_chat_target(self.send_chat_input.value),
                self.dice_select.value,
                delete_after=optional_int(self.send_delete_after_input.value),
                account=self.account_select.value or "",
            )
            ui.notify("Dice 已发送", type="positive")
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def load_members(self) -> None:
        try:
            rows = await self.runtime.list_members(
                self.state.workdir,
                normalize_chat_target(self.members_chat_input.value),
                query=self.members_query_input.value or "",
                admin=bool(self.members_admin_input.value),
                limit=int(self.members_limit_input.value or 10),
                account=self.account_select.value or "",
            )
            self.members_table.rows = rows
            self.members_table.update()
            ui.notify(f"共加载 {len(rows)} 条成员记录", type="positive")
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def create_schedule(self) -> None:
        try:
            rows = await self.runtime.schedule_messages(
                self.state.workdir,
                normalize_chat_target(self.schedule_chat_input.value),
                self.schedule_text_input.value or "",
                self.schedule_crontab_input.value or "",
                next_times=int(self.schedule_next_input.value or 1),
                random_seconds=int(self.schedule_random_input.value or 0),
                account=self.account_select.value or "",
            )
            self.schedule_table.rows = [
                {"message_id": "-", "date": row["at"], "text": row["text"]}
                for row in rows
            ]
            self.schedule_table.update()
            ui.notify(f"已创建 {len(rows)} 条定时消息", type="positive")
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)

    async def load_schedules(self) -> None:
        try:
            rows = await self.runtime.list_scheduled_messages(
                self.state.workdir,
                normalize_chat_target(self.schedule_list_chat_input.value),
                account=self.account_select.value or "",
            )
            self.schedule_table.rows = rows
            self.schedule_table.update()
            ui.notify(f"加载到 {len(rows)} 条已配置消息", type="positive")
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)


class LLMConfigPanel:
    def __init__(self, state, notify_error, on_change: Callable[[], None]):
        self.state = state
        self.notify_error = notify_error
        self.on_change = on_change
        self.status = None
        self._build()

    def __call__(self, *args, **kwargs):
        self.refresh()

    def _build(self) -> None:
        with ui.card().classes("w-full shadow-sm"):
            ui.label("LLM配置").classes("text-lg font-semibold")
            self.status = ui.label("").classes("text-sm text-primary")
            with ui.grid(columns=2).classes("w-full gap-4"):
                self.api_key_input = ui.input(
                    label="OPENAI_API_KEY",
                    password=True,
                    password_toggle_button=True,
                ).props("outlined")
                self.base_url_input = ui.input(
                    label="OPENAI_BASE_URL",
                ).props("outlined")
                self.model_input = ui.input(
                    label="OPENAI_MODEL",
                    value=DEFAULT_MODEL,
                ).props("outlined")
            with ui.row().classes("gap-2"):
                ui.button("加载当前配置", on_click=self.refresh)
                ui.button("保存配置", color="primary", on_click=self.save)

    def refresh(self) -> None:
        cfg = load_llm_config(self.state.workdir)
        if not cfg:
            self.api_key_input.value = ""
            self.base_url_input.value = ""
            self.model_input.value = DEFAULT_MODEL
            self.status.text = "当前工作目录还没有 LLM 配置。LLM 是可选的，不配置程序也可以运行。"
        else:
            self.api_key_input.value = cfg.api_key
            self.base_url_input.value = cfg.base_url or ""
            self.model_input.value = cfg.model or DEFAULT_MODEL
            source = "环境变量" if cfg.from_env else "本地配置文件"
            self.status.text = f"已加载 {source} 中的 LLM 配置。"
        self.api_key_input.update()
        self.base_url_input.update()
        self.model_input.update()
        self.status.update()

    def save(self) -> None:
        try:
            if not (self.api_key_input.value or "").strip():
                raise ValueError("OPENAI_API_KEY 不能为空")
            path = save_llm_config(
                self.api_key_input.value or "",
                base_url=self.base_url_input.value or None,
                model=self.model_input.value or DEFAULT_MODEL,
                workdir=self.state.workdir,
            )
            self.status.text = f"LLM 配置已保存到 {path}"
            self.status.update()
            ui.notify("LLM 配置已保存", type="positive")
            self.on_change()
        except Exception as exc:  # noqa: BLE001
            self.notify_error(exc)
