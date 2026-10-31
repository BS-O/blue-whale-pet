"""单实例（SPEC §3）：Windows 命名 Mutex / Linux 锁文件；二启唤醒已有实例。

唤醒通道：首个实例在 127.0.0.1 随机端口监听，端口写入数据目录 ``instance.json``；
第二个实例读到端口后发送 ``show``，已有实例弹出桌宠。失败静默退出（不崩溃）。
"""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable

import constants as C

logger = logging.getLogger("bluewhale.single_instance")

MUTEX_NAME = f"Local\\{C.APP_ID}_single_instance_v1"
ERROR_ALREADY_EXISTS = 183


class _WakeServer(threading.Thread):
    def __init__(self, data_dir: Path, on_wake: Callable[[], None], logger_: logging.Logger) -> None:
        super().__init__(name="BlueWhaleWakeServer", daemon=True)
        self.data_dir = Path(data_dir)
        self.on_wake = on_wake
        self.log = logger_
        self.port_file = self.data_dir / "instance.json"
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self.port: int | None = None

    def start_server(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", 0))
            sock.listen(4)
            sock.settimeout(0.5)
        except OSError as exc:
            self.log.warning("唤醒监听启动失败: %s", exc)
            return False
        self._sock = sock
        self.port = int(sock.getsockname()[1])
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            payload = {"port": self.port, "pid": os.getpid()}
            tmp = self.port_file.with_name(f".instance.json.tmp-{os.getpid()}")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            os.replace(tmp, self.port_file)
        except OSError as exc:
            self.log.warning("写入唤醒端口文件失败: %s", exc)
        self.start()
        return True

    def run(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.settimeout(1.0)
                data = conn.recv(64)
                if b"show" in data:
                    try:
                        self.on_wake()
                    except Exception:  # noqa: BLE001
                        self.log.exception("唤醒回调异常")
                try:
                    conn.sendall(b"ok\n")
                except OSError:
                    pass
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def stop_server(self) -> None:
        self._stop.set()
        try:
            if self._sock is not None:
                self._sock.close()
        except OSError:
            pass
        try:
            if self.port_file.exists():
                self.port_file.unlink()
        except OSError:
            pass
        if self.is_alive() and threading.current_thread() is not self:
            self.join(timeout=1.0)


def _wake_existing(data_dir: Path) -> bool:
    """尝试唤醒已运行实例；返回是否成功。"""
    port_file = Path(data_dir) / "instance.json"
    for _ in range(4):
        try:
            info = json.loads(port_file.read_text(encoding="utf-8"))
            port = int(info.get("port"))
            pid = int(info.get("pid") or 0)
            if pid and pid == os.getpid():
                return False
            with socket.create_connection(("127.0.0.1", port), timeout=0.6) as sock:
                sock.sendall(b"show\n")
                sock.settimeout(1.0)
                try:
                    sock.recv(16)
                except OSError:
                    pass
                return True
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            threading.Event().wait(0.15)
    return False


class SingleInstance:
    def __init__(self, data_dir: Path, logger_: logging.Logger | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.log = logger_ or logger
        self._mutex_handle = None
        self._lock_file = None
        self._server: _WakeServer | None = None
        self.acquired = False

    # ------------------------------------------------------------------
    def acquire(self) -> bool:
        """尝试成为唯一实例；已有实例时尝试唤醒并返回 False。"""
        if sys.platform == "win32":
            return self._acquire_windows()
        return self._acquire_posix()

    def _acquire_windows(self) -> bool:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
            handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
            last_error = int(kernel32.GetLastError())
            if not handle:
                self.log.warning("CreateMutex 失败，跳过单实例检查")
                self.acquired = True
                return True
            if last_error == ERROR_ALREADY_EXISTS:
                kernel32.CloseHandle(ctypes.c_void_p(handle))
                woke = _wake_existing(self.data_dir)
                self.log.info("已有实例在运行，唤醒%s，本实例退出", "成功" if woke else "失败")
                return False
            self._mutex_handle = ctypes.c_void_p(handle)
            self.acquired = True
            return True
        except Exception:  # noqa: BLE001
            self.log.exception("Windows 单实例检查异常，按首实例继续")
            self.acquired = True
            return True

    def _lock_dir(self) -> Path:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if runtime and Path(runtime).is_dir():
            return Path(runtime)
        return Path(tempfile.gettempdir())

    def _acquire_posix(self) -> bool:
        try:
            import fcntl

            lock_dir = self._lock_dir()
            try:
                lock_path = lock_dir / f"{C.APP_PACKAGE}.lock"
                self._lock_file = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115
            except OSError:
                lock_path = self.data_dir / "instance.lock"
                self.data_dir.mkdir(parents=True, exist_ok=True)
                self._lock_file = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115
            try:
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                woke = _wake_existing(self.data_dir)
                self.log.info("已有实例在运行，唤醒%s，本实例退出", "成功" if woke else "失败")
                try:
                    self._lock_file.close()
                except OSError:
                    pass
                self._lock_file = None
                return False
            try:
                self._lock_file.seek(0)
                self._lock_file.truncate()
                self._lock_file.write(str(os.getpid()))
                self._lock_file.flush()
            except OSError:
                pass
            self.acquired = True
            return True
        except Exception:  # noqa: BLE001
            self.log.exception("Linux 单实例检查异常，按首实例继续")
            self.acquired = True
            return True

    # ------------------------------------------------------------------
    def start_wake_server(self, on_wake: Callable[[], None]) -> bool:
        """启动二启唤醒监听（须在 acquire 成功后调用）。"""
        if not self.acquired:
            return False
        try:
            self._server = _WakeServer(self.data_dir, on_wake, self.log)
            return self._server.start_server()
        except Exception:  # noqa: BLE001
            self.log.exception("启动唤醒监听异常")
            self._server = None
            return False

    def release(self) -> None:
        """释放锁与监听（退出时调用）。"""
        if self._server is not None:
            try:
                self._server.stop_server()
            except Exception:  # noqa: BLE001
                pass
            self._server = None
        if sys.platform == "win32":
            try:
                import ctypes

                if self._mutex_handle:
                    ctypes.windll.kernel32.CloseHandle(self._mutex_handle)
            except Exception:  # noqa: BLE001
                pass
            self._mutex_handle = None
        else:
            if self._lock_file is not None:
                try:
                    import fcntl

                    fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self._lock_file.close()
                except OSError:
                    pass
                self._lock_file = None
        self.acquired = False
