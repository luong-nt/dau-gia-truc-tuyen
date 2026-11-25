"""Điều phối tự động hai agent: Codex (lập trình) và Claude (giao việc + kiểm thử).

Script đọc trạng thái trong docs/tasks/TASK-*.md rồi tự gọi agent ở chế độ không tương tác:
  - Codex:  `codex exec`  — làm task TODO / sửa task CHANGES_REQUESTED
  - Claude: `claude -p`   — viết test song song, kiểm thử task REVIEW, lập task mới từ backlog

Chạy (trong thư mục dgtt-backend, đã có Docker DB và 2 database test):
    python scripts/auto_run.py                    # chạy đến khi hết việc
    python scripts/auto_run.py --dry-run          # chỉ in ra sẽ làm gì
    python scripts/auto_run.py --max-new-tasks 2  # cho Claude lập thêm tối đa 2 task từ backlog

Dừng giữa chừng: Ctrl+C (agent đang chạy sẽ bị dừng; trạng thái trong file task vẫn giữ nguyên,
lần chạy sau sẽ tiếp tục). Log từng lượt nằm trong logs/auto_run/.
Chỉ dùng thư viện chuẩn của Python.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_DIR = ROOT / "docs" / "tasks"
LOG_DIR = ROOT / "logs" / "auto_run"
STATE_FILE = LOG_DIR / "state.json"

DB_BASE = "postgresql+asyncpg://dgtt:dgtt@localhost:5432"
CLAUDE_TEST_DB = f"{DB_BASE}/dgtt_test"
CODEX_TEST_DB = f"{DB_BASE}/dgtt_test_codex"

HEADLESS_NOTE = (
    "Bạn đang chạy TỰ ĐỘNG, không có người trả lời. Không hỏi lại người dùng. "
    "Nếu cần quyết định của người dùng (nghiệp vụ không có trong SRS/AGENTS.md, đổi schema, thêm thư viện) "
    "thì ghi câu hỏi vào file task, đặt trạng thái BLOCKED theo quy trình, rồi kết thúc. "
    "Biến môi trường TEST_DATABASE_URL đã được đặt sẵn đúng database test của bạn: chỉ cần chạy `pytest`."
)

# ---------------------------------------------------------------------------
# Lệnh gọi agent. Sửa ở đây nếu phiên bản CLI của bạn khác.
# Prompt luôn được truyền qua stdin (tránh lỗi trích dẫn tiếng Việt trên Windows).
# ---------------------------------------------------------------------------
CODEX_CMD = [
    "codex",
    "exec",
    "--sandbox",
    "workspace-write",
    # Cho phép kết nối mạng trong sandbox để tới PostgreSQL ở localhost
    "-c",
    "sandbox_workspace_write.network_access=true",
    "-c",
    "approval_policy=never",
    "-",  # đọc prompt từ stdin
]

CLAUDE_ALLOWED_TOOLS = ",".join(
    [
        "Read",
        "Edit",
        "Write",
        "Glob",
        "Grep",
        "Bash(pytest *)",
        "Bash(python -m pytest *)",
        "Bash(ruff *)",
        "Bash(python -m ruff *)",
        "Bash(git status *)",
        "Bash(git diff *)",
        "Bash(git log *)",
    ]
)
# Claude không được sửa code (luật Edit áp dụng cho mọi công cụ sửa file)
CLAUDE_DISALLOWED_TOOLS = ",".join(f"Edit({path}/**)" for path in ("app", "migrations", "seeds", "sql"))
CLAUDE_CMD = [
    "claude",
    "-p",
    "--permission-mode",
    "acceptEdits",
    "--allowedTools",
    CLAUDE_ALLOWED_TOOLS,
    "--disallowedTools",
    CLAUDE_DISALLOWED_TOOLS,
]

# ---------------------------------------------------------------------------

STATUS_RE = re.compile(r"\*\*Trạng thái:\*\*\s*([A-Z_]+)")
DEPS_RE = re.compile(r"\*\*Phụ thuộc:\*\*(.*)")
TASK_ID_RE = re.compile(r"TASK-\d{3}")

OPEN_FOR_CODEX = ("CHANGES_REQUESTED", "TODO")
WAITING_FOR_CLAUDE = ("REVIEW", "TESTING")


@dataclass
class Task:
    id: str
    path: Path
    status: str
    deps: list[str]


@dataclass
class Job:
    agent: str  # "codex" | "claude"
    action: str  # "implement" | "fix" | "resume" | "write_tests" | "review" | "plan"
    task_id: str | None
    prompt: str


@dataclass
class Running:
    job: Job
    proc: subprocess.Popen
    log_path: Path
    started: float
    status_before: str | None


@dataclass
class State:
    tests_written: list[str] = field(default_factory=list)
    fix_rounds: dict[str, int] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)  # "agent:action:task" -> số lần thất bại
    planned: int = 0

    @classmethod
    def load(cls) -> State:
        if STATE_FILE.exists():
            return cls(**json.loads(STATE_FILE.read_text(encoding="utf-8")))
        return cls()

    def save(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(self.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}", flush=True)


def load_tasks() -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    for path in sorted(TASK_DIR.glob("TASK-*.md")):
        text = path.read_text(encoding="utf-8")
        task_id = TASK_ID_RE.search(path.name).group(0)
        status_match = STATUS_RE.search(text)
        deps_match = DEPS_RE.search(text)
        deps = TASK_ID_RE.findall(deps_match.group(1)) if deps_match else []
        tasks[task_id] = Task(
            task_id, path, status_match.group(1) if status_match else "UNKNOWN", [d for d in deps if d != task_id]
        )
    return tasks


def deps_done(task: Task, tasks: dict[str, Task]) -> bool:
    return all(tasks.get(d) is not None and tasks[d].status == "DONE" for d in task.deps)


def failure_key(agent: str, action: str, task_id: str | None) -> str:
    return f"{agent}:{action}:{task_id or '-'}"


class Orchestrator:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.state = State.load()
        self.running: dict[str, Running] = {}

    # ---------------- chọn việc ----------------
    def _skipped(self, agent: str, action: str, task_id: str | None) -> bool:
        if self.state.failures.get(failure_key(agent, action, task_id), 0) >= self.args.max_attempts:
            return True
        return bool(task_id and self.state.fix_rounds.get(task_id, 0) > self.args.max_fix_rounds)

    def next_codex_job(self, tasks: dict[str, Task]) -> Job | None:
        busy_task = self.running.get("claude").job.task_id if "claude" in self.running else None
        # Không code task mới khi Claude đang chạy toàn bộ test (tránh test đọc code dở dang)
        if not self.args.parallel_review and any(t.status in WAITING_FOR_CLAUDE for t in tasks.values()):
            return None
        for task in tasks.values():  # task IN_PROGRESS bị bỏ dở từ lần chạy trước
            if task.status == "IN_PROGRESS" and not self._skipped("codex", "resume", task.id):
                return Job(
                    "codex",
                    "resume",
                    task.id,
                    f"Tiếp tục {task.id} (đang IN_PROGRESS từ lượt trước) theo AGENTS.md Mục 7 "
                    f"cho đến khi bàn giao REVIEW. {HEADLESS_NOTE}",
                )
        for status in OPEN_FOR_CODEX:
            for task in tasks.values():
                if task.status != status or task.id == busy_task or not deps_done(task, tasks):
                    continue
                action = "fix" if status == "CHANGES_REQUESTED" else "implement"
                if self._skipped("codex", action, task.id):
                    continue
                verb = "Sửa" if action == "fix" else "Làm"
                extra = " theo mục 'Kết quả kiểm thử (Claude)'" if action == "fix" else ""
                return Job(
                    "codex",
                    action,
                    task.id,
                    f"{verb} {task.id}{extra}. Tuân thủ AGENTS.md Mục 7–8: nhận task, hiện thực, "
                    f"tự kiểm tra, điền 'Ghi chú triển khai (Codex)', đặt REVIEW. {HEADLESS_NOTE}",
                )
        return None

    def next_claude_job(self, tasks: dict[str, Task]) -> Job | None:
        codex_task = self.running.get("codex").job.task_id if "codex" in self.running else None
        # 1) Kiểm thử task đã bàn giao
        for task in tasks.values():
            if (
                task.status in WAITING_FOR_CLAUDE
                and task.id != codex_task
                and not self._skipped("claude", "review", task.id)
            ):
                return Job(
                    "claude",
                    "review",
                    task.id,
                    f"Thực hiện Quy trình C trong CLAUDE.md: kiểm thử {task.id}, kết luận DONE hoặc "
                    f"CHANGES_REQUESTED, cập nhật docs/TASKS.md. {HEADLESS_NOTE}",
                )
        # 2) Viết test song song cho task Codex đang làm hoặc sắp làm
        for task in tasks.values():
            if (
                task.status in ("TODO", "IN_PROGRESS")
                and deps_done(task, tasks)
                and task.id not in self.state.tests_written
                and not self._skipped("claude", "write_tests", task.id)
            ):
                return Job(
                    "claude",
                    "write_tests",
                    task.id,
                    f"Thực hiện Quy trình B trong CLAUDE.md: viết test cho {task.id} theo đặc tả. "
                    f"KHÔNG sửa file docs/tasks của {task.id} (Codex có thể đang giữ). {HEADLESS_NOTE}",
                )
        # 3) Lập task mới khi sắp hết việc
        open_tasks = [t for t in tasks.values() if t.status not in ("DONE", "BLOCKED")]
        if (
            self.state.planned < self.args.max_new_tasks
            and len(open_tasks) < 2
            and not self._skipped("claude", "plan", None)
        ):
            return Job(
                "claude",
                "plan",
                None,
                "Thực hiện Quy trình A trong CLAUDE.md: lập ĐÚNG MỘT task tiếp theo từ Backlog trong "
                "docs/TASKS.md (ưu tiên việc không phụ thuộc task chưa DONE; bỏ qua việc ghi 'Cần người dùng "
                f"quyết định'). Nếu backlog không còn việc phù hợp thì không tạo gì. {HEADLESS_NOTE}",
            )
        return None

    # ---------------- chạy agent ----------------
    def start(self, job: Job, tasks: dict[str, Task]) -> None:
        cmd = list(CODEX_CMD if job.agent == "codex" else CLAUDE_CMD)
        if job.agent == "claude" and self.args.claude_max_turns:
            cmd += ["--max-turns", str(self.args.claude_max_turns)]
        exe = shutil.which(cmd[0])
        if exe is None:
            sys.exit(f"Không tìm thấy lệnh '{cmd[0]}' trong PATH. Cài đặt và đăng nhập CLI trước.")
        cmd[0] = exe

        env = os.environ.copy()
        env["TEST_DATABASE_URL"] = CODEX_TEST_DB if job.agent == "codex" else CLAUDE_TEST_DB
        env["PYTHONIOENCODING"] = "utf-8"
        venv_bin = ROOT / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        if venv_bin.exists():
            env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
            env["VIRTUAL_ENV"] = str(venv_bin.parent)

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = LOG_DIR / f"{stamp}-{job.agent}-{job.action}-{job.task_id or 'plan'}.log"
        log_file = log_path.open("w", encoding="utf-8")
        log_file.write(f"$ {' '.join(cmd)}\n--- PROMPT ---\n{job.prompt}\n--- OUTPUT ---\n")
        log_file.flush()

        proc = subprocess.Popen(
            cmd,
            cwd=ROOT,
            env=env,
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        proc.stdin.write(job.prompt)
        proc.stdin.close()
        status_before = tasks[job.task_id].status if job.task_id in tasks else None
        self.running[job.agent] = Running(job, proc, log_path, time.monotonic(), status_before)
        log(f"▶ {job.agent:6} {job.action:11} {job.task_id or '':8} → {log_path.name}")

    def reap(self) -> None:
        for agent, run in list(self.running.items()):
            timed_out = time.monotonic() - run.started > self.args.timeout_minutes * 60
            if timed_out:
                run.proc.kill()
            code = run.proc.poll()
            if code is None:
                continue
            del self.running[agent]
            job = run.job
            tasks = load_tasks()
            status_after = tasks[job.task_id].status if job.task_id in tasks else None
            ok = code == 0 and not timed_out
            if job.action == "write_tests" and ok:
                self.state.tests_written.append(job.task_id)
            if job.action == "plan":
                self.state.planned += 1
            if job.action == "review" and status_after == "CHANGES_REQUESTED":
                self.state.fix_rounds[job.task_id] = self.state.fix_rounds.get(job.task_id, 0) + 1
            progressed = job.action in ("write_tests", "plan") or status_after != run.status_before
            if not ok or not progressed:
                key = failure_key(job.agent, job.action, job.task_id)
                self.state.failures[key] = self.state.failures.get(key, 0) + 1
            self.state.save()
            note = "HẾT GIỜ" if timed_out else f"exit={code}"
            change = f"{run.status_before} → {status_after}" if job.task_id else ""
            log(f"■ {agent:6} {job.action:11} {job.task_id or '':8} {note} {change}")

    def stop_all(self) -> None:
        for run in self.running.values():
            run.proc.kill()

    # ---------------- vòng lặp chính ----------------
    def run(self) -> None:
        deadline = time.monotonic() + self.args.max_hours * 3600
        idle_rounds = 0
        while time.monotonic() < deadline:
            self.reap()
            tasks = load_tasks()
            started = False
            for agent, pick in (("codex", self.next_codex_job), ("claude", self.next_claude_job)):
                if agent in self.running:
                    continue
                job = pick(tasks)
                if job is None:
                    continue
                if self.args.dry_run:
                    log(f"(dry-run) {job.agent} {job.action} {job.task_id or ''}\n    {job.prompt}")
                    continue
                self.start(job, tasks)
                started = True
                tasks = load_tasks()
            if self.args.dry_run:
                break
            if not self.running and not started:
                idle_rounds += 1
                if idle_rounds >= 2:
                    break
            else:
                idle_rounds = 0
            time.sleep(self.args.poll_seconds)
        self.stop_all()
        self.summary()

    def summary(self) -> None:
        tasks = load_tasks()
        log("Kết thúc. Trạng thái task:")
        for task in tasks.values():
            mark = ""
            if task.status == "BLOCKED":
                mark = "  ← cần bạn trả lời trong file task"
            elif self.state.fix_rounds.get(task.id, 0) > self.args.max_fix_rounds:
                mark = f"  ← đã sửa {self.state.fix_rounds[task.id]} lần vẫn chưa đạt, cần bạn xem"
            print(f"    {task.id}  {task.status:18}{mark}")
        stuck = [k for k, v in self.state.failures.items() if v >= self.args.max_attempts]
        if stuck:
            print("    Bị bỏ qua vì thất bại nhiều lần (xem log trong logs/auto_run/):", ", ".join(stuck))
            print("    Xử lý xong nguyên nhân thì chạy lại với --reset-state.")
        if any(t.status == "DONE" for t in tasks.values()):
            print("    Task DONE: hãy xem lại rồi commit với message 'TASK-xxx: <tiêu đề>'.")


def check_git_clean() -> None:
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout
    except FileNotFoundError:
        return
    if out.strip():
        log("CẢNH BÁO: còn thay đổi chưa commit. Nên commit trước để có thể quay lại nếu agent sửa sai.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tự động điều phối Codex + Claude theo docs/tasks.")
    parser.add_argument("--max-hours", type=float, default=4, help="Tổng thời gian chạy tối đa (giờ)")
    parser.add_argument("--timeout-minutes", type=float, default=45, help="Thời gian tối đa cho một lượt agent")
    parser.add_argument(
        "--max-new-tasks",
        type=int,
        default=0,
        help="Số task Claude được tự lập thêm từ backlog (mặc định 0: chỉ làm task đã có)",
    )
    parser.add_argument(
        "--max-fix-rounds", type=int, default=3, help="Số lần CHANGES_REQUESTED tối đa cho một task trước khi bỏ qua"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Số lần một lượt thất bại (lỗi/không đổi trạng thái) trước khi bỏ qua",
    )
    parser.add_argument("--claude-max-turns", type=int, default=0, help="Giới hạn --max-turns cho Claude (0 = không)")
    parser.add_argument(
        "--parallel-review", action="store_true", help="Cho Codex làm task mới trong lúc Claude đang kiểm thử task khác"
    )
    parser.add_argument("--poll-seconds", type=float, default=10)
    parser.add_argument("--reset-state", action="store_true", help="Xoá logs/auto_run/state.json trước khi chạy")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in việc sẽ làm ở lượt đầu, không gọi agent")
    args = parser.parse_args()

    if args.reset_state and STATE_FILE.exists():
        STATE_FILE.unlink()
    check_git_clean()
    orchestrator = Orchestrator(args)
    try:
        orchestrator.run()
    except KeyboardInterrupt:
        log("Đã nhận Ctrl+C, dừng các agent đang chạy...")
        orchestrator.stop_all()
        orchestrator.summary()


if __name__ == "__main__":
    main()
