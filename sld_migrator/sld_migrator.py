# -*- coding: utf-8 -*-
"""SLD Migrator — GUI-утилита переноса «Blocarea vinzarilor in minus» (UNA.md, схема MARKET).

Запуск:  python sld_migrator.py     (или run.bat)
Нужны только Python 3.8+ (tkinter входит в стандартную поставку) и Oracle sqlplus.
Документация и карта процесса встроены: кнопки «Документация» и «Карта процесса».
"""
import configparser
import datetime as dt
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import steps as S
import webdocs

APP_DIR = Path(__file__).resolve().parent
VERSION = "1.0 (11.11.2026)"
STATUS_ICON = {"pending": "○", "running": "▶", "done": "✔", "dry": "◐", "failed": "✖", "skipped": "➜"}
STATUS_RU = {"pending": "ожидает", "running": "выполняется", "done": "выполнен", "dry": "сухой прогон",
             "failed": "ошибка", "skipped": "отмечен вручную"}
KIND_RU = {"manual": "ручной", "check": "проверка (только чтение)", "change": "ИЗМЕНЕНИЕ", "long": "ДЛИТЕЛЬНОЕ ИЗМЕНЕНИЕ"}


def rel(p):
    """Путь относительно папки утилиты — для показа в окне и журнале."""
    try:
        return os.path.relpath(str(p), str(APP_DIR))
    except Exception:
        return str(p)


def now_s():
    return dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


# ============================================================================ конфигурация
class Config:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("SLDMIG_INI") or APP_DIR / "sld_migrator.ini")
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(self.path, encoding="utf-8")
        g = cp["general"] if cp.has_section("general") else {}
        self.sqlplus = g.get("sqlplus", "sqlplus")
        self.nls_lang = g.get("nls_lang", "AMERICAN_AMERICA.CL8MSWIN1251")
        self.encoding = g.get("encoding", "cp1251")
        self.scripts_dir = (APP_DIR / g.get("scripts_dir", "../scripts")).resolve()
        self.backup_prod_dir = (APP_DIR / g.get("backup_prod_dir", "../backup_prod")).resolve()
        self.monitor_interval = int(g.get("monitor_interval", 10))
        self.http_port = int(g.get("http_port", 0))
        self.profiles = {}
        for sec in cp.sections():
            if sec.startswith("profile:"):
                self.profiles[sec.split(":", 1)[1]] = dict(cp[sec])


# ============================================================================ запуск sqlplus
class Proc:
    _seq = 0

    def __init__(self, title, kind, tag, hidden=False):
        Proc._seq += 1
        self.id = Proc._seq
        self.title, self.kind, self.tag, self.hidden = title, kind, tag, hidden
        self.pid = None
        self.start = time.time()
        self.end = None
        self.status = "running"          # running | ok | fail | killed
        self.rc = None
        self.lines = []
        self.marks = {}
        self.errors = []
        self.connected = False
        self.popen = None
        self.on_done = None
        self.logfile = None

    @property
    def elapsed(self):
        return (self.end or time.time()) - self.start

    def last_line(self):
        for l in reversed(self.lines):
            if l.strip():
                return l.strip()
        return ""


class Engine:
    """Асинхронный запуск sqlplus: каждый процесс — отдельный поток, вывод идёт в очередь событий."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.events = queue.Queue()
        self.procs = []
        self.profile = None          # dict профиля
        self.profile_name = None
        self.password = None
        self.log_dir = APP_DIR / "logs"

    def set_profile(self, name, password):
        self.profile_name, self.profile, self.password = name, self.cfg.profiles[name], password

    def _script(self, body, tag, strict, guard=True):
        p = self.profile
        host = p.get("expected_host", "").lower().replace("'", "")
        out = ["set echo off feedback on heading on pagesize 500 linesize 250 trimspool on trimout on tab off verify off define off sqlblanklines on",
               "whenever oserror exit 8",
               'connect %s/"%s"@%s' % (p["user"], self.password, p["dsn"]),
               "set serveroutput on size unlimited",
               "set heading off feedback off",
               "select '@@CONNECTED|'||sys_context('USERENV','SERVER_HOST') from dual;"]
        if guard and host:
            # защита от «не той базы»: проверка выполняется в самой базе до любого шага
            out += ["whenever sqlerror exit 7",
                    "begin if lower(sys_context('USERENV','SERVER_HOST')) <> '%s' then "
                    "raise_application_error(-20999,'WRONG DATABASE: '||sys_context('USERENV','SERVER_HOST')); end if; end;" % host,
                    "/", "whenever sqlerror continue"]
        out += ["exec dbms_application_info.set_module('%s','%s')" % ("SLDMIG" if guard != "mon" else "SLDMIG-MON", tag),
                "set heading on feedback on"]
        if strict:
            out.append("whenever sqlerror exit 9 rollback")
        out += [body, "exit"]
        return "\n".join(out) + "\n"

    def run(self, title, body, kind="чтение", tag="-", strict=False, hidden=False, on_done=None, module=None):
        proc = Proc(title, kind, tag, hidden)
        proc.on_done = on_done
        guard = "mon" if module == "mon" else True
        script = self._script(body, tag, strict, guard)
        if not hidden:
            d = self.log_dir / self.profile_name
            d.mkdir(parents=True, exist_ok=True)
            proc.logfile = d / ("%s_%s.log" % (dt.datetime.now().strftime("%Y%m%d_%H%M%S"), re.sub(r"\W+", "_", tag)))
        self.procs.append(proc)
        threading.Thread(target=self._worker, args=(proc, script), daemon=True).start()
        return proc

    def _worker(self, proc, script):
        cfg = self.cfg
        env = dict(os.environ, NLS_LANG=cfg.nls_lang)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        log = None
        try:
            if proc.logfile:
                log = open(proc.logfile, "w", encoding="utf-8")
                log.write("# %s | %s | профиль %s | %s\n" % (now_s(), proc.title, self.profile_name, proc.kind))
            po = subprocess.Popen([cfg.sqlplus, "-S", "-L", "/nolog"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, env=env, creationflags=flags)
            proc.popen, proc.pid = po, po.pid
            self.events.put(("start", proc, None))
            po.stdin.write(script.encode(cfg.encoding, "replace"))
            po.stdin.close()
            for raw in po.stdout:
                line = raw.decode(cfg.encoding, "replace").rstrip("\r\n")
                st = line.strip()
                if st.startswith("@@"):
                    k, _, v = st[2:].partition("|")
                    if k == "CONNECTED":
                        proc.connected = True
                    proc.marks[k] = v.strip()
                    if log:
                        log.write(line + "\n")
                    self.events.put(("mark", proc, st))
                    continue
                if re.match(r"^(ORA-\d+|SP2-\d+|PLS-\d+)", st):
                    proc.errors.append(st)
                proc.lines.append(line)
                if log:
                    log.write(line + "\n")
                    log.flush()
                self.events.put(("line", proc, line))
            po.wait()
            proc.rc = po.returncode
        except FileNotFoundError:
            proc.errors.append("sqlplus не найден: %s" % cfg.sqlplus)
            proc.lines.append(proc.errors[-1])
            proc.rc = -1
        except Exception as e:                      # noqa
            proc.errors.append("ошибка запуска: %r" % e)
            proc.lines.append(proc.errors[-1])
            proc.rc = -2
        proc.end = time.time()
        if proc.status != "killed":
            if not proc.connected:
                proc.status = "fail"
                if not proc.errors:
                    proc.errors.append("нет соединения с базой")
            else:
                proc.status = "ok" if proc.rc == 0 else "fail"
        if log:
            log.write("# конец %s | статус %s | rc=%s | %.1f c\n" % (now_s(), proc.status, proc.rc, proc.elapsed))
            log.close()
        self.events.put(("done", proc, None))

    def kill(self, proc):
        if proc.status == "running" and proc.popen:
            proc.status = "killed"
            try:
                proc.popen.kill()
            except Exception:
                pass

    def running(self, include_hidden=False):
        return [p for p in self.procs if p.status == "running" and (include_hidden or not p.hidden)]


# ============================================================================ встроенный веб-сервер
class WebState:
    json_text = "{}"
    shots_dir = APP_DIR / "screenshots"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/process"):
            self._send(webdocs.PROCESS_HTML)
        elif path == "/doc":
            self._send(webdocs.DOC_HTML)
        elif path == "/api/state":
            self._send(WebState.json_text, "application/json; charset=utf-8")
        elif path.startswith("/screenshots/"):
            f = WebState.shots_dir / Path(path).name
            if f.is_file() and f.suffix == ".png":
                self._send(f.read_bytes(), "image/png")
            else:
                self._send("not found", code=404)
        else:
            self._send("not found", code=404)


# ============================================================================ GUI
class App:
    def __init__(self, root, cfg=None, auto=False):
        self.root = root
        self.cfg = cfg or Config()
        self.eng = Engine(self.cfg)
        self.auto = auto                    # автодемо: без диалогов (только в сухом прогоне)
        self.connected = False
        self.host = ""
        self.state = {"steps": {}, "jqp_saved": None}
        self.checks_result = []
        self.checks_stage = ""
        self.monitor = {"at": "", "state": {}, "sessions": [], "longops": [], "log": [], "took": 0}
        self.mon_proc = None
        self.mon_last = 0
        self.sel_step = S.STEPS[0]["id"]
        self.sel_proc = None
        self.step_out = {}                  # step id -> список строк последнего запуска
        self._build()
        self._start_http()
        self._load_state()
        self._refresh_steps()
        self._show_step(self.sel_step)
        self.root.after(150, self._pump)
        self.root.after(1000, self._tick)

    # ------------------------------------------------------------------ построение окна
    def _build(self):
        r = self.root
        r.title("SLD Migrator %s — Blocarea vinzarilor in minus (UNA.md / MARKET)" % VERSION)
        r.geometry("1380x860")
        r.minsize(1100, 700)
        st = ttk.Style()
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        st.configure("Treeview", rowheight=24, font=("Segoe UI", 10))
        st.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        st.configure("Big.TLabel", font=("Segoe UI", 13, "bold"))
        st.configure("Run.TButton", font=("Segoe UI", 10, "bold"))

        top = ttk.Frame(r, padding=(8, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Профиль:").pack(side="left")
        self.profile_var = tk.StringVar(value=next(iter(self.cfg.profiles), ""))
        self.profile_cb = ttk.Combobox(top, textvariable=self.profile_var, values=list(self.cfg.profiles), width=8, state="readonly")
        self.profile_cb.pack(side="left", padx=4)
        self.profile_cb.bind("<<ComboboxSelected>>", lambda e: self._profile_changed())
        self.btn_connect = ttk.Button(top, text="Подключиться", command=self.connect_dialog)
        self.btn_connect.pack(side="left", padx=4)
        self.conn_lbl = tk.Label(top, text="  не подключено  ", bg="#b0b7c3", fg="white", font=("Segoe UI", 10, "bold"), padx=8, pady=3)
        self.conn_lbl.pack(side="left", padx=6)
        self.dry_var = tk.BooleanVar(value=True)
        self.dry_cb = ttk.Checkbutton(top, text="Сухой прогон (ничего не менять)", variable=self.dry_var, command=self._dry_toggled)
        self.dry_cb.pack(side="left", padx=10)
        self.expert_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Эксперт (без порядка шагов)", variable=self.expert_var).pack(side="left")
        ttk.Button(top, text="Карта процесса", command=lambda: self.open_web("/process")).pack(side="right", padx=3)
        ttk.Button(top, text="Документация", command=lambda: self.open_web("/doc")).pack(side="right", padx=3)

        self.banner = tk.Label(r, text="", font=("Segoe UI", 10, "bold"), fg="white", bg="#0f766e", pady=3)
        self.banner.pack(fill="x")

        pw = ttk.Panedwindow(r, orient="horizontal")
        pw.pack(fill="both", expand=True, padx=6, pady=4)

        # ---- слева: шаги
        left = ttk.Frame(pw)
        pw.add(left, weight=2)
        self.progress_lbl = ttk.Label(left, text="", font=("Segoe UI", 10, "bold"))
        self.progress_lbl.pack(anchor="w", pady=(0, 2))
        self.progress = ttk.Progressbar(left, maximum=100)
        self.progress.pack(fill="x", pady=(0, 4))
        self.tree = ttk.Treeview(left, columns=("st", "when"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Шаг")
        self.tree.heading("st", text="Статус")
        self.tree.heading("when", text="Когда")
        self.tree.column("#0", width=300, stretch=True)
        self.tree.column("st", width=100, stretch=False)
        self.tree.column("when", width=85, stretch=False)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        for tag, fg, bg in (("pending", "#475569", ""), ("running", "#1d4ed8", "#dbeafe"), ("done", "#15803d", ""),
                            ("dry", "#0f766e", ""), ("failed", "#b91c1c", "#fee2e2"), ("skipped", "#b45309", ""),
                            ("phase", "#0f172a", "#e2e8f0"), ("current", "#0f172a", "#fef08a")):
            self.tree.tag_configure(tag, foreground=fg, background=bg)
        self.tree.tag_configure("phase", font=("Segoe UI", 10, "bold"))
        for ph, title, sub in S.PHASES:
            self.tree.insert("", "end", iid="ph_" + ph, text=title, values=("", ""), open=True, tags=("phase",))
        for s in S.STEPS:
            self.tree.insert("ph_" + s["phase"], "end", iid=s["id"], text="", values=("", s["when"]))
        self.tree.bind("<<TreeviewSelect>>", self._tree_select)

        # ---- справа: вкладки
        self.nb = ttk.Notebook(pw)
        pw.add(self.nb, weight=5)
        self._build_step_tab()
        self._build_checks_tab()
        self._build_procs_tab()
        self._build_monitor_tab()
        self._build_log_tab()

        self.status = tk.Label(r, text="", anchor="w", bg="#e2e8f0", font=("Segoe UI", 9), padx=8, pady=3)
        self.status.pack(fill="x", side="bottom")

    def _text(self, parent, height=10, mono=True, bg="#ffffff"):
        f = ttk.Frame(parent)
        t = tk.Text(f, height=height, wrap="none" if mono else "word", bg=bg, relief="solid", bd=1,
                    font=("Consolas", 10) if mono else ("Segoe UI", 10))
        sy = ttk.Scrollbar(f, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sy.set)
        t.pack(side="left", fill="both", expand=True)
        sy.pack(side="left", fill="y")
        t.tag_configure("err", foreground="#b91c1c")
        t.tag_configure("ok", foreground="#15803d")
        t.tag_configure("dim", foreground="#64748b")
        t.tag_configure("hl", foreground="#1d4ed8")
        return f, t

    def _build_step_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Шаг  ")
        self.tab_step = tab
        self.step_title = ttk.Label(tab, text="", style="Big.TLabel")
        self.step_title.pack(anchor="w")
        self.step_meta = ttk.Label(tab, text="", foreground="#475569")
        self.step_meta.pack(anchor="w", pady=(2, 4))
        self.step_desc = tk.Message(tab, text="", width=810, font=("Segoe UI", 10), anchor="w", justify="left")
        self.step_desc.pack(anchor="w", fill="x")
        self.step_risk = tk.Message(tab, text="", width=810, font=("Segoe UI", 10), fg="#b45309", anchor="w", justify="left")
        self.step_risk.pack(anchor="w", fill="x")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=6)
        self.btn_run = ttk.Button(bar, text="Выполнить шаг", style="Run.TButton", command=lambda: self.run_step(self.sel_step))
        self.btn_run.pack(side="left")
        ttk.Button(bar, text="Отметить вручную…", command=lambda: self.mark_manual(self.sel_step)).pack(side="left", padx=6)
        ttk.Button(bar, text="Сбросить шаг", command=lambda: self.reset_step(self.sel_step)).pack(side="left")
        ttk.Button(bar, text="Сбросить весь ход", command=self.reset_all).pack(side="right")
        self.step_state = ttk.Label(bar, text="", font=("Segoe UI", 10, "bold"))
        self.step_state.pack(side="left", padx=14)
        pw = ttk.Panedwindow(tab, orient="vertical")
        pw.pack(fill="both", expand=True)
        f1 = ttk.Labelframe(pw, text="SQL шага (то, что будет выполнено)")
        f, self.step_sql = self._text(f1, 9, bg="#f8fafc")
        f.pack(fill="both", expand=True, padx=4, pady=4)
        pw.add(f1, weight=2)
        f2 = ttk.Labelframe(pw, text="Результат последнего запуска")
        f, self.step_outw = self._text(f2, 12)
        f.pack(fill="both", expand=True, padx=4, pady=4)
        pw.add(f2, weight=3)

    def _build_checks_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Проверки  ")
        self.tab_checks = tab
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Стадия:").pack(side="left")
        self.stage_var = tk.StringVar(value="авто")
        ttk.Combobox(bar, textvariable=self.stage_var, width=22, state="readonly",
                     values=["авто", "pre — до миграции", "window — окно", "post — после окна"]).pack(side="left", padx=4)
        ttk.Button(bar, text="Запустить все проверки", style="Run.TButton", command=lambda: self.run_checks()).pack(side="left", padx=6)
        self.checks_sum = ttk.Label(bar, text="", font=("Segoe UI", 10, "bold"))
        self.checks_sum.pack(side="left", padx=10)
        cols = ("grp", "id", "title", "value", "res", "msg")
        self.chk = ttk.Treeview(tab, columns=cols, show="headings")
        for c, t, w in zip(cols, ("Группа", "№", "Проверка", "Значение", "Итог", "Комментарий"), (90, 40, 360, 200, 70, 300)):
            self.chk.heading(c, text=t)
            self.chk.column(c, width=w, stretch=c in ("title", "msg"))
        self.chk.tag_configure("ok", foreground="#15803d")
        self.chk.tag_configure("warn", foreground="#b45309", background="#fef3c7")
        self.chk.tag_configure("fail", foreground="#b91c1c", background="#fee2e2")
        self.chk.tag_configure("info", foreground="#334155")
        sb = ttk.Scrollbar(tab, orient="vertical", command=self.chk.yview)
        self.chk.configure(yscrollcommand=sb.set)
        self.chk.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

    def _build_procs_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Процессы  ")
        self.tab_procs = tab
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Остановить выбранный", command=self.kill_selected).pack(side="left")
        self.show_hidden = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="показывать служебные (монитор)", variable=self.show_hidden).pack(side="left", padx=10)
        self.procs_sum = ttk.Label(bar, text="")
        self.procs_sum.pack(side="right")
        pw = ttk.Panedwindow(tab, orient="vertical")
        pw.pack(fill="both", expand=True)
        cols = ("id", "title", "kind", "pid", "start", "elapsed", "status", "last")
        f = ttk.Frame(pw)
        self.ptree = ttk.Treeview(f, columns=cols, show="headings", height=9)
        for c, t, w in zip(cols, ("#", "Процесс", "Тип", "PID", "Старт", "Длится", "Статус", "Последняя строка вывода"),
                           (36, 300, 90, 60, 70, 70, 100, 380)):
            self.ptree.heading(c, text=t)
            self.ptree.column(c, width=w, stretch=c in ("title", "last"))
        self.ptree.tag_configure("running", foreground="#1d4ed8", background="#dbeafe")
        self.ptree.tag_configure("ok", foreground="#15803d")
        self.ptree.tag_configure("fail", foreground="#b91c1c", background="#fee2e2")
        self.ptree.tag_configure("killed", foreground="#b45309")
        self.ptree.pack(fill="both", expand=True)
        self.ptree.bind("<<TreeviewSelect>>", self._proc_select)
        pw.add(f, weight=2)
        f2 = ttk.Labelframe(pw, text="Вывод выбранного процесса (обновляется на лету)")
        fr, self.proc_out = self._text(f2, 12)
        fr.pack(fill="both", expand=True, padx=4, pady=4)
        pw.add(f2, weight=3)

    def _build_monitor_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Монитор БД  ")
        self.tab_mon = tab
        bar = ttk.Frame(tab)
        bar.pack(fill="x")
        self.mon_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Опрос базы каждые", variable=self.mon_on).pack(side="left")
        self.mon_int = tk.IntVar(value=self.cfg.monitor_interval)
        ttk.Spinbox(bar, from_=5, to=300, width=4, textvariable=self.mon_int).pack(side="left", padx=3)
        ttk.Label(bar, text="сек").pack(side="left")
        ttk.Button(bar, text="Опросить сейчас", command=lambda: self.poll_monitor(force=True)).pack(side="left", padx=8)
        self.mon_lbl = ttk.Label(bar, text="", foreground="#475569")
        self.mon_lbl.pack(side="right")
        self.mon_state = tk.Label(tab, text="", justify="left", anchor="w", font=("Consolas", 10), bg="#f1f5f9", padx=8, pady=6)
        self.mon_state.pack(fill="x", pady=6)

        def tv(title, cols, heads, widths, h):
            lf = ttk.Labelframe(tab, text=title)
            lf.pack(fill="both", expand=True, pady=3)
            t = ttk.Treeview(lf, columns=cols, show="headings", height=h)
            for c, hd, w in zip(cols, heads, widths):
                t.heading(c, text=hd)
                t.column(c, width=w, stretch=(c == cols[-1]))
            t.pack(fill="both", expand=True, padx=3, pady=3)
            return t
        self.mon_sess = tv("Сессии утилиты в базе (v$session, module = SLDMIG)",
                           ("sid", "ser", "st", "act", "sec", "sql", "undo", "ev"),
                           ("SID", "Serial#", "Статус", "Шаг", "Сек.", "SQL_ID", "UNDO, МБ", "Ожидание / событие"),
                           (60, 70, 80, 70, 60, 120, 80, 400), 4)
        self.mon_long = tv("Длительные операции (v$session_longops)",
                           ("sid", "op", "tgt", "pct", "el", "rem", "bar"),
                           ("SID", "Операция", "Объект", "%", "Прошло, с", "Осталось, с", "Ход"),
                           (60, 220, 200, 60, 80, 90, 300), 4)
        self.mon_log = tv("Журнал пересчёта сальдо (XPROCESS_LOG)", ("at", "t", "msg"), ("Время", "Тип", "Сообщение"), (130, 40, 700), 5)

    def _build_log_tab(self):
        tab = ttk.Frame(self.nb, padding=8)
        self.nb.add(tab, text="  Журнал  ")
        f, self.logw = self._text(tab, 20)
        f.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ служебное
    def log(self, msg, tag=None):
        self.logw.insert("end", "%s  %s\n" % (now_s(), msg), tag)
        self.logw.see("end")

    def _state_path(self):
        d = APP_DIR / "state"
        d.mkdir(exist_ok=True)
        return d / ("state_%s.json" % self.profile_var.get())

    def _load_state(self):
        self.state = {"steps": {}, "jqp_saved": None}
        p = self._state_path()
        if p.exists():
            try:
                self.state.update(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
        for sid, v in self.state["steps"].items():
            if v.get("status") == "running":
                v["status"] = "pending"

    def _save_state(self):
        self._state_path().write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")

    def st(self, sid):
        return self.state["steps"].get(sid, {}).get("status", "pending")

    def set_status(self, sid, status, note=""):
        self.state["steps"][sid] = {"status": status, "at": now_s(), "note": note,
                                    "dry": bool(self.dry_var.get()) and status != "skipped"}
        self._save_state()
        self._refresh_steps()
        if sid == self.sel_step:
            self._show_step(sid, keep_out=True)
        self.log("Шаг %s: %s%s" % (sid, STATUS_RU[status], (" — " + note) if note else ""),
                 {"failed": "err", "done": "ok", "dry": "hl"}.get(status))

    def profile(self):
        return self.cfg.profiles.get(self.profile_var.get(), {})

    def is_prod(self):
        return self.profile().get("kind", "test").lower() == "prod"

    def current_step(self):
        for s in S.STEPS:
            if s["phase"] != "RB" and self.st(s["id"]) in ("pending", "failed", "running"):
                return s["id"]
        return None

    def auto_stage(self):
        cur = self.current_step()
        if cur is None:
            return "post"
        ids = [s["id"] for s in S.STEPS]
        i = ids.index(cur)
        if i <= ids.index("W1"):
            return "pre"
        if i <= ids.index("W9"):
            return "window"
        return "post"

    # ------------------------------------------------------------------ обновление вида
    def _refresh_steps(self):
        cur = self.current_step()
        total = done = 0
        for s in S.STEPS:
            stt = self.st(s["id"])
            tags = [stt]
            if s["id"] == cur:
                tags = ["current"]
            mark = "  ◀ вы здесь" if s["id"] == cur else ""
            self.tree.item(s["id"], text="%s  %s  %s%s" % (STATUS_ICON[stt], s["id"], s["title"], mark),
                           values=(STATUS_RU[stt], s["when"]), tags=tags)
            if s["phase"] != "RB":
                total += 1
                done += stt in ("done", "dry", "skipped")
        self.progress["value"] = 100.0 * done / total
        self.progress_lbl.config(text="Пройдено %d из %d шагов%s" % (done, total, ("  •  текущий: " + cur) if cur else "  •  всё пройдено"))
        mode = "СУХОЙ ПРОГОН — изменяющие шаги не выполняются, показывается SQL" if self.dry_var.get() else "БОЕВОЙ РЕЖИМ — шаги меняют базу"
        bg = "#0f766e" if self.dry_var.get() else ("#b91c1c" if self.is_prod() else "#b45309")
        self.banner.config(text="%s   |   профиль %s (%s)" % (mode, self.profile_var.get(), "PROD" if self.is_prod() else "тест"), bg=bg)

    def _tree_select(self, e=None):
        sel = self.tree.selection()
        if sel and sel[0] in [s["id"] for s in S.STEPS]:
            self.sel_step = sel[0]
            self._show_step(sel[0])

    def step_sql_text(self, s):
        """SQL шага с подставленными значениями — для показа и выполнения."""
        act = s.get("action")
        if act == "checks":
            return "-- %d проверок, стадия «%s». Список — на вкладке «Проверки».\n" % (len(S.CHECKS), s["stage"])
        if act == "backup_pkg":
            return "-- чтение user_source для PKG_SLD_UTIL (PACKAGE, PACKAGE BODY) и сохранение в backups\\\n"
        if act == "install_pkg":
            return "-- сравнение user_source с файлом, затем при отличии:\n@%s\nshow errors\n" % rel(self.cfg.scripts_dir / s["script"])
        if act == "balance":
            return self.balance_sql()
        if s["kind"] == "manual":
            return "-- ручной шаг: выполняется людьми, в утилите только отмечается\n"
        sql = s.get("sql", "")
        jq = self.state.get("jqp_saved") or self.profile().get("jqp_default", "1000")
        sql = sql.replace("{JQP_SAVED}", str(jq))
        if "{PKG_BACKUP}" in sql:
            sp, bd = self.backup_files()
            sql = sql.replace("{PKG_BACKUP}", "-- код пакета из копии:\n--   %s\n--   %s" % (rel(sp) if sp else "НЕТ КОПИИ", rel(bd) if bd else "НЕТ КОПИИ"))
        tail = "\n".join(l for l in s.get("info_sql", "").splitlines() if not l.startswith("set heading") and "'@@" not in l)
        return sql + ("\n-- контроль после шага:\n" + tail if tail.strip() else "")

    def _show_step(self, sid, keep_out=False):
        s = S.step_by_id(sid)
        stt = self.st(sid)
        self.step_title.config(text="%s. %s" % (s["id"], s["title"]))
        self.step_meta.config(text="Тип: %s   •   Кто: %s   •   Когда: %s   •   Длительность: %s%s" % (
            KIND_RU[s["kind"]], s["who"], s["when"], s["dur"], ("   •   Скрипт: " + s["script"]) if s.get("script") else ""))
        self.step_desc.config(text=s["desc"])
        self.step_risk.config(text=("Риск: " + s["risk"]) if s.get("risk") and s["risk"] != "—" else "")
        info = self.state["steps"].get(sid, {})
        self.step_state.config(text="%s %s%s" % (STATUS_ICON[stt], STATUS_RU[stt], ("  (%s)" % info.get("at", "")) if info else ""),
                               foreground={"done": "#15803d", "failed": "#b91c1c", "running": "#1d4ed8", "dry": "#0f766e",
                                           "skipped": "#b45309"}.get(stt, "#475569"))
        self.btn_run.config(text="Отметить выполненным" if s["kind"] == "manual" else
                            ("Выполнить шаг" if s["kind"] == "check" or not self.dry_var.get() else "Сухой прогон шага"))
        self.step_sql.config(state="normal")
        self.step_sql.delete("1.0", "end")
        self.step_sql.insert("end", self.step_sql_text(s))
        self.step_sql.config(state="disabled")
        if not keep_out:
            self.step_outw.delete("1.0", "end")
            for line, tag in self.step_out.get(sid, []):
                self.step_outw.insert("end", line + "\n", tag)
            if info.get("note"):
                self.step_outw.insert("end", "\n[%s] %s\n" % (info.get("at"), info["note"]), "dim")
            self.step_outw.see("end")

    def out(self, sid, line, tag=None):
        if tag is None and re.match(r"^\s*(ORA-|SP2-|PLS-|ERROR)", line):
            tag = "err"
        self.step_out.setdefault(sid, []).append((line, tag))
        if sid == self.sel_step:
            self.step_outw.insert("end", line + "\n", tag)
            self.step_outw.see("end")

    # ------------------------------------------------------------------ соединение
    def _profile_changed(self):
        self.connected = False
        self.conn_lbl.config(text="  не подключено  ", bg="#b0b7c3")
        self.dry_var.set(True)
        self._load_state()
        self.step_out.clear()
        self._refresh_steps()
        self._show_step(self.sel_step)

    def connect_dialog(self):
        name = self.profile_var.get()
        pwd = os.environ.get("SLDMIG_PWD_" + name.upper())
        if not pwd:
            pwd = simpledialog.askstring("Пароль", "Пароль пользователя %s для профиля %s\n(хранится только в памяти до закрытия окна):"
                                         % (self.profile().get("user", ""), name), show="*", parent=self.root)
        if pwd:
            self.connect(name, pwd)

    def connect(self, name, pwd):
        self.profile_var.set(name)
        self.eng.set_profile(name, pwd)
        self.conn_lbl.config(text="  соединение…  ", bg="#64748b")

        def done(p):
            if p.status == "ok" and "CONNECTED" in p.marks:
                self.connected, self.host = True, self.profile().get("alias") or p.marks["CONNECTED"]
                self.conn_lbl.config(text="  %s • %s@%s • %s  " % (name, self.profile()["user"], self.host, p.marks.get("DB", "")),
                                     bg="#b91c1c" if self.is_prod() else "#15803d")
                self.log("Подключено: профиль %s, сервер %s, %s" % (name, self.host, p.marks.get("VER", "")), "ok")
                self.poll_monitor(force=True)
            else:
                self.connected = False
                self.conn_lbl.config(text="  ошибка соединения  ", bg="#b91c1c")
                msg = "; ".join(p.errors[:3]) or "нет ответа"
                if p.rc == 7:
                    msg = "Это не та база: сервер не совпадает с expected_host профиля. " + msg
                self.log("Соединение не удалось: " + msg, "err")
                if not self.auto:
                    messagebox.showerror("Соединение", msg, parent=self.root)
        self.eng.run("Проверка соединения", S.mark("DB", "sys_context('USERENV','DB_NAME')||' '||to_char(sysdate,'hh24:mi')")
                     + S.mark("VER", "select max(version) from v$instance"), tag="connect", on_done=done)

    def need_conn(self):
        if not self.connected:
            if not self.auto:
                messagebox.showwarning("Нет соединения", "Сначала подключитесь к базе (кнопка «Подключиться»).", parent=self.root)
            return False
        return True

    def _dry_toggled(self):
        if not self.dry_var.get():
            ok = False
            if self.is_prod():
                a = simpledialog.askstring("БОЕВОЙ РЕЖИМ НА PROD",
                                           "Вы выключаете сухой прогон на ПРОДУКТИВНОЙ базе.\nШаги начнут менять базу клиента.\n\n"
                                           "Есть письменное согласие клиента и назначенное окно?\nВведите слово PROD для подтверждения:",
                                           parent=self.root)
                ok = (a or "").strip() == "PROD"
            else:
                ok = messagebox.askyesno("Боевой режим", "Выключить сухой прогон?\nИзменяющие шаги начнут реально менять базу %s."
                                         % self.profile_var.get(), icon="warning", parent=self.root)
            if not ok:
                self.dry_var.set(True)
        self.log("Режим: %s" % ("сухой прогон" if self.dry_var.get() else "БОЕВОЙ"), "hl")
        self._refresh_steps()
        self._show_step(self.sel_step, keep_out=True)

    # ------------------------------------------------------------------ шаги
    def can_run(self, sid):
        if self.expert_var.get():
            return True, ""
        s = S.step_by_id(sid)
        if s["phase"] == "RB":
            return True, ""
        for p in S.STEPS:
            if p["id"] == sid:
                return True, ""
            if p["phase"] == "RB":
                continue
            if self.st(p["id"]) not in ("done", "dry", "skipped"):
                return False, "Сначала выполните шаг %s «%s»" % (p["id"], p["title"])
        return True, ""

    def mark_manual(self, sid):
        note = "" if self.auto else simpledialog.askstring(
            "Отметить вручную", "Шаг %s будет отмечен как выполненный вне утилиты.\nКто и когда выполнил, чем подтверждено:" % sid,
            parent=self.root)
        if note is None:
            return
        self.set_status(sid, "skipped" if S.step_by_id(sid)["kind"] != "manual" else "done", note or "отмечено вручную")

    def reset_step(self, sid):
        self.state["steps"].pop(sid, None)
        self.step_out.pop(sid, None)
        self._save_state()
        self._refresh_steps()
        self._show_step(sid)

    def reset_all(self):
        if self.auto or messagebox.askyesno("Сброс", "Сбросить отметки всех шагов профиля %s?\n(в базе ничего не меняется)" % self.profile_var.get(),
                                            parent=self.root):
            self.state = {"steps": {}, "jqp_saved": None}
            self.step_out.clear()
            self._save_state()
            self._refresh_steps()
            self._show_step(self.sel_step)

    def confirm_change(self, s):
        if self.auto:
            return False            # автодемо никогда не выполняет боевые изменения
        text = "Шаг %s: %s\n\nБаза: %s (%s)\nТип: %s\nРиск: %s\n\nВыполнить?" % (
            s["id"], s["title"], self.profile_var.get(), self.host, KIND_RU[s["kind"]], s.get("risk", "—"))
        if self.is_prod():
            a = simpledialog.askstring("Изменение на PROD", text + "\n\nВведите слово PROD для подтверждения:", parent=self.root)
            return (a or "").strip() == "PROD"
        return messagebox.askyesno("Изменение базы", text, icon="warning", parent=self.root)

    def run_step(self, sid):
        s = S.step_by_id(sid)
        if s["kind"] == "manual":
            return self.mark_manual(sid)
        ok, why = self.can_run(sid)
        if not ok:
            self.log(why, "err")
            if not self.auto:
                messagebox.showinfo("Порядок шагов", why + "\n\n(или включите режим «Эксперт»)", parent=self.root)
            return
        if not self.need_conn():
            return
        if self.st(sid) == "running":
            return
        dry = self.dry_var.get()
        act = s.get("action")
        if s["kind"] in ("change", "long") and not dry and act != "install_pkg":
            if not self.confirm_change(s):
                return
        self.step_out[sid] = []
        self.select_step(sid)
        self.set_status(sid, "running")
        self.out(sid, "=== %s  %s. %s  [%s] ===" % (now_s(), s["id"], s["title"], "сухой прогон" if dry and s["kind"] != "check" else "выполнение"), "hl")
        if act == "checks":
            return self.run_checks(stage=s["stage"], step=sid)
        if act == "backup_pkg":
            return self._step_backup(s)
        if act == "install_pkg":
            return self._step_install(s, dry)
        if act == "balance":
            body, strict = self.balance_sql(), False
        elif act == "rollback":
            body, strict = self._rollback_sql(s, dry)
            if body is None:
                return
        elif s["kind"] == "check":
            body, strict = s["info_sql"], False
        elif dry:
            self.out(sid, "-- В сухом прогоне этот SQL НЕ выполняется:", "dim")
            for l in self.step_sql_text(s).split("-- контроль после шага:")[0].rstrip().splitlines():
                self.out(sid, "    " + l, "dim")
            if s.get("demo_sql"):
                self.out(sid, "-- Вместо него: имитация длительной операции (40 с) для проверки мониторинга", "hl")
            else:
                self.out(sid, "-- Выполняется только контрольный запрос (чтение):", "dim")
            body, strict = s.get("demo_sql", "") + s.get("info_sql", ""), False
        else:
            jq = str(self.state.get("jqp_saved") or self.profile().get("jqp_default", "1000"))
            body = s["sql"].replace("{JQP_SAVED}", jq) + "whenever sqlerror continue\n" + s.get("info_sql", "")
            strict = True
        self._launch(s, body, strict, dry)

    def _launch(self, s, body, strict, dry):
        sid = s["id"]
        kind = "чтение" if (s["kind"] == "check" or dry) else "ИЗМЕНЕНИЕ"
        self.eng.run("%s. %s" % (sid, s["title"]), body, kind=kind, tag=sid, strict=strict,
                     on_done=lambda p: self._step_done(s, p, dry))

    def _step_done(self, s, p, dry):
        sid = s["id"]
        if p.status == "killed":
            return self.set_status(sid, "failed", "процесс остановлен пользователем")
        if p.status != "ok":
            return self.set_status(sid, "failed", "; ".join(p.errors[:2]) or ("код завершения %s" % p.rc))
        if p.marks.get("JQP") and sid == "W1" and p.marks["JQP"] != "0" and not self.state.get("jqp_saved"):
            self.state["jqp_saved"] = p.marks["JQP"]
            self.out(sid, "Запомнено job_queue_processes = %s" % p.marks["JQP"], "hl")
        jq = str(self.state.get("jqp_saved") or self.profile().get("jqp_default", "1000"))
        bad = []
        for k, exp in s.get("expect", {}).items():
            exp = exp.replace("{JQP_SAVED}", jq)
            got = p.marks.get(k)
            okk = got == exp
            self.out(sid, "контроль %-12s = %-12s ожидается %-12s %s" % (k, got, exp, "OK" if okk else "НЕ СОВПАЛО"), "ok" if okk else "err")
            if not okk:
                bad.append(k)
        for k, v in p.marks.items():
            if k not in s.get("expect", {}) and k != "CONNECTED":
                self.out(sid, "значение %-12s = %s" % (k, v), "dim")
        if p.errors:
            return self.set_status(sid, "failed", "; ".join(p.errors[:2]))
        if s["kind"] in ("change", "long") and dry:
            return self.set_status(sid, "dry", "SQL показан, база не менялась" + ("; контроль сейчас не совпал бы: " + ", ".join(bad) if bad else ""))
        if bad:
            if dry:
                return self.set_status(sid, "dry", "условие шага сейчас не выполнено (%s) — в сухом прогоне не блокирует" % ", ".join(bad))
            return self.set_status(sid, "failed", "контроль не прошёл: " + ", ".join(bad))
        self.set_status(sid, "done", "%.1f с" % p.elapsed)

    # ---- работа с исходным кодом пакета
    def fetch_source(self, typ, cb, tag):
        body = ("set heading off feedback off pagesize 0 linesize 4000\nprompt @@SRC_BEGIN\n"
                "select rtrim(text, chr(10)||chr(13)) from user_source where name='PKG_SLD_UTIL' and type='%s' order by line;\n"
                "prompt @@SRC_END\n" % typ)

        def done(p):
            cb(p, p.lines if p.status == "ok" else None)
        self.eng.run("Чтение кода PKG_SLD_UTIL (%s)" % typ, body, tag=tag, on_done=done)

    @staticmethod
    def norm(lines):
        out = [" ".join(l.split()) for l in lines]
        out = [l for l in out if l and l != "/" and l.upper() != "CREATE OR REPLACE"]
        return out

    def backup_files(self):
        d = APP_DIR / "backups"
        name = self.profile_var.get()
        sp = sorted(d.glob("%s_pkg_sld_util_spec_*.sql" % name))
        bd = sorted(d.glob("%s_pkg_sld_util_body_*.sql" % name))
        return (sp[-1] if sp else None), (bd[-1] if bd else None)

    def _step_backup(self, s):
        sid = s["id"]
        d = APP_DIR / "backups"
        d.mkdir(exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        res = {}

        def save(kind, typ, nxt):
            def cb(p, lines):
                if lines is None or not [l for l in lines if l.strip()]:
                    return self.set_status(sid, "failed", "не удалось прочитать %s: %s" % (typ, "; ".join(p.errors[:2])))
                while lines and not lines[-1].strip():
                    lines.pop()
                f = d / ("%s_pkg_sld_util_%s_%s.sql" % (self.profile_var.get(), kind, ts))
                f.write_text("CREATE OR REPLACE\n" + "\n".join(lines) + "\n/\n", encoding="utf-8")
                res[kind] = f
                self.out(sid, "сохранено: %s  (%d строк)" % (rel(f), len(lines)), "ok")
                nxt()
            return cb
        self.fetch_source("PACKAGE", save("spec", "PACKAGE", lambda: self.fetch_source(
            "PACKAGE BODY", save("body", "PACKAGE BODY", lambda: self.set_status(sid, "done", "копия сохранена в backups")), sid)), sid)

    def _step_install(self, s, dry):
        sid = s["id"]
        f = self.cfg.scripts_dir / s["script"]
        if not f.is_file():
            return self.set_status(sid, "failed", "нет файла %s" % rel(f))
        text = f.read_text(encoding="utf-8-sig")
        if not self.backup_files()[0] and not self.expert_var.get():
            return self.set_status(sid, "failed", "нет копии пакета — выполните шаг P1")

        def cb(p, lines):
            if lines is None:
                return self.set_status(sid, "failed", "; ".join(p.errors[:2]))
            a, b = self.norm(lines), self.norm(text.splitlines())
            if a == b:
                self.out(sid, "Код в базе совпадает с файлом %s (%d строк) — установка не нужна." % (f.name, len(b)), "ok")
                return self.set_status(sid, "done", "уже установлено, идентично файлу")
            diff = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
            self.out(sid, "Код в базе ОТЛИЧАЕТСЯ от файла: в базе %d строк, в файле %d, отличий ≈ %d." % (len(a), len(b), diff), "hl")
            if dry:
                self.out(sid, "-- В сухом прогоне установка не выполняется: @%s" % rel(f), "dim")
                return self.set_status(sid, "dry", "отличий ≈ %d, установка показана" % diff)
            if not self.confirm_change(s):
                return self.set_status(sid, "pending")
            body = text.rstrip() + ("\n" if text.rstrip().endswith("/") else "\n/\n") + "show errors\n" + s.get("info_sql", "")
            self._launch(s, body, False, dry)
        self.fetch_source(s["pkg_type"], cb, sid)

    def _rollback_sql(self, s, dry):
        sid = s["id"]
        sp, bd = self.backup_files()
        if (not sp or not bd) and self.is_prod():
            a = sorted(self.cfg.backup_prod_dir.glob("pkg_sld_util_spec_PROD_*.sql"))
            b = sorted(self.cfg.backup_prod_dir.glob("pkg_sld_util_body_PROD_*.sql"))
            sp, bd = (a[-1] if a else None), (b[-1] if b else None)
        if not sp or not bd:
            self.set_status(sid, "failed", "нет копии пакета для отката (шаг P1)")
            return None, False
        jq = str(self.state.get("jqp_saved") or self.profile().get("jqp_default", "1000"))
        if dry:
            self.out(sid, "-- В сухом прогоне откат НЕ выполняется. Код пакета будет взят из:", "dim")
            self.out(sid, "    %s\n    %s" % (rel(sp), rel(bd)), "dim")
            for l in s["sql"].replace("{JQP_SAVED}", jq).splitlines():
                self.out(sid, "    " + l, "dim")
            return s["info_sql"], False
        pk = ""
        for f in (sp, bd):
            t = f.read_text(encoding="utf-8-sig").rstrip()
            pk += t + ("\n" if t.endswith("/") else "\n/\n") + "show errors\n"
        return s["sql"].replace("{JQP_SAVED}", jq).replace("{PKG_BACKUP}", pk) + "whenever sqlerror continue\n" + s["info_sql"], True

    def balance_sql(self):
        p = self.profile()
        d = p.get("check_date", "")
        dexpr = "date '%s'" % d if re.match(r"^\d{4}-\d\d-\d\d$", d) else "trunc(sysdate,'mm') - 1"
        cont, sc = p.get("check_cont", "2171"), p.get("check_sc", "2905,2609,105520,9805")
        return """-- контрольная дата: %(d)s, счёт %(cont)s, аналитики %(sc)s
-- XSLD — глобальная временная таблица: постоянные данные не меняются
declare
  v_dt date := %(dexpr)s;
  n1 int; n2 int; t0 date := sysdate;
begin
  delete from xsld where id in ('MIG_FAST','MIG_FC');
  un$sld.make(v_dt,'MIG_FAST','ACD1J','%(cont)s',' ','%(sc)s');
  dbms_output.put_line('fast (TXSLD):  '||round((sysdate-t0)*86400)||' s');  t0 := sysdate;
  un$sld.make(v_dt,'MIG_FC','ACD1J','%(cont)s',' ','%(sc)s', pOldMethod => true);
  dbms_output.put_line('classic (FC):  '||round((sysdate-t0)*86400)||' s');
  select count(*) into n1 from xsld where id = 'MIG_FAST';
  select count(*) into n2 from xsld where id = 'MIG_FC';
  dbms_output.put_line('rows: fast='||n1||'  classic='||n2||'  date='||to_char(v_dt,'dd.mm.yyyy'));
end;
/
prompt Differences (expected: no rows):
select nvl(a.cont,b.cont) cont, nvl(a.sc,b.sc) sc, nvl(a.dep,b.dep) dep,
       a.suma fast_suma, b.suma fc_suma, a.cant fast_cant, b.cant fc_cant
from (select * from xsld where id = 'MIG_FAST') a
full join (select * from xsld where id = 'MIG_FC') b
  on a.cont = b.cont and a.sc = b.sc and nvl(a.dep,-1) = nvl(b.dep,-1) and nvl(a.ap,'-') = nvl(b.ap,'-')
where (nvl(a.suma,0) <> nvl(b.suma,0) or nvl(a.cant,0) <> nvl(b.cant,0)) and rownum <= 50;
%(m1)s%(m2)s%(m3)srollback;
""" % dict(d=d or "конец прошлого месяца", dexpr=dexpr, cont=cont, sc=sc,
           m1=S.mark("FAST_ROWS", "select count(*) from xsld where id='MIG_FAST'"),
           m2=S.mark("FC_ROWS", "select count(*) from xsld where id='MIG_FC'"),
           m3=S.mark("DIFF", "select count(*) from (select * from xsld where id='MIG_FAST') a full join "
                             "(select * from xsld where id='MIG_FC') b on a.cont=b.cont and a.sc=b.sc and nvl(a.dep,-1)=nvl(b.dep,-1) "
                             "and nvl(a.ap,'-')=nvl(b.ap,'-') where nvl(a.suma,0)<>nvl(b.suma,0) or nvl(a.cant,0)<>nvl(b.cant,0)"))

    # ------------------------------------------------------------------ проверки
    def local_checks(self):
        cfg, res = self.cfg, []

        def add(i, title, ok, val, msg="", bad="fail"):
            res.append(dict(id=i, group="Локально", title=title, value=str(val), status="ok" if ok else bad, msg=msg))
        sp = Path(cfg.sqlplus)
        found = sp.is_file() or any((Path(p) / cfg.sqlplus).is_file() or (Path(p) / (cfg.sqlplus + ".exe")).is_file()
                                    for p in os.environ.get("PATH", "").split(os.pathsep) if p)
        add("L1", "sqlplus найден", found, cfg.sqlplus, "" if found else "укажите путь в sld_migrator.ini")
        miss = [n for n in ("02_pkg_sld_util_spec.sql", "03_pkg_sld_util_body.sql") if not (cfg.scripts_dir / n).is_file()]
        add("L2", "Файлы пакета (02, 03) на месте", not miss, "..\\scripts", ("нет: " + ", ".join(miss)) if miss else "")
        sp_, bd_ = self.backup_files()
        prod_bk = list(cfg.backup_prod_dir.glob("pkg_sld_util_*PROD*.sql")) if self.is_prod() else []
        add("L3", "Копия пакета для отката", bool(sp_ and bd_) or len(prod_bk) >= 2,
            (sp_.name if sp_ else (prod_bk[0].parent if prod_bk else "нет")),
            "" if (sp_ and bd_) else ("взята из backup_prod" if prod_bk else "появится после шага P1"), bad="warn")
        try:
            (APP_DIR / "logs").mkdir(exist_ok=True)
            t = APP_DIR / "logs" / ".w"
            t.write_text("x")
            t.unlink()
            okw = True
        except Exception:
            okw = False
        add("L4", "Папка журналов доступна на запись", okw, "logs")
        n = dt.datetime.now()
        h6 = (dt.datetime.combine(n.date() + dt.timedelta(days=1 if n.hour >= 6 else 0), dt.time(6)) - n).total_seconds() / 3600
        res.append(dict(id="L5", group="Локально", title="Часов до 06:00 (начало утренней нагрузки)", value="%.1f" % h6,
                        status="info" if h6 >= 5 or self.auto_stage() != "window" else "warn",
                        msg="пересчёт занимает ≈4 ч" if h6 < 5 else ""))
        res.append(dict(id="L6", group="Локально", title="Режим утилиты", value="сухой прогон" if self.dry_var.get() else "БОЕВОЙ",
                        status="info", msg=""))
        return res

    def run_checks(self, stage=None, step=None):
        if not self.need_conn():
            if step:
                self.set_status(step, "pending")
            return
        if stage is None:
            v = self.stage_var.get().split(" ")[0]
            stage = self.auto_stage() if v == "авто" else v
        body = "set heading off feedback off pagesize 0 linesize 2000\n"
        for c in S.CHECKS:
            sql = c["sql"].strip()
            expr = "(%s)" % sql
            body += "prompt @@BEGIN|%s\nselect '@@C_%s|'||%s from dual;\n" % (c["id"], c["id"], expr)
        self.checks_sum.config(text="выполняется…", foreground="#1d4ed8")
        local = self.local_checks()

        def done(p):
            res = list(local)
            errs = {}
            cur = None
            # ошибки ORA привязываем к проверке по порядку вывода
            for ev in p.seq:
                if ev.startswith("@@BEGIN|"):
                    cur = ev.split("|")[1]
                elif cur and re.match(r"^(ORA-|SP2-)", ev):
                    errs.setdefault(cur, ev)
            cfgp = self.profile()
            for c in S.CHECKS:
                val = p.marks.get("C_" + c["id"])
                rule = c["rule"].get(stage, S._info) if isinstance(c["rule"], dict) else c["rule"]
                if p.status != "ok" and val is None:
                    st_, msg = "fail", "; ".join(p.errors[:1]) or "нет ответа базы"
                elif val is None:
                    st_, msg = "fail", errs.get(c["id"], "нет значения")
                else:
                    try:
                        st_, msg = rule(val, cfgp)
                        if c["id"] == "D1" and cfgp.get("alias") and st_ == "ok":
                            val = cfgp["alias"]         # псевдоним сервера вместо настоящего имени
                    except Exception as e:      # noqa
                        st_, msg = "warn", "ошибка правила: %r" % e
                res.append(dict(id=c["id"], group=c["group"], title=c["title"], value=val if val is not None else "—", status=st_, msg=msg))
            self.checks_result, self.checks_stage = res, stage
            self._show_checks()
            nf = sum(r["status"] == "fail" for r in res)
            nw = sum(r["status"] == "warn" for r in res)
            self.log("Проверки (стадия %s): всего %d, ошибок %d, предупреждений %d" % (stage, len(res), nf, nw), "err" if nf else "ok")
            if step:
                for r in res:
                    self.out(step, "%-4s %-58s %-28s %-5s %s" % (r["id"], r["title"][:58], str(r["value"])[:28], r["status"].upper(), r["msg"]),
                             {"fail": "err", "ok": "ok", "warn": "hl"}.get(r["status"], "dim"))
                if nf and self.dry_var.get():
                    self.set_status(step, "dry", "несоответствий: %d — в сухом прогоне не блокирует (см. «Проверки»)" % nf)
                elif nf:
                    self.set_status(step, "failed", "проверок с ошибкой: %d (см. вкладку «Проверки»)" % nf)
                else:
                    self.set_status(step, "done", "проверок %d, предупреждений %d" % (len(res), nw))
        p = self.eng.run("Проверки (%s)" % stage, body, tag=step or "checks", on_done=done)
        p.seq = []

    def _show_checks(self):
        self.chk.delete(*self.chk.get_children())
        for r in self.checks_result:
            self.chk.insert("", "end", values=(r["group"], r["id"], r["title"], r["value"],
                                               {"ok": "✔ OK", "warn": "! ВНИМ.", "fail": "✖ СТОП", "info": "· инфо"}[r["status"]], r["msg"]),
                            tags=(r["status"],))
        nf = sum(r["status"] == "fail" for r in self.checks_result)
        nw = sum(r["status"] == "warn" for r in self.checks_result)
        no = sum(r["status"] == "ok" for r in self.checks_result)
        self.checks_sum.config(text="стадия «%s»:  ✔ %d   ! %d   ✖ %d   (%s)" % (self.checks_stage, no, nw, nf, now_s()),
                               foreground="#b91c1c" if nf else ("#b45309" if nw else "#15803d"))

    # ------------------------------------------------------------------ монитор БД
    MON_SQL = """set heading off feedback off pagesize 0 linesize 2000
select '@@M_TIME|'||to_char(sysdate,'dd.mm.yyyy hh24:mi:ss') from dual;
select '@@M_RESTRICT|'||status from user_triggers where trigger_name='TMDB_CM_RESTRICT_DML_TRG';
select '@@M_TSLD_TR|'||status from user_triggers where trigger_name='TMDB_CM_TSLD_TR';
select '@@M_JQP|'||value from v$parameter where name='job_queue_processes';
select '@@M_RUNJOBS|'||((select count(*) from v$lock where type='JQ') + (select count(*) from user_scheduler_running_jobs)) from dual;
select '@@M_CMLOCKS|'||count(*) from dba_dml_locks where name='TMDB_CM';
select '@@M_TXSLD_MB|'||nvl(round(sum(bytes)/1048576),0) from user_segments where segment_name='TXSLD';
select '@@M_TSLD_MB|'||nvl(round(sum(bytes)/1048576),0) from user_segments where segment_name='TSLD';
select '@@M_FREE_MB|'||nvl(round(sum(bytes)/1048576),0) from dba_free_space where tablespace_name='TBSUN4_TABLES';
select '@@M_UNDO_MB|'||nvl(round(sum(t.used_ublk)*8192/1048576),0) from v$transaction t;
select '##S|'||s.sid||'|'||s.serial#||'|'||s.status||'|'||nvl(s.action,'-')||'|'||s.last_call_et||'|'||nvl(s.sql_id,'-')||'|'||
       nvl((select round(t.used_ublk*8192/1048576) from v$transaction t where t.addr=s.taddr),0)||'|'||nvl(s.event,'-')
from v$session s where s.module='SLDMIG';
select '##L|'||sid||'|'||opname||'|'||nvl(target_desc,target)||'|'||sofar||'|'||totalwork||'|'||elapsed_seconds||'|'||nvl(time_remaining,0)
from v$session_longops where sofar < totalwork and last_update_time > sysdate - 2/1440;
select '##G|'||to_char(log_date,'dd.mm hh24:mi:ss')||'|'||message_type||'|'||replace(substr(message,1,200),chr(10),' ') from (
  select * from xprocess_log where id > (select max(id) - 20000 from xprocess_log)
  and (message like '%TXSLD%' or message like '%TSLD%' or lower(message) like '%сальдо%')
  order by id desc) where rownum <= 6;
"""

    def poll_monitor(self, force=False):
        if not self.connected or (self.mon_proc and self.mon_proc.status == "running"):
            return
        if not force and (not self.mon_on.get() or time.time() - self.mon_last < max(5, self.mon_int.get())):
            return
        self.mon_last = time.time()

        def done(p):
            self.mon_proc = None
            if p.status != "ok":
                self.mon_lbl.config(text="опрос не удался: %s" % ("; ".join(p.errors[:1]) or p.status), foreground="#b91c1c")
                return
            m = {"at": now_s(), "took": round(p.elapsed, 1), "state": {k[2:]: v for k, v in p.marks.items() if k.startswith("M_")},
                 "sessions": [], "longops": [], "log": []}
            for l in p.lines:
                l = l.strip()
                if l.startswith("##S|"):
                    m["sessions"].append(l[4:].split("|", 7))
                elif l.startswith("##L|"):
                    m["longops"].append(l[4:].split("|", 6))
                elif l.startswith("##G|"):
                    m["log"].append(l[4:].split("|", 2))
            self.monitor = m
            self._show_monitor()
        self.mon_proc = self.eng.run("Монитор БД", self.MON_SQL, tag="monitor", hidden=True, on_done=done, module="mon")

    def _show_monitor(self):
        m = self.monitor
        s = m["state"]
        self.mon_lbl.config(text="последний опрос %s, занял %s с" % (m["at"], m["took"]), foreground="#475569")
        self.mon_state.config(text=(
            "Время сервера: %s      Планировщик (job_queue_processes): %s      Идёт заданий: %s\n"
            "Блокировка проводок (RESTRICT): %-9s Онлайн-сальдо (TSLD_TR): %-9s Блокировок на TMDB_CM: %s\n"
            "TXSLD: %s МБ      TSLD: %s МБ      Свободно в TBSUN4_TABLES: %s МБ      UNDO в работе: %s МБ" % (
                s.get("TIME", "?"), s.get("JQP", "?"), s.get("RUNJOBS", "?"), s.get("RESTRICT", "?"), s.get("TSLD_TR", "?"),
                s.get("CMLOCKS", "?"), s.get("TXSLD_MB", "?"), s.get("TSLD_MB", "?"), s.get("FREE_MB", "?"), s.get("UNDO_MB", "?"))))
        for t, rows in ((self.mon_sess, m["sessions"]), (self.mon_log, m["log"])):
            t.delete(*t.get_children())
            for r in rows:
                t.insert("", "end", values=r)
        self.mon_long.delete(*self.mon_long.get_children())
        for r in m["longops"]:
            try:
                pct = 100.0 * float(r[3]) / max(float(r[4]), 1)
            except Exception:
                pct = 0
            n = int(pct / 4)
            self.mon_long.insert("", "end", values=(r[0], r[1], r[2], "%.0f%%" % pct, r[5], r[6], "█" * n + "░" * (25 - n)))

    # ------------------------------------------------------------------ процессы
    def _proc_select(self, e=None):
        sel = self.ptree.selection()
        if sel:
            self.sel_proc = int(sel[0])
            self._show_proc_out()

    def _show_proc_out(self):
        p = next((x for x in self.eng.procs if x.id == self.sel_proc), None)
        self.proc_out.delete("1.0", "end")
        if p:
            for l in p.lines[-2000:]:
                self.proc_out.insert("end", l + "\n", "err" if re.match(r"^\s*(ORA-|SP2-|PLS-)", l) else None)
            self.proc_out.see("end")

    def kill_selected(self):
        p = next((x for x in self.eng.procs if x.id == self.sel_proc), None)
        if p and p.status == "running":
            if self.auto or messagebox.askyesno(
                    "Остановить процесс", "Остановить «%s»?\n\nКлиент sqlplus будет завершён. Незавершённая транзакция в базе откатится; "
                    "откат длинной операции может занять столько же времени, сколько она шла." % p.title, icon="warning", parent=self.root):
                self.eng.kill(p)
                self.log("Процесс #%d остановлен пользователем" % p.id, "err")

    def _refresh_procs(self):
        shown = [p for p in self.eng.procs if self.show_hidden.get() or not p.hidden][-200:]
        have = set(self.ptree.get_children())
        ids = set()
        for p in shown:
            iid = str(p.id)
            ids.add(iid)
            vals = (p.id, p.title, p.kind, p.pid or "", time.strftime("%H:%M:%S", time.localtime(p.start)),
                    "%d:%02d" % divmod(int(p.elapsed), 60),
                    {"running": "▶ идёт", "ok": "✔ готово", "fail": "✖ ошибка", "killed": "■ остановлен"}[p.status], p.last_line()[:160])
            if iid in have:
                self.ptree.item(iid, values=vals, tags=(p.status,))
            else:
                self.ptree.insert("", 0, iid=iid, values=vals, tags=(p.status,))
        for iid in have - ids:
            self.ptree.delete(iid)
        run = self.eng.running()
        self.procs_sum.config(text="запущено всего: %d   •   идёт сейчас: %d" % (len([p for p in self.eng.procs if not p.hidden]), len(run)))

    # ------------------------------------------------------------------ циклы
    def _pump(self):
        try:
            for _ in range(500):
                ev, p, data = self.eng.events.get_nowait()
                if ev == "start":
                    if not p.hidden:
                        self.log("▶ процесс #%d «%s» запущен (pid %s)" % (p.id, p.title, p.pid))
                elif ev in ("line", "mark"):
                    if hasattr(p, "seq"):
                        p.seq.append(data.strip())
                    if ev == "line" and not p.hidden:
                        if p.tag in self.step_out and p.title.split(".")[0] == p.tag and data.strip():
                            self.out(p.tag, data)
                        if p.id == self.sel_proc:
                            self.proc_out.insert("end", data + "\n")
                            self.proc_out.see("end")
                elif ev == "done":
                    if not p.hidden:
                        self.log("■ процесс #%d «%s»: %s за %.1f с%s" % (p.id, p.title, p.status, p.elapsed,
                                 (" — " + "; ".join(p.errors[:2])) if p.errors else ""), "err" if p.status != "ok" else None)
                    if p.on_done:
                        try:
                            p.on_done(p)
                        except Exception as e:      # noqa
                            self.log("внутренняя ошибка обработчика: %r" % e, "err")
        except queue.Empty:
            pass
        self.root.after(150, self._pump)

    def _tick(self):
        self._refresh_procs()
        self.poll_monitor()
        n = dt.datetime.now()
        run = self.eng.running()
        txt = "%s   •   процессов идёт: %d" % (n.strftime("%d.%m.%Y %H:%M:%S"), len(run))
        if run:
            txt += "   •   " + ";  ".join("%s (%d:%02d)" % ((p.title[:40],) + divmod(int(p.elapsed), 60)) for p in run[:3])
        txt += "   •   журналы: logs\\%s   •   веб: http://127.0.0.1:%d/" % (self.profile_var.get(), self.http_port)
        self.status.config(text=txt)
        WebState.json_text = json.dumps(self.snapshot(), ensure_ascii=False)
        self.root.after(1000, self._tick)

    # ------------------------------------------------------------------ веб
    def snapshot(self):
        steps = []
        for d in S.public_steps():
            info = self.state["steps"].get(d["id"], {})
            d.update(status=info.get("status", "pending"), at=info.get("at", ""), note=info.get("note", ""))
            steps.append(d)
        return dict(
            app=dict(version=VERSION, profile=self.profile_var.get(), prod=self.is_prod(), connected=self.connected, host=self.host,
                     dry=bool(self.dry_var.get()), stage=self.auto_stage(), now=now_s(), live=True,
                     check_date=self.profile().get("check_date", "")),
            phases=[dict(id=a, title=b, sub=c) for a, b, c in S.PHASES], steps=steps, current=self.current_step(),
            procs=[dict(id=p.id, title=p.title, kind=p.kind, status=p.status, elapsed=int(p.elapsed), last=p.last_line()[:120])
                   for p in self.eng.procs if not p.hidden][-15:],
            monitor=self.monitor, checks=self.checks_result, checks_stage=self.checks_stage, checks_def=S.public_checks())

    def _start_http(self):
        srv = ThreadingHTTPServer(("127.0.0.1", self.cfg.http_port), Handler)
        self.http_port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

    def open_web(self, path):
        webbrowser.open("http://127.0.0.1:%d%s" % (self.http_port, path))

    def export_html(self, folder):
        """Сохраняет документацию и карту процесса отдельными файлами (открываются без утилиты)."""
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        snap = self.snapshot()
        snap["app"]["live"] = False
        js = json.dumps(snap, ensure_ascii=False).replace("</", "<\\/")
        for name, html in (("documentation.html", webdocs.DOC_HTML), ("process_map.html", webdocs.PROCESS_HTML)):
            html = html.replace("/*EMBED*/null", js).replace('href="/doc"', 'href="documentation.html"') \
                       .replace('href="/process"', 'href="process_map.html"').replace('src="/screenshots/', 'src="../screenshots/')
            (folder / name).write_text(html, encoding="utf-8")
        return folder

    def select_step(self, sid):
        self.sel_step = sid
        self.tree.selection_set(sid)
        self.tree.see(sid)
        self._show_step(sid)


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    app = App(root)
    if "--export-html" in sys.argv:
        print(app.export_html(APP_DIR / "docs"))
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
