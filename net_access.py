"""Cross-platform, best-effort LAN firewall access for Brahma Echo's local servers.

Shared by dashboard/server.py (phone remote, port 8000) and
brahma_connect/gateway/server.py (device gateway, port 8765) so both
open the OS firewall the same way instead of each maintaining its own copy.
"""
from __future__ import annotations

import platform
import subprocess


def _quiet_run(*args, **kwargs):
    if platform.system() == "Windows":
        kwargs.setdefault("creationflags", getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(*args, **kwargs)


def ensure_network_access(port: int, *, label: str = "Brahma Dashboard") -> None:
    """Open `port` in the OS firewall for LAN access, tagged with `label`.

    Runs in a background thread — never blocks uvicorn startup.

    Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW
              (native UAC dialog, guaranteed to appear). One-time setup.
    macOS   : osascript admin dialog if the Application Firewall is on.
    Linux   : pkexec GUI -> sudo -n -> prints manual command as fallback.
    """
    import sys, os, tempfile, threading

    # ── Windows ──────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        import ctypes, time

        port_rule = f"{label} Port {port}"
        prog_rule = f"{label} Python"
        py_exe = sys.executable

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = _quiet_run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = _quiet_run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        need_port = not _netsh_rule_exists(port_rule)
        need_prog = not _netsh_rule_exists(prog_rule)
        need_private = _network_is_public()

        if not need_port and not need_prog and not need_private:
            return  # already fully configured

        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        if need_port:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rule}" protocol=TCP dir=in '
                f'localport={port} action=allow'
            )
        if need_prog:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{prog_rule}" dir=in action=allow '
                f'program="{py_exe}" enable=yes'
            )

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="brahma_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))
            os.close(fd)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            return

        try:
            r = _quiet_run([bat_path], capture_output=True, timeout=8, shell=True)
            if r.returncode == 0:
                print(f"[{label}] Firewall configured for port {port}.")
                try:
                    os.unlink(bat_path)
                except Exception:
                    pass
                return
        except Exception:
            pass

        print(f"[{label}] One-time network setup required.")
        print(f"[{label}] >>> A Windows security dialog will appear — click 'Yes' <<<")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", bat_path, None, None, 0,
            )
            if int(ret) > 32:
                time.sleep(2)
                print(f"[{label}] Network setup complete — port {port} is open.")
            else:
                print(f"[{label}] Setup was not allowed.")
                print(f"[{label}] LAN connections may fail until Brahma is run as Administrator.")
        except Exception as e:
            print(f"[{label}] Firewall setup error: {e}")
        finally:
            def _cleanup(path: str) -> None:
                time.sleep(5)
                try:
                    os.unlink(path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()
        return

    # ── macOS ─────────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        fw_ctl = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        try:
            r = _quiet_run([fw_ctl, "--getglobalstate"], capture_output=True, text=True, timeout=5)
            if "disabled" in r.stdout.lower():
                return

            py = sys.executable
            listed = _quiet_run([fw_ctl, "--listapps"], capture_output=True, text=True, timeout=5)
            if py in listed.stdout:
                return

            print(f"[{label}] One-time network setup — enter your password in the macOS dialog.")
            _quiet_run(
                ["osascript", "-e",
                 f'do shell script "{fw_ctl} --add {py} && {fw_ctl} --unblockapp {py}"'
                 f' with administrator privileges'],
                timeout=60,
            )
        except Exception:
            pass
        return

    # ── Linux ─────────────────────────────────────────────────────────────────
    def _privileged(cmd: list[str]) -> bool:
        for prefix in (["pkexec"], ["sudo", "-n"]):
            try:
                r = _quiet_run(prefix + cmd, capture_output=True, timeout=30)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    try:  # ufw
        r = _quiet_run(["ufw", "status"], capture_output=True, text=True, timeout=5)
        if "active" in r.stdout.lower():
            if _privileged(["ufw", "allow", f"{port}/tcp"]):
                print(f"[{label}] ufw: port {port} allowed.")
            else:
                print(f"[{label}] Run manually:  sudo ufw allow {port}/tcp")
            return
    except FileNotFoundError:
        pass

    try:  # firewalld
        r = _quiet_run(["firewall-cmd", "--state"], capture_output=True, text=True, timeout=5)
        if "running" in r.stdout.lower():
            ok = (_privileged(["firewall-cmd", "--add-port", f"{port}/tcp", "--permanent"])
                  and _privileged(["firewall-cmd", "--reload"]))
            if ok:
                print(f"[{label}] firewalld: port {port} allowed.")
            else:
                print(f"[{label}] Run manually:  sudo firewall-cmd --add-port={port}/tcp --permanent && sudo firewall-cmd --reload")
            return
    except FileNotFoundError:
        pass

    try:  # iptables (not persistent but works until reboot)
        r = _quiet_run(["iptables", "-L", "INPUT", "-n"], capture_output=True, timeout=5)
        if r.returncode == 0:
            if _privileged(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]):
                print(f"[{label}] iptables: port {port} opened.")
            else:
                print(f"[{label}] Run manually:  sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    except FileNotFoundError:
        pass  # no iptables means firewall is probably off — nothing to do
