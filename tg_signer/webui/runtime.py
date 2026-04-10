import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable, Optional

from pyrogram import errors

from tg_signer.ai_tools import DEFAULT_MODEL
from tg_signer.core import DICE_EMOJIS, UserMonitor, UserSigner, get_proxy
from tg_signer.logger import configure_logger


@dataclass
class WebRuntimeSettings:
    account: str = "my_account"
    session_dir: Path = Path(".")
    proxy: str = ""
    session_string: str = ""
    in_memory: bool = False
    num_of_dialogs: int = 20
    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    log_file: Path = Path("logs") / "tg-signer.log"


@dataclass
class PendingLogin:
    worker: UserSigner
    phone_number: str
    phone_code_hash: str
    created_at: datetime = field(default_factory=datetime.now)
    requires_password: bool = False


@dataclass
class BackgroundJob:
    job_id: str
    kind: str
    label: str
    accounts: list[str]
    task_names: list[str]
    signer_tasks: list[str] = field(default_factory=list)
    monitor_tasks: list[str] = field(default_factory=list)
    status: str = "running"
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    task: Optional[asyncio.Task] = field(default=None, repr=False)


class MemoryLogHandler(logging.Handler):
    def __init__(self, max_lines: int = 500):
        super().__init__()
        self.max_lines = max_lines
        self.lines: deque[str] = deque(maxlen=max_lines)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # noqa: BLE001
            self.handleError(record)


class TGWebRuntime:
    def __init__(self) -> None:
        self.settings = WebRuntimeSettings()
        self.pending_logins: dict[str, PendingLogin] = {}
        self.jobs: dict[str, BackgroundJob] = {}
        self.events: deque[str] = deque(maxlen=200)
        self._job_index = 0
        self.log_handler = MemoryLogHandler()
        self.apply_settings()

    def apply_settings(
        self,
        *,
        account: Optional[str] = None,
        session_dir: Optional[str | Path] = None,
        proxy: Optional[str] = None,
        session_string: Optional[str] = None,
        in_memory: Optional[bool] = None,
        num_of_dialogs: Optional[int] = None,
        log_level: Optional[str] = None,
        log_dir: Optional[str | Path] = None,
        log_file: Optional[str | Path] = None,
    ) -> WebRuntimeSettings:
        if account is not None:
            self.settings.account = account.strip() or "my_account"
        if session_dir is not None:
            self.settings.session_dir = Path(session_dir).expanduser()
        if proxy is not None:
            self.settings.proxy = proxy.strip()
        if session_string is not None:
            self.settings.session_string = session_string.strip()
        if in_memory is not None:
            self.settings.in_memory = bool(in_memory)
        if num_of_dialogs is not None:
            self.settings.num_of_dialogs = max(int(num_of_dialogs), 1)
        if log_level is not None:
            self.settings.log_level = log_level.upper()
        if log_dir is not None:
            self.settings.log_dir = Path(log_dir).expanduser()
        if log_file is not None:
            self.settings.log_file = Path(log_file).expanduser()

        logger = configure_logger(
            log_level=self.settings.log_level,
            log_dir=self.settings.log_dir,
            log_file=self.settings.log_file,
        )
        self.log_handler.setFormatter(
            logging.Formatter(
                "[%(levelname)s] [%(name)s] %(asctime)s %(filename)s %(lineno)s %(message)s"
            )
        )
        if not any(h is self.log_handler for h in logger.handlers):
            logger.addHandler(self.log_handler)
        self._event(
            f"Web runtime updated: account={self.settings.account}, session_dir={self.settings.session_dir}"
        )
        return self.settings

    def _event(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.events.appendleft(line)
        logging.getLogger("tg-signer").info("[webui] %s", message)

    def recent_events(self) -> list[str]:
        return list(self.events)

    def recent_logs(self) -> list[str]:
        return list(self.log_handler.lines)

    def _account_key(self, account: Optional[str] = None) -> str:
        account_name = account or self.settings.account
        return f"{self.settings.session_dir.resolve()}::{account_name}"

    def _build_signer(
        self,
        workdir: Path,
        *,
        task_name: Optional[str] = None,
        account: Optional[str] = None,
    ) -> UserSigner:
        return UserSigner(
            task_name=task_name,
            account=account or self.settings.account,
            proxy=get_proxy(self.settings.proxy),
            session_dir=self.settings.session_dir,
            workdir=workdir,
            session_string=self.settings.session_string or None,
            in_memory=self.settings.in_memory,
        )

    def _build_monitor(
        self,
        workdir: Path,
        *,
        task_name: Optional[str] = None,
        account: Optional[str] = None,
    ) -> UserMonitor:
        return UserMonitor(
            task_name=task_name,
            account=account or self.settings.account,
            proxy=get_proxy(self.settings.proxy),
            session_dir=self.settings.session_dir,
            workdir=workdir,
            session_string=self.settings.session_string or None,
            in_memory=self.settings.in_memory,
        )

    async def _disconnect_client(self, client) -> None:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    async def _disconnect_worker(self, worker: UserSigner) -> None:
        await self._disconnect_client(worker.app)

    async def _ensure_authorized_worker(self, worker) -> None:
        try:
            authorized = await worker.app.connect()
            if not authorized:
                raise ValueError("Current account is not logged in. Please log in from the Web page first.")
            await worker.sync_login_state(
                num_of_dialogs=self.settings.num_of_dialogs,
                print_chat=False,
            )
        finally:
            await self._disconnect_client(worker.app)

    async def _ensure_authorized_account(
        self, workdir: Path, account: str
    ) -> None:
        worker = self._build_signer(workdir, account=account)
        await self._ensure_authorized_worker(worker)

    async def fetch_account_status(self, workdir: Path) -> dict[str, object]:
        worker = self._build_signer(workdir)
        try:
            authorized = await worker.app.connect()
            if not authorized:
                return {
                    "authorized": False,
                    "account": self.settings.account,
                    "session_dir": str(self.settings.session_dir),
                }
            me = await worker.sync_login_state(
                num_of_dialogs=self.settings.num_of_dialogs,
                print_chat=False,
            )
            self._event(f"Account {self.settings.account} authenticated as {me.id}")
            return {
                "authorized": True,
                "account": self.settings.account,
                "session_dir": str(self.settings.session_dir),
                "user_id": me.id,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
            }
        finally:
            await self._disconnect_worker(worker)

    async def begin_login(self, workdir: Path, phone_number: str) -> dict[str, object]:
        phone_number = phone_number.strip()
        if not phone_number:
            raise ValueError("Phone number is required")

        key = self._account_key()
        if key in self.pending_logins:
            pending = self.pending_logins.pop(key)
            await self._disconnect_worker(pending.worker)

        worker = self._build_signer(workdir)
        try:
            authorized = await worker.app.connect()
            if authorized:
                me = await worker.sync_login_state(
                    num_of_dialogs=self.settings.num_of_dialogs,
                    print_chat=False,
                )
                await self._disconnect_worker(worker)
                self._event(f"Account {self.settings.account} is already logged in")
                return {
                    "status": "authorized",
                    "user_id": me.id,
                    "username": me.username,
                    "first_name": me.first_name,
                }

            sent_code = await worker.app.send_code(phone_number)
            self.pending_logins[key] = PendingLogin(
                worker=worker,
                phone_number=phone_number,
                phone_code_hash=sent_code.phone_code_hash,
            )
            self._event(f"Verification code sent for account {self.settings.account}")
            return {
                "status": "code_sent",
                "phone_number": phone_number,
                "sent_type": str(getattr(sent_code, "type", "")),
                "next_type": str(getattr(sent_code, "next_type", "")),
                "timeout": getattr(sent_code, "timeout", None),
            }
        except Exception:
            await self._disconnect_worker(worker)
            raise

    async def verify_login_code(self, code: str) -> dict[str, object]:
        key = self._account_key()
        pending = self.pending_logins.get(key)
        if pending is None:
            raise ValueError("No pending login flow for the current account")

        code = code.strip().replace(" ", "")
        if not code:
            raise ValueError("Verification code is required")

        try:
            await pending.worker.app.sign_in(
                pending.phone_number,
                pending.phone_code_hash,
                code,
            )
        except errors.SessionPasswordNeeded:
            pending.requires_password = True
            self._event(f"2FA password required for account {self.settings.account}")
            return {"status": "password_required"}

        me = await pending.worker.sync_login_state(
            num_of_dialogs=self.settings.num_of_dialogs,
            print_chat=False,
        )
        await self._disconnect_worker(pending.worker)
        self.pending_logins.pop(key, None)
        self._event(f"Login completed for account {self.settings.account}")
        return {
            "status": "authorized",
            "user_id": me.id,
            "username": me.username,
            "first_name": me.first_name,
        }

    async def submit_password(self, password: str) -> dict[str, object]:
        key = self._account_key()
        pending = self.pending_logins.get(key)
        if pending is None:
            raise ValueError("No pending login flow for the current account")
        if not password:
            raise ValueError("Password is required")

        await pending.worker.app.check_password(password)
        me = await pending.worker.sync_login_state(
            num_of_dialogs=self.settings.num_of_dialogs,
            print_chat=False,
        )
        await self._disconnect_worker(pending.worker)
        self.pending_logins.pop(key, None)
        self._event(f"2FA login completed for account {self.settings.account}")
        return {
            "status": "authorized",
            "user_id": me.id,
            "username": me.username,
            "first_name": me.first_name,
        }

    async def logout(self, workdir: Path) -> None:
        key = self._account_key()
        pending = self.pending_logins.pop(key, None)
        if pending is not None:
            await self._disconnect_worker(pending.worker)

        worker = self._build_signer(workdir)
        await worker.logout()
        self._event(f"Logged out account {self.settings.account}")

    async def send_text(
        self,
        workdir: Path,
        chat_id: int | str,
        text: str,
        delete_after: Optional[int] = None,
        account: Optional[str] = None,
    ) -> str:
        account_name = (account or self.settings.account).strip() or self.settings.account
        worker = self._build_signer(workdir, account=account_name)
        await self._ensure_authorized_worker(worker)
        await worker.send_text(chat_id, text, delete_after)
        self._event(f"Sent text message to {chat_id} with account {account_name}")
        return "ok"

    async def send_dice(
        self,
        workdir: Path,
        chat_id: int | str,
        emoji: str,
        delete_after: Optional[int] = None,
        account: Optional[str] = None,
    ) -> str:
        emoji = (emoji or "").strip() or DICE_EMOJIS[0]
        account_name = (account or self.settings.account).strip() or self.settings.account
        worker = self._build_signer(workdir, account=account_name)
        await self._ensure_authorized_worker(worker)
        await worker.send_dice_cli(chat_id, emoji, delete_after)
        self._event(f"Sent dice {emoji} to {chat_id} with account {account_name}")
        return "ok"

    async def list_members(
        self,
        workdir: Path,
        chat_id: str | int,
        query: str = "",
        *,
        admin: bool = False,
        limit: int = 10,
        account: Optional[str] = None,
    ) -> list[dict[str, object]]:
        account_name = (account or self.settings.account).strip() or self.settings.account
        worker = self._build_signer(workdir, account=account_name)
        await self._ensure_authorized_worker(worker)
        rows = await worker.list_members_data(
            chat_id,
            query=query,
            admin=admin,
            limit=limit,
        )
        self._event(f"Loaded {len(rows)} members from {chat_id} with account {account_name}")
        return rows

    async def schedule_messages(
        self,
        workdir: Path,
        chat_id: int | str,
        text: str,
        crontab: str,
        *,
        next_times: int = 1,
        random_seconds: int = 0,
        account: Optional[str] = None,
    ) -> list[dict[str, object]]:
        account_name = (account or self.settings.account).strip() or self.settings.account
        worker = self._build_signer(workdir, account=account_name)
        await self._ensure_authorized_worker(worker)
        rows = await worker.schedule_messages(
            chat_id,
            text,
            crontab,
            next_times=next_times,
            random_seconds=random_seconds,
        )
        self._event(f"Scheduled {len(rows)} messages for {chat_id} with account {account_name}")
        return rows

    async def list_scheduled_messages(
        self,
        workdir: Path,
        chat_id: int | str,
        account: Optional[str] = None,
    ) -> list[dict[str, object]]:
        account_name = (account or self.settings.account).strip() or self.settings.account
        worker = self._build_signer(workdir, account=account_name)
        await self._ensure_authorized_worker(worker)
        rows = await worker.get_schedule_messages_data(chat_id)
        self._event(f"Loaded {len(rows)} scheduled messages from {chat_id} with account {account_name}")
        return rows

    def pending_login_status(self) -> Optional[str]:
        pending = self.pending_logins.get(self._account_key())
        if pending is None:
            return None
        if pending.requires_password:
            return "password_required"
        return "code_sent"

    def llm_defaults(self) -> dict[str, str]:
        return {"model": DEFAULT_MODEL}

    def _create_job(
        self,
        *,
        kind: str,
        label: str,
        accounts: list[str],
        task_names: list[str],
        signer_tasks: Optional[list[str]] = None,
        monitor_tasks: Optional[list[str]] = None,
        coro_factory: Callable[[], Awaitable[None]],
    ) -> BackgroundJob:
        self._job_index += 1
        job = BackgroundJob(
            job_id=f"job-{self._job_index}",
            kind=kind,
            label=label,
            accounts=accounts,
            task_names=task_names,
            signer_tasks=list(signer_tasks or []),
            monitor_tasks=list(monitor_tasks or []),
        )

        async def runner() -> None:
            try:
                await coro_factory()
            except asyncio.CancelledError:
                job.status = "cancelled"
                self._event(f"Stopped {job.label}")
                raise
            except Exception as exc:  # noqa: BLE001
                job.status = "failed"
                job.error = str(exc)
                self._event(f"{job.label} failed: {exc}")
            else:
                job.status = "completed"
                self._event(f"{job.label} completed")
            finally:
                job.finished_at = datetime.now()

        loop = asyncio.get_running_loop()
        job.task = loop.create_task(runner(), name=job.label)
        self.jobs[job.job_id] = job
        self._event(f"Started {job.label}")
        return job

    def list_jobs(self) -> list[BackgroundJob]:
        return sorted(
            self.jobs.values(),
            key=lambda job: job.started_at,
            reverse=True,
        )

    def get_running_keepalive_configs(self, account: str) -> dict[str, list[str]]:
        clean_account = (account or "").strip()
        signer_tasks: set[str] = set()
        monitor_tasks: set[str] = set()
        for job in self.jobs.values():
            if job.kind != "keepalive" or job.status != "running":
                continue
            if clean_account and clean_account not in job.accounts:
                continue
            signer_tasks.update(job.signer_tasks)
            monitor_tasks.update(job.monitor_tasks)
        return {
            "signer_tasks": sorted(signer_tasks),
            "monitor_tasks": sorted(monitor_tasks),
        }

    async def stop_job(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job or not job.task:
            raise ValueError("Job not found")
        if job.task.done():
            return
        job.task.cancel()
        try:
            await job.task
        except asyncio.CancelledError:
            pass

    async def delete_job(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            raise ValueError("Job not found")
        if job.task and not job.task.done():
            await self.stop_job(job_id)
        self.jobs.pop(job_id, None)
        self._event(f"Deleted {job.label}")

    def start_signer_job(
        self,
        workdir: Path,
        task_names: list[str],
        *,
        only_once: bool,
        force_rerun: bool = False,
    ) -> BackgroundJob:
        clean_task_names = [name.strip() for name in task_names if name.strip()]
        if not clean_task_names:
            raise ValueError("At least one signer task is required")

        async def run_many() -> None:
            workers = [
                self._build_signer(workdir, task_name=task_name)
                for task_name in clean_task_names
            ]
            await self._ensure_authorized_worker(workers[0])
            await asyncio.gather(
                *[
                    worker.run(
                        num_of_dialogs=self.settings.num_of_dialogs,
                        only_once=only_once,
                        force_rerun=force_rerun,
                    )
                    for worker in workers
                ]
            )

        mode = "run-once" if only_once else "run"
        return self._create_job(
            kind=mode,
            label=f"Signer {mode}: {', '.join(clean_task_names)}",
            accounts=[self.settings.account],
            task_names=clean_task_names,
            signer_tasks=clean_task_names,
            coro_factory=run_many,
        )

    def start_monitor_job(self, workdir: Path, task_name: str) -> BackgroundJob:
        task_name = task_name.strip()
        if not task_name:
            raise ValueError("Monitor task name is required")

        async def run_monitor() -> None:
            worker = self._build_monitor(workdir, task_name=task_name)
            await self._ensure_authorized_worker(worker)
            await worker.run(num_of_dialogs=self.settings.num_of_dialogs)

        return self._create_job(
            kind="monitor",
            label=f"Monitor run: {task_name}",
            accounts=[self.settings.account],
            task_names=[task_name],
            monitor_tasks=[task_name],
            coro_factory=run_monitor,
        )

    def start_multi_run_job(self, workdir: Path, task_name: str, accounts: list[str]) -> BackgroundJob:
        task_name = task_name.strip()
        clean_accounts = [account.strip() for account in accounts if account.strip()]
        if not task_name:
            raise ValueError("Signer task name is required")
        if not clean_accounts:
            raise ValueError("At least one account is required")

        async def run_many_accounts() -> None:
            workers = [
                self._build_signer(workdir, task_name=task_name, account=account)
                for account in clean_accounts
            ]
            for worker in workers:
                await self._ensure_authorized_worker(worker)
            await asyncio.gather(
                *[
                    worker.run(
                        num_of_dialogs=self.settings.num_of_dialogs,
                        only_once=False,
                        force_rerun=False,
                    )
                    for worker in workers
                ]
            )

        return self._create_job(
            kind="multi-run",
            label=f"Signer multi-run: {task_name}",
            accounts=clean_accounts,
            task_names=[task_name],
            signer_tasks=[task_name],
            coro_factory=run_many_accounts,
        )

    def start_keepalive_job(
        self,
        workdir: Path,
        *,
        account: str,
        signer_tasks: list[str],
        monitor_tasks: list[str],
    ) -> BackgroundJob:
        account = account.strip()
        clean_signer_tasks = [name.strip() for name in signer_tasks if name.strip()]
        clean_monitor_tasks = [name.strip() for name in monitor_tasks if name.strip()]
        if not account:
            raise ValueError("Account is required")
        if not clean_signer_tasks and not clean_monitor_tasks:
            raise ValueError("Select at least one signer or monitor config")

        async def run_keepalive() -> None:
            await self._ensure_authorized_account(workdir, account)
            signers = [
                self._build_signer(workdir, task_name=task_name, account=account)
                for task_name in clean_signer_tasks
            ]
            monitors = [
                self._build_monitor(workdir, task_name=task_name, account=account)
                for task_name in clean_monitor_tasks
            ]
            await asyncio.gather(
                *[
                    signer.run(
                        num_of_dialogs=self.settings.num_of_dialogs,
                        only_once=False,
                        force_rerun=False,
                    )
                    for signer in signers
                ],
                *[
                    monitor.run(num_of_dialogs=self.settings.num_of_dialogs)
                    for monitor in monitors
                ],
            )

        task_names = clean_signer_tasks + clean_monitor_tasks
        return self._create_job(
            kind="keepalive",
            label=f"Keepalive run: {account}",
            accounts=[account],
            task_names=task_names,
            signer_tasks=clean_signer_tasks,
            monitor_tasks=clean_monitor_tasks,
            coro_factory=run_keepalive,
        )
