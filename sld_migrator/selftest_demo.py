# -*- coding: utf-8 -*-
"""Автоматический прогон утилиты в СУХОМ режиме на тестовой базе со снимками экрана.

Запуск:  set SLDMIG_PWD_TEST=<пароль>  &&  python selftest_demo.py
Работает только с профилем kind = test и только в сухом прогоне:
изменяющие шаги не выполняются, диалоги подтверждения в этом режиме недоступны.
Нужен пакет Pillow (только для снимков экрана; самой утилите он не нужен).
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image

import sld_migrator as M
import steps as S

PROFILE = "TEST"
SHOTS = M.APP_DIR / "screenshots"
EDGE = [p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe") if os.path.isfile(p)]


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    SHOTS.mkdir(exist_ok=True)
    root = tk.Tk()
    app = M.App(root, auto=True)
    assert app.cfg.profiles[PROFILE].get("kind") == "test", "самопроверка разрешена только на тестовом профиле"
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry("%dx%d+0+0" % (min(1420, sw - 20), min(860, sh - 40)))
    root.attributes("-topmost", True)
    app.profile_var.set(PROFILE)
    app._profile_changed()
    app.reset_all()
    busy = {"n": 0}
    weblock = threading.Lock()

    def shot(name):
        root.lift()
        root.update()
        time.sleep(0.25)
        root.update()
        # PrintWindow рисует окно в память: работает и при заблокированном или перекрытом экране
        u, g = ctypes.windll.user32, ctypes.windll.gdi32
        hwnd = int(root.wm_frame(), 16)
        r, d = wintypes.RECT(), wintypes.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        hdc = u.GetWindowDC(hwnd)
        mdc = g.CreateCompatibleDC(hdc)
        bmp = g.CreateCompatibleBitmap(hdc, w, h)
        g.SelectObject(mdc, bmp)
        u.PrintWindow(hwnd, mdc, 2)

        class BMI(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("a", wintypes.LONG), ("b", wintypes.LONG),
                        ("c", wintypes.DWORD), ("e", wintypes.DWORD)]
        bi = BMI(ctypes.sizeof(BMI), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        g.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        im = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
        g.DeleteObject(bmp)
        g.DeleteDC(mdc)
        u.ReleaseDC(hwnd, hdc)
        if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(d), ctypes.sizeof(d)) == 0:
            im = im.crop((d.left - r.left, d.top - r.top, d.right - r.left, d.bottom - r.top))
        im.save(SHOTS / name)
        print("shot", name, flush=True)

    def web(name, path, w=1500, h=2600):
        if not EDGE:
            return
        busy["n"] += 1

        def run():
            try:
                with weblock:               # снимки строго по одному, у каждого свой профиль браузера
                    subprocess.run([EDGE[0], "--headless=new", "--disable-gpu", "--hide-scrollbars",
                                    "--user-data-dir=" + tempfile.mkdtemp(prefix="sldmig_edge_"),
                                    "--window-size=%d,%d" % (w, h), "--virtual-time-budget=4000",
                                    "--screenshot=%s" % (SHOTS / name),
                                    "http://127.0.0.1:%d%s" % (app.http_port, path)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
                    t_end = time.time() + 40
                    while not (SHOTS / name).is_file() and time.time() < t_end:
                        time.sleep(0.5)
                    time.sleep(1)
                print("web ", name, "ok" if (SHOTS / name).is_file() else "НЕ СОЗДАН", flush=True)
            except Exception as e:      # noqa
                print("web shot failed", name, e, flush=True)
            busy["n"] -= 1
        threading.Thread(target=run, daemon=True).start()

    def idle():
        return not app.eng.running() and app.eng.events.empty()

    def stepdone(sid):
        return lambda: app.st(sid) not in ("pending", "running") and idle()

    def run(sid):
        app.run_step(sid)
        return stepdone(sid)

    def tab(t):
        app.nb.select(t)

    def scenario():
        yield lambda: True
        shot("01_start.png")
        app.connect(PROFILE, os.environ["SLDMIG_PWD_TEST"])
        yield lambda: idle() and (app.connected or "ошибка" in app.conn_lbl.cget("text"))
        assert app.connected, "нет соединения с тестовой базой"
        yield lambda: app.monitor["at"] != ""
        shot("02_connected.png")
        for s in S.STEPS:                       # этап 0 — ручные условия
            if s["phase"] == "E0":
                app.run_step(s["id"])
        yield run("P0")
        shot("03_precheck_step.png")
        tab(app.tab_checks)
        shot("04_checks.png")
        tab(app.tab_step)
        yield run("P1")
        yield run("P2")
        yield run("P3")
        yield run("P4")
        shot("05_package_compare.png")
        app.run_step("P5")
        app.run_step("P6")
        for sid in ("W1", "W2", "W3", "W4", "W5"):
            yield run(sid)
        shot("05b_dry_run_change_step.png")
        yield run("W6")
        yield run("W7")
        # ---- W8: имитация длительной операции, мониторинг
        app.run_step("W8")
        t0 = time.time()
        yield lambda: time.time() - t0 > 9
        shot("06a_long_step_running.png")
        app.poll_monitor(force=True)
        yield lambda: app.mon_proc is None and time.time() - t0 > 12
        tab(app.tab_mon)
        shot("06_monitor_longops.png")
        tab(app.tab_procs)
        app.ptree.selection_set(app.ptree.get_children()[0])
        app._proc_select()
        yield lambda: time.time() - t0 > 16
        shot("07_processes.png")
        root.update()
        web("08_process_map_running.png", "/process", 1500, 3500)
        web("08b_process_step_detail.png", "/process?open=W8", 1500, 1500)
        yield lambda: busy["n"] == 0
        tab(app.tab_step)
        yield stepdone("W8")
        for sid in ("W9", "W10", "W11", "W12", "W13"):
            yield run(sid)
        # ---- W14: настоящая сверка сальдо на 31.12.2026 (≈1 минута)
        app.run_step("W14")
        t1 = time.time()
        yield lambda: time.time() - t1 > 20
        app.poll_monitor(force=True)
        yield lambda: app.mon_proc is None
        tab(app.tab_mon)
        shot("09a_balance_running_monitor.png")
        tab(app.tab_step)
        yield stepdone("W14")
        shot("09_balance_check.png")
        yield run("W15")
        tab(app.tab_checks)
        shot("09b_checks_post.png")
        tab(app.tab_step)
        app.run_step("W16")
        yield run("A1")
        app.run_step("A2")
        yield run("A3")
        app.run_step("A4")
        app.run_step("A5")
        app.select_step("A1")
        shot("10_all_steps.png")
        yield run("RB")
        shot("11_rollback_dry.png")
        tab(app.nb.tabs()[-1])
        shot("12_journal.png")
        tab(app.tab_step)
        yield lambda: True
        root.update()
        web("13_process_map_done.png", "/process", 1500, 3500)
        web("14_documentation.png", "/doc", 1300, 3400)
        yield lambda: busy["n"] == 0
        print("export:", app.export_html(M.APP_DIR / "docs"), flush=True)
        summary = {s["id"]: app.st(s["id"]) for s in S.STEPS}
        print("STATUSES", summary, flush=True)
        print("CHECKS", [(r["id"], r["status"], r["value"], r["msg"]) for r in app.checks_result if r["status"] in ("fail", "warn")], flush=True)

    gen = scenario()
    cond = {"f": next(gen), "t": time.time()}

    def drive():
        try:
            if cond["f"]():
                cond["f"] = next(gen)
                cond["t"] = time.time()
            elif time.time() - cond["t"] > 300:
                print("TIMEOUT waiting; statuses:", {s["id"]: app.st(s["id"]) for s in S.STEPS}, flush=True)
                root.destroy()
                return
        except StopIteration:
            root.destroy()
            return
        except Exception as e:      # noqa
            import traceback
            traceback.print_exc()
            root.destroy()
            return
        root.after(300, drive)
    root.after(1500, drive)
    root.mainloop()


if __name__ == "__main__":
    main()
