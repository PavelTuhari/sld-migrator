# -*- coding: utf-8 -*-
"""Удержание соединения с базой во время многочасовых шагов (W8).

Зачем. Пока идёт pkg_sld_util.rebuild_sld_actual, клиент и сервер часами не передают друг другу ни байта.
Сетевое оборудование на пути (NAT, межсетевой экран, VPN) считает такое соединение брошенным и молча его забывает.
Обе стороны узнают об этом только через 2 часа — по стандартной проверке TCP keepalive операционной системы:
клиент получает ORA-03114, серверный процесс прерывает вызов, и база откатывает всё, что успела посчитать.
Так закончилась первая попытка полного пересчёта на тестовой базе 11–12.11.2026 (обрыв ровно на 120-й минуте).

Что делает модуль. Открывает порт на 127.0.0.1 и прозрачно пересылает байты между sqlplus и сервером базы,
а на соединении с сервером включает TCP keepalive с коротким периодом (по умолчанию проба после 60 с тишины).
Пробы — служебные пакеты TCP без данных: протокол Oracle Net их не видит, сервер базы отвечает на них сам,
сетевое оборудование видит живое соединение. В базе и в настройках операционной системы ничего не меняется.

Используется утилитой автоматически (параметр профиля keepalive, секунды; 0 — выключить).
"""
import re
import socket
import threading


class Relay:
    """Ретранслятор 127.0.0.1:<port> -> host:port с TCP keepalive на стороне сервера базы."""

    def __init__(self, host, port, idle=60, interval=30):
        self.target = (host, int(port))
        self.idle, self.interval = max(10, int(idle)), max(5, int(interval))
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(32)
        self.port = self.srv.getsockname()[1]
        self.opened = 0          # сколько соединений прошло через ретранслятор
        self.active = 0          # сколько открыто сейчас
        self.failed = 0          # сколько раз не удалось соединиться с сервером
        self.mode = ""           # как включён keepalive (для журнала)
        self._lock = threading.Lock()
        threading.Thread(target=self._accept, daemon=True, name="keepalive-relay").start()

    # -- настройки сокета к серверу
    def _keepalive(self, s):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):                       # Windows: (вкл, тишина мс, интервал проб мс)
            s.ioctl(socket.SIO_KEEPALIVE_VALS, (1, self.idle * 1000, self.interval * 1000))
            self.mode = "SIO_KEEPALIVE_VALS %d/%d с" % (self.idle, self.interval)
        else:                                                           # Linux / macOS
            done = []
            for name, val in (("TCP_KEEPIDLE", self.idle), ("TCP_KEEPALIVE", self.idle),
                              ("TCP_KEEPINTVL", self.interval), ("TCP_KEEPCNT", 10)):
                if hasattr(socket, name):
                    try:
                        s.setsockopt(socket.IPPROTO_TCP, getattr(socket, name), val)
                        done.append(name)
                    except OSError:
                        pass
            self.mode = "SO_KEEPALIVE " + ",".join(done)

    def _accept(self):
        while True:
            try:
                c, _ = self.srv.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(c,), daemon=True).start()

    @staticmethod
    def _pump(a, b):
        try:
            while True:
                d = a.recv(65536)
                if not d:
                    break
                b.sendall(d)
        except OSError:
            pass
        finally:
            try:
                b.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def _serve(self, c):
        try:
            u = socket.create_connection(self.target, timeout=30)
        except OSError:
            with self._lock:
                self.failed += 1
            c.close()
            return
        counted = False
        try:
            u.settimeout(None)
            self._keepalive(u)
            for s in (c, u):
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._lock:
                self.opened += 1
                self.active += 1
                counted = True
            t = threading.Thread(target=self._pump, args=(u, c), daemon=True)
            t.start()
            self._pump(c, u)
            t.join()
        finally:
            if counted:
                with self._lock:
                    self.active -= 1
            for s in (c, u):
                try:
                    s.close()
                except OSError:
                    pass

    def close(self):
        try:
            self.srv.close()
        except OSError:
            pass


def parse_dsn(dsn):
    """(host, port, функция, строящая строку соединения через локальный порт) или None, если адрес разобрать нельзя."""
    dsn = (dsn or "").strip()
    m = re.match(r"^//([^:/\s]+)(?::(\d+))?/(\S+)$", dsn)                # //host:port/service
    if m:
        host, port, svc = m.group(1), int(m.group(2) or 1521), m.group(3)
        return host, port, lambda p: "//127.0.0.1:%d/%s" % (p, svc)
    if dsn.startswith("("):                                             # полный описатель с одним адресом
        hosts = re.findall(r"\(\s*HOST\s*=\s*([^)\s]+)\s*\)", dsn, re.I)
        ports = re.findall(r"\(\s*PORT\s*=\s*(\d+)\s*\)", dsn, re.I)
        if len(hosts) == 1 and len(ports) == 1:
            def via(p):
                s = re.sub(r"\(\s*HOST\s*=\s*[^)\s]+\s*\)", "(HOST=127.0.0.1)", dsn, flags=re.I)
                return re.sub(r"\(\s*PORT\s*=\s*\d+\s*\)", "(PORT=%d)" % p, s, flags=re.I)
            return hosts[0], int(ports[0]), via
    return None


_relays = {}


def dsn_via_relay(dsn, idle=60):
    """Вернуть (строка соединения через ретранслятор, ретранслятор) или (исходная строка, None)."""
    if int(idle or 0) <= 0:
        return dsn, None
    parsed = parse_dsn(dsn)
    if not parsed:
        return dsn, None
    host, port, via = parsed
    if host in ("127.0.0.1", "localhost", "::1"):
        return dsn, None
    key = (host, port, int(idle))
    try:
        if key not in _relays:
            _relays[key] = Relay(host, port, idle=int(idle), interval=max(5, int(idle) // 2))
    except OSError:
        return dsn, None
    return via(_relays[key].port), _relays[key]
