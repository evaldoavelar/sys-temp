#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_daemon.py: Daemon de monitoramento térmico, alerta via Telegram e watchdog de processos.
Integrado ao projeto sys-temp.
"""

import sys
import os
import time
import signal
import json
import logging
import threading
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    print("Erro: psutil não encontrado. Instale com: pip install psutil")
    sys.exit(1)

CONFIG_PATH = Path.home() / ".config" / "sys-temp" / "alert.env"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_NAME = "sys-temp-alert.service"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("sys-temp-alert")


def load_config() -> dict:
    """Carrega as configurações de ~/.config/sys-temp/alert.env com valores padrão."""
    config = {
        "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "ENABLE_TELEGRAM_POLLING": os.getenv("ENABLE_TELEGRAM_POLLING", "true").lower() in ("true", "1", "yes"),
        "TEMP_THRESHOLD": float(os.getenv("TEMP_THRESHOLD", "85.0")),
        "ALERT_DELAY_SECONDS": int(os.getenv("ALERT_DELAY_SECONDS", "120")),
        "KILL_DELAY_SECONDS": int(os.getenv("KILL_DELAY_SECONDS", "300")),
        "RECOVERY_THRESHOLD": float(os.getenv("RECOVERY_THRESHOLD", "75.0")),
        "PROTECTED_PROCESSES": [
            p.strip().lower() for p in os.getenv(
                "PROTECTED_PROCESSES",
                "systemd,init,sshd,gnome-shell,xorg,wayland,pipewire,pulseaudio,dbus-daemon,hermes,bash,zsh,fish,tmux,screen,dockerd,containerd,sys-temp"
            ).split(",") if p.strip()
        ]
    }

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'").split("#")[0].strip()
                        if k == "TELEGRAM_BOT_TOKEN":
                            config[k] = v
                        elif k == "TELEGRAM_CHAT_ID":
                            config[k] = v
                        elif k == "ENABLE_TELEGRAM_POLLING":
                            config[k] = v.lower() in ("true", "1", "yes")
                        elif k == "TEMP_THRESHOLD":
                            config[k] = float(v)
                        elif k == "ALERT_DELAY_SECONDS":
                            config[k] = int(v)
                        elif k == "KILL_DELAY_SECONDS":
                            config[k] = int(v)
                        elif k == "RECOVERY_THRESHOLD":
                            config[k] = float(v)
                        elif k == "PROTECTED_PROCESSES":
                            config[k] = [p.strip().lower() for p in v.split(",") if p.strip()]
        except Exception as e:
            logger.warning(f"Erro ao ler arquivo de configuração {CONFIG_PATH}: {e}")

    return config


class TelegramBot:
    def __init__(self, token: str, default_chat_id: str):
        self.token = token
        self.default_chat_id = default_chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_message(self, text: str, chat_id: str = None, parse_mode: str = "HTML") -> bool:
        cid = chat_id or self.default_chat_id
        if not self.token or not cid:
            logger.warning("Telegram Bot Token ou Chat ID não configurados em ~/.config/sys-temp/alert.env")
            return False

        payload = {
            "chat_id": cid,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(f"{self.base_url}/sendMessage", data=data)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("ok", False)
        except Exception as e:
            logger.error(f"Falha ao enviar mensagem Telegram: {e}")
            return False

    def register_commands(self) -> bool:
        """Registra os comandos oficiais no menu do Telegram via setMyCommands."""
        if not self.token:
            return False

        commands = [
            {"command": "status", "description": "Telemetria atual (temperatura, fan, processos)"},
            {"command": "matar_agora", "description": "Encerra imediatamente o processo ofensor"},
            {"command": "cancelar_kill", "description": "Aborta a finalização preventiva"},
            {"command": "ajuda", "description": "Exibe ajuda e comandos disponíveis"}
        ]
        url = f"{self.base_url}/setMyCommands"
        data = json.dumps({"commands": commands}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("ok"):
                    logger.info("Comandos oficiais do Telegram registrados com sucesso via setMyCommands.")
                    return True
                return False
        except Exception as e:
            logger.warning(f"Não foi possível registrar comandos no Telegram: {e}")
            return False

    def get_updates(self, offset: int = None, timeout: int = 20) -> list:
        if not self.token:
            return []

        params = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset

        url = f"{self.base_url}/getUpdates?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url)

        try:
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("result", [])
        except urllib.error.HTTPError as e:
            if e.code == 409:
                logger.warning("Telegram 409 Conflict: outra instância ou bot está usando getUpdates com este mesmo token.")
            else:
                logger.warning(f"Erro HTTP Telegram getUpdates: {e}")
            return []
        except Exception as e:
            logger.debug(f"Erro de conexão getUpdates Telegram: {e}")
            return []


def read_system_temperature() -> float:
    """Lê a temperatura atual da CPU em °C."""
    try:
        raw_temps = psutil.sensors_temperatures()
        if 'coretemp' in raw_temps:
            for s in raw_temps['coretemp']:
                if s.label and 'Package' in s.label:
                    return s.current
            if raw_temps['coretemp']:
                return raw_temps['coretemp'][0].current
        if 'dell_smm' in raw_temps:
            for s in raw_temps['dell_smm']:
                if s.label and 'CPU' in s.label:
                    return s.current
    except Exception:
        pass

    try:
        import glob
        for tz_type in glob.glob("/sys/class/thermal/thermal_zone*/type"):
            with open(tz_type) as f:
                if "x86_pkg_temp" in f.read():
                    t_file = tz_type.replace("/type", "/temp")
                    with open(t_file) as tf:
                        return int(tf.read().strip()) / 1000.0
    except Exception:
        pass

    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 50.0


def read_system_fan_rpm() -> int:
    """Lê rotação da ventoinha em RPM."""
    try:
        raw_fans = psutil.sensors_fans()
        if 'dell_smm' in raw_fans and raw_fans['dell_smm']:
            return raw_fans['dell_smm'][0].current
    except Exception:
        pass
    return 0


def get_root_offender(pid: int, protected_list: list) -> int:
    """Retorna o PID do processo raiz não-protegido pertencente ao usuário que gerou o PID atual (ex: script pai que disparou workers)."""
    try:
        proc = psutil.Process(pid)
    except Exception:
        return pid

    curr = proc
    current_uid = os.getuid()
    while True:
        try:
            parent = curr.parent()
            if not parent or parent.pid <= 1:
                break
            if parent.uids().real != current_uid:
                break
            p_name = (parent.name() or '').lower()
            p_cmd = " ".join(parent.cmdline() or []).lower()
            if any(prot in p_name or prot in p_cmd for prot in protected_list):
                break
            curr = parent
        except Exception:
            break
    return curr.pid


def find_top_offender_process(protected_list: list) -> dict | None:
    """Localiza o processo que mais consome CPU pertencente ao usuário atual e não protegido."""
    current_uid = os.getuid()
    candidates = []

    # Faz primeira leitura para calibrar cpu_percent
    for p in psutil.process_iter(['pid', 'name', 'uids', 'cpu_percent']):
        try:
            p.cpu_percent()
        except Exception:
            pass

    time.sleep(0.15)

    for p in psutil.process_iter(['pid', 'name', 'uids', 'cpu_percent', 'memory_percent', 'cmdline']):
        try:
            info = p.info
            # Apenas processos pertencentes ao usuário corrente
            if not info['uids'] or info['uids'].real != current_uid:
                continue

            name = (info['name'] or '').lower()
            cmd_str = " ".join(info['cmdline'] or []).lower()
            if any(prot in name or prot in cmd_str for prot in protected_list):
                continue

            cpu_p = info['cpu_percent'] or 0.0
            if cpu_p > 10.0:  # Consumo relevante de CPU
                candidates.append({
                    'pid': info['pid'],
                    'name': info['name'],
                    'cpu_percent': cpu_p,
                    'memory_percent': info['memory_percent'] or 0.0,
                    'cmdline': " ".join(info['cmdline'] or [])[:80]
                })
        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort(key=lambda x: x['cpu_percent'], reverse=True)
    top = candidates[0]

    # Identifica o processo raiz não-protegido da árvore
    root_pid = get_root_offender(top['pid'], protected_list)
    if root_pid != top['pid']:
        try:
            r_proc = psutil.Process(root_pid)
            total_cpu = top['cpu_percent']
            for child in r_proc.children(recursive=True):
                try:
                    if child.pid != top['pid']:
                        c_p = child.cpu_percent()
                        if c_p:
                            total_cpu += c_p
                except Exception:
                    pass
            return {
                'pid': root_pid,
                'name': r_proc.name(),
                'cpu_percent': total_cpu,
                'memory_percent': r_proc.memory_percent() or top['memory_percent'],
                'cmdline': " ".join(r_proc.cmdline() or [])[:80]
            }
        except Exception:
            pass

    return top


def terminate_offender(pid: int, name: str, timeout: int = 10) -> bool:
    """Encerra processo ofensor e toda a sua árvore de subprocessos com SIGTERM e escala para SIGKILL se necessário."""
    pids_to_kill = [pid]
    try:
        proc = psutil.Process(pid)
        for child in proc.children(recursive=True):
            pids_to_kill.append(child.pid)
    except Exception:
        pass

    # Garante lista única preservando ordem (filhos primeiro, depois o pai)
    pids_to_kill = list(dict.fromkeys(reversed(pids_to_kill)))
    logger.warning(f"Enviando SIGTERM para a árvore do processo {name} (PIDs: {pids_to_kill})...")

    for p in pids_to_kill:
        try:
            os.kill(p, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as e:
            logger.error(f"Erro ao enviar SIGTERM para PID {p}: {e}")

    # Aguarda encerramento gracioso por até timeout segundos
    deadline = time.time() + timeout
    while time.time() < deadline:
        alive_pids = []
        for p in pids_to_kill:
            try:
                os.kill(p, 0)
                alive_pids.append(p)
            except ProcessLookupError:
                pass
            except Exception:
                pass
        if not alive_pids:
            logger.info(f"Processo {name} e todos os subprocessos ({pids_to_kill}) encerraram graciosamente com SIGTERM.")
            return True
        time.sleep(0.5)

    # Se ainda houver processos vivos, força SIGKILL
    remaining = []
    for p in pids_to_kill:
        try:
            os.kill(p, 0)
            remaining.append(p)
        except ProcessLookupError:
            pass
        except Exception:
            pass

    if remaining:
        logger.warning(f"Processos {remaining} não encerraram no prazo. Enviando SIGKILL forçado...")
        for p in remaining:
            try:
                os.kill(p, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.error(f"Erro ao enviar SIGKILL para PID {p}: {e}")
        time.sleep(0.5)

    return True


class ThermalAlertDaemon:
    def __init__(self):
        self.config = load_config()
        self.bot = TelegramBot(self.config["TELEGRAM_BOT_TOKEN"], self.config["TELEGRAM_CHAT_ID"])
        self.running = True

        # Estados térmicos e cronômetros
        self.high_temp_start = None
        self.alert_sent = False
        self.kill_countdown_start = None
        self.pending_kill = None       # dict: {'pid': int, 'name': str, 'cpu': float}
        self.kill_cancelled = False
        self.last_alert_time = 0

    def get_status_report(self) -> str:
        """Gera relatório de telemetria formatado em HTML para o Telegram."""
        temp = read_system_temperature()
        fan_rpm = read_system_fan_rpm()
        vmem = psutil.virtual_memory()
        load1, load5, load15 = os.getloadavg()

        status_emoji = "🟢" if temp < 70 else ("🟡" if temp < 85 else "🔴")
        lines = [
            f"💻 <b>Status do Sistema (cst-tux)</b> {status_emoji}",
            f"━━━━━━━━━━━━━━━━━━━",
            f"🌡️ <b>CPU Temp:</b> <code>{temp:.1f}°C</code> (Limiar: {self.config['TEMP_THRESHOLD']:.0f}°C)",
            f"🌀 <b>Cooler Fan:</b> <code>{fan_rpm} RPM</code>",
            f"🧠 <b>Memória RAM:</b> <code>{vmem.used/(1024**3):.1f}/{vmem.total/(1024**3):.1f} GiB ({vmem.percent:.0f}%)</code>",
            f"⚖️ <b>Carga Média:</b> <code>{load1:.2f}, {load5:.2f}, {load15:.2f}</code>",
        ]

        if self.pending_kill and not self.kill_cancelled:
            rem = max(0, int(self.config["KILL_DELAY_SECONDS"] - (time.time() - (self.kill_countdown_start or time.time()))))
            lines.append(f"\n⚠️ <b>AÇÃO PROGRAMADA ATIVA:</b>")
            lines.append(f"Alvo: <code>{self.pending_kill['name']}</code> (PID: {self.pending_kill['pid']})")
            lines.append(f"Tempo restante: <b>{rem}s</b> para encerramento.")

        # Top 3 processos
        lines.append("\n📊 <b>Top 3 Processos CPU:</b>")
        try:
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    procs.append(p.info)
                except Exception:
                    pass
            procs.sort(key=lambda x: (x.get('cpu_percent') or 0), reverse=True)
            for p in procs[:3]:
                name = (p.get('name') or '')[:14]
                cpu = p.get('cpu_percent') or 0.0
                mem = p.get('memory_percent') or 0.0
                lines.append(f"• <code>{name:<14}</code> (PID {p.get('pid'):>5}): <b>{cpu:>4.1f}%</b> CPU | {mem:>4.1f}% MEM")
        except Exception:
            lines.append("• <i>Não foi possível listar processos</i>")

        return "\n".join(lines)

    def handle_command(self, cmd: str, from_id: int) -> str:
        """Processa comandos recebidos do Telegram."""
        auth_id = str(from_id)
        configured_id = str(self.config["TELEGRAM_CHAT_ID"]).strip()

        if auth_id != configured_id:
            logger.warning(f"Tentativa de comando de usuário não autorizado: {from_id}")
            return "⛔ <b>Acesso Negado:</b> Você não está autorizado a interagir com este watchdog."

        raw_cmd = cmd.strip()
        clean_cmd = raw_cmd.split()[0].split("@")[0].lower()
        if not clean_cmd.startswith("/"):
            clean_cmd = "/" + clean_cmd

        if clean_cmd in ("/status", "/stats"):
            return self.get_status_report()

        elif clean_cmd in ("/cancelar_kill", "/cancelar", "/abort"):
            if self.pending_kill and not self.kill_cancelled:
                self.kill_cancelled = True
                pid = self.pending_kill['pid']
                name = self.pending_kill['name']
                logger.info(f"Encerramento automático cancelado via Telegram para PID {pid} ({name})")
                return f"🛡️ <b>Ação Cancelada!</b>\nO encerramento automático do processo <code>{name}</code> (PID {pid}) foi abortado a seu pedido."
            else:
                return "ℹ️ Não há nenhuma finalização de processo agendada no momento."

        elif clean_cmd in ("/matar_agora", "/kill", "/encerrar"):
            if self.pending_kill:
                pid = self.pending_kill['pid']
                name = self.pending_kill['name']
                success = terminate_offender(pid, name)
                self.pending_kill = None
                self.kill_cancelled = True
                if success:
                    return f"🛑 <b>Processo Finalizado com Sucesso:</b>\n<code>{name}</code> (PID {pid}) e sua árvore foram encerrados imediatamente."
                else:
                    return f"⚠️ Falha ao encerrar <code>{name}</code> (PID {pid}). Verifique os logs."
            else:
                offender = find_top_offender_process(self.config["PROTECTED_PROCESSES"])
                if offender:
                    success = terminate_offender(offender['pid'], offender['name'])
                    if success:
                        return f"🛑 <b>Top Processo Finalizado:</b>\n<code>{offender['name']}</code> (PID {offender['pid']}, {offender['cpu_percent']:.1f}% CPU) e subprocessos foram encerrados."
                    else:
                        return f"⚠️ Falha ao tentar encerrar PID {offender['pid']}."
                else:
                    return "ℹ️ Nenhum processo ofensor de usuário consumindo CPU acima do normal."

        elif clean_cmd in ("/ajuda", "/help", "/start"):
            return (
                "🤖 <b>Comandos do Watchdog sys-temp:</b>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                "• /status - Consulta telemetria de temperatura, fan e processos\n"
                "• /matar_agora - Encerra imediatamente o processo que estiver aquecendo a CPU\n"
                "• /cancelar_kill - Cancela a contagem regressiva de encerramento\n"
                "• /ajuda - Exibe este guia de comandos\n\n"
                f"⚙️ <i>Limiar térmico atual: {self.config['TEMP_THRESHOLD']:.0f}°C por {self.config['ALERT_DELAY_SECONDS']}s</i>"
            )

        return (
            "❓ <b>Comando não reconhecido.</b>\n\n"
            "Use o menu [ / ] ou envie um dos comandos:\n"
            "• /status - Ver temperatura e processos\n"
            "• /matar_agora - Finalizar processo ofensor\n"
            "• /cancelar_kill - Abortar finalização programada\n"
            "• /ajuda - Guia completo"
        )

    def polling_loop(self):
        """Thread secundária que realiza long polling no Telegram para receber comandos."""
        if not self.config["ENABLE_TELEGRAM_POLLING"]:
            logger.info("Telegram Polling desativado nas configurações (ENABLE_TELEGRAM_POLLING=false).")
            return

        # Registra comandos no menu oficial do Telegram
        self.bot.register_commands()

        last_update_id = None
        logger.info("Iniciando escuta de comandos interativos no Telegram...")

        while self.running:
            try:
                updates = self.bot.get_updates(offset=last_update_id, timeout=15)
                for up in updates:
                    last_update_id = up["update_id"] + 1
                    msg = up.get("message") or up.get("channel_post")
                    if not msg or "text" not in msg:
                        continue

                    text = msg.get("text", "").strip()
                    from_user = msg.get("from") or {}
                    from_id = from_user.get("id") or msg.get("chat", {}).get("id")

                    if not text:
                        continue

                    if text.startswith("/"):
                        logger.info(f"Comando recebido de {from_id}: {text}")
                        reply = self.handle_command(text, from_id)
                        self.bot.send_message(reply, chat_id=str(from_id))
                    else:
                        logger.info(f"Mensagem de texto livre recebida de {from_id}: {text}")
                        reply = (
                            "👋 Olá! Sou o <b>sys-temp Watchdog</b>.\n\n"
                            "Você pode usar o menu <b>[ / ]</b> do Telegram ou enviar:\n"
                            "• /status - Telemetria atual da máquina\n"
                            "• /matar_agora - Encerrar processo que estiver aquecendo a CPU\n"
                            "• /cancelar_kill - Cancelar encerramento programado\n"
                            "• /ajuda - Guia de comandos"
                        )
                        self.bot.send_message(reply, chat_id=str(from_id))

            except Exception as e:
                logger.error(f"Erro no loop de polling do Telegram: {e}")
                time.sleep(5)

    def watchdog_step(self):
        """Passo do ciclo principal do watchdog executado a cada 5 segundos."""
        temp = read_system_temperature()
        threshold = self.config["TEMP_THRESHOLD"]
        alert_delay = self.config["ALERT_DELAY_SECONDS"]
        kill_delay = self.config["KILL_DELAY_SECONDS"]
        recovery_thresh = self.config["RECOVERY_THRESHOLD"]

        # 1. Avaliação de Temperatura Alta
        if temp >= threshold:
            if self.high_temp_start is None:
                self.high_temp_start = time.time()
                logger.info(f"Temperatura subiu para {temp:.1f}°C (>= {threshold:.0f}°C). Iniciando contagem de sustentação...")

            duration = time.time() - self.high_temp_start

            # Disparo do Alerta Inicial apósALERT_DELAY_SECONDS
            if duration >= alert_delay and not self.alert_sent:
                offender = find_top_offender_process(self.config["PROTECTED_PROCESSES"])
                fan_rpm = read_system_fan_rpm()

                self.alert_sent = True
                self.kill_countdown_start = time.time()
                self.kill_cancelled = False
                self.last_alert_time = time.time()

                offender_info = ""
                if offender:
                    self.pending_kill = offender
                    offender_info = (
                        f"🎯 <b>Processo Ofensor Detectado:</b>\n"
                        f"• Nome: <code>{offender['name']}</code> (PID: <code>{offender['pid']}</code>)\n"
                        f"• Consumo CPU: <b>{offender['cpu_percent']:.1f}%</b> | RAM: {offender['memory_percent']:.1f}%\n"
                    )
                else:
                    self.pending_kill = None
                    offender_info = "• <i>Nenhum processo individual de usuário ultrapassou 10% de CPU.</i>\n"

                alert_msg = (
                    f"🔥 <b>ALERTA DE TEMPERATURA CRÍTICA</b> 🔥\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"<b>Host:</b> Dell Inspiron (cst-tux)\n"
                    f"🌡️ <b>Temperatura Atual:</b> <code>{temp:.1f}°C</code> (sustentada por {int(duration)}s)\n"
                    f"🌀 <b>Cooler Fan:</b> <code>{fan_rpm} RPM</code>\n\n"
                    f"{offender_info}\n"
                    f"⚠️ <b>Ação de Proteção Programada:</b>\n"
                    f"Se a temperatura permanecer crítica por mais <b>{int(kill_delay/60)} minutos</b>, o processo ofensor será <b>automaticamente finalizado</b> para proteger o hardware.\n\n"
                    f"<i>Para cancelar ou agir agora, responda:</i>\n"
                    f"/cancelar_kill - Aborta a finalização\n"
                    f"/matar_agora - Encerra imediatamente\n"
                    f"/status - Consulta telemetria atual"
                )

                logger.warning(f"Disparando Alerta no Telegram! Temp: {temp:.1f}°C, Duração: {int(duration)}s")
                self.bot.send_message(alert_msg)

            # Execução da ação de Kill após KILL_DELAY_SECONDS se o calor persistir
            if self.alert_sent and self.pending_kill and not self.kill_cancelled:
                kill_elapsed = time.time() - self.kill_countdown_start
                if kill_elapsed >= kill_delay:
                    pid = self.pending_kill['pid']
                    name = self.pending_kill['name']
                    logger.warning(f"Prazo de {kill_delay}s esgotado. Finalizando processo {name} (PID: {pid}) preventivamente...")

                    success = terminate_offender(pid, name)
                    if success:
                        msg = (
                            f"🛑 <b>PROCESSO FINALIZADO PELO WATCHDOG</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"O processo <code>{name}</code> (PID: <code>{pid}</code>) foi finalizado preventivamente após {int(kill_delay/60)} minutos de temperatura crítica inalterada ({temp:.1f}°C).\n"
                            f"O notebook está agora sob resfriamento."
                        )
                    else:
                        msg = f"⚠️ Falha ao finalizar o processo <code>{name}</code> (PID: {pid}). Verifique manualmente."

                    self.bot.send_message(msg)
                    self.pending_kill = None
                    self.last_kill_time = time.time()

            # Se o ofensor foi finalizado mas a temperatura continua crítica após 30s adicionais
            elif self.alert_sent and self.pending_kill is None and not self.kill_cancelled:
                if hasattr(self, 'last_kill_time') and (time.time() - self.last_kill_time) >= 30:
                    new_offender = find_top_offender_process(self.config["PROTECTED_PROCESSES"])
                    if new_offender:
                        logger.warning(f"Temperatura ainda crítica ({temp:.1f}°C). Novo ofensor identificado: {new_offender['name']} (PID: {new_offender['pid']})")
                        self.pending_kill = new_offender
                        self.kill_countdown_start = time.time()
                        re_msg = (
                            f"⚠️ <b>TEMPERATURA AINDA CRÍTICA ({temp:.1f}°C)</b>\n"
                            f"Novo processo ofensor detectado: <code>{new_offender['name']}</code> (PID: <code>{new_offender['pid']}</code>, CPU: {new_offender['cpu_percent']:.1f}%).\n"
                            f"Finalização automática programada caso persista."
                        )
                        self.bot.send_message(re_msg)

        else:
            # Temperatura abaixo do threshold
            if self.high_temp_start is not None:
                logger.info(f"Temperatura retornou para {temp:.1f}°C (< {threshold:.0f}°C). Resetando contagem.")
                self.high_temp_start = None

            # Envia aviso de normalização se havíamos alertado antes
            if self.alert_sent and temp <= recovery_thresh:
                logger.info(f"Temperatura normalizada com sucesso ({temp:.1f}°C <= {recovery_thresh:.0f}°C). Enviando aviso...")
                norm_msg = (
                    f"✅ <b>TEMPERATURA NORMALIZADA</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━\n"
                    f"O sistema resfriou com sucesso. Temperatura atual: <b>{temp:.1f}°C</b>.\n"
                    f"Todas as ações preventivas foram resetadas para operação normal."
                )
                self.bot.send_message(norm_msg)
                self.alert_sent = False
                self.pending_kill = None
                self.kill_cancelled = False

    def run(self):
        """Inicia os loops de watchdog e polling."""
        logger.info(f"Iniciando Watchdog Térmico sys-temp (Limiar: {self.config['TEMP_THRESHOLD']}°C, Alerta: {self.config['ALERT_DELAY_SECONDS']}s, Kill: {self.config['KILL_DELAY_SECONDS']}s)")

        # Inicia thread de escuta do Telegram
        polling_thread = threading.Thread(target=self.polling_loop, daemon=True)
        polling_thread.start()

        def sig_handler(sig, frame):
            logger.info("Recebido sinal de encerramento. Finalizando daemon...")
            self.running = False

        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)

        while self.running:
            try:
                self.watchdog_step()
            except Exception as e:
                logger.error(f"Erro no ciclo do watchdog: {e}")
            time.sleep(5)


# --- UTILITÁRIOS SYSTEMD & CLI ---

def get_service_content() -> str:
    exec_path = Path.home() / ".local" / "bin" / "sys-temp"
    return f"""[Unit]
Description=Sys-Temp Thermal Alert & Watchdog Daemon
After=network.target

[Service]
Type=simple
ExecStart={exec_path} daemon run
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def install_service():
    """Instala e ativa a unidade systemd de usuário."""
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    service_file = SYSTEMD_USER_DIR / SERVICE_NAME

    with open(service_file, "w", encoding="utf-8") as f:
        f.write(get_service_content())

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", SERVICE_NAME], check=True)
    print(f"✔ Serviço {SERVICE_NAME} instalado e iniciado com sucesso!")
    print("Verifique o status com: sys-temp daemon status")


def uninstall_service():
    """Desativa e remove a unidade systemd de usuário."""
    service_file = SYSTEMD_USER_DIR / SERVICE_NAME
    subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], check=False)
    subprocess.run(["systemctl", "--user", "disable", SERVICE_NAME], check=False)
    if service_file.exists():
        service_file.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    print(f"✔ Serviço {SERVICE_NAME} removido com sucesso.")


def test_telegram():
    """Testa o envio de uma mensagem de teste para o Telegram."""
    cfg = load_config()
    token = cfg["TELEGRAM_BOT_TOKEN"]
    chat_id = cfg["TELEGRAM_CHAT_ID"]

    if not token or not chat_id:
        print("❌ Erro: TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não definidos em ~/.config/sys-temp/alert.env")
        print("Edite o arquivo e configure seu bot.")
        return False

    bot = TelegramBot(token, chat_id)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    msg = (
        f"🤖 <b>Teste de Conexão: sys-temp Watchdog</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"✔ Conexão com o Telegram validada com sucesso!\n"
        f"Data e hora: <code>{now_str}</code>\n"
        f"Host: <b>Dell Inspiron (cst-tux)</b>\n\n"
        f"<i>O daemon está pronto para monitorar a saúde do seu hardware.</i>"
    )

    print(f"Enviando mensagem de teste para chat_id {chat_id}...")
    success = bot.send_message(msg)
    if success:
        print("✔ Mensagem de teste enviada com sucesso ao Telegram!")
    else:
        print("❌ Falha ao enviar mensagem de teste. Verifique o token e o chat_id.")
    return success


def handle_daemon_cli(args: list):
    """Ponto de entrada para comandos sys-temp daemon <subcomando>."""
    if not args or args[0] in ("help", "--help", "-h"):
        print("Uso: sys-temp daemon <comando>")
        print("\nComandos disponíveis:")
        print("  run            Executa o daemon em primeiro plano (foreground/logs)")
        print("  install        Instala e ativa o serviço systemd de usuário (sys-temp-alert.service)")
        print("  uninstall      Para e remove o serviço systemd de usuário")
        print("  start          Inicia o serviço systemd")
        print("  stop           Para o serviço systemd")
        print("  restart        Reinicia o serviço systemd")
        print("  status         Exibe o status do serviço systemd")
        print("  logs           Exibe os últimos logs do serviço no journalctl")
        print("  test-telegram  Envia uma mensagem de teste para validar a configuração")
        return

    cmd = args[0]
    if cmd == "run":
        daemon = ThermalAlertDaemon()
        daemon.run()
    elif cmd == "install":
        install_service()
    elif cmd == "uninstall":
        uninstall_service()
    elif cmd == "start":
        subprocess.run(["systemctl", "--user", "start", SERVICE_NAME])
    elif cmd == "stop":
        subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME])
    elif cmd == "restart":
        subprocess.run(["systemctl", "--user", "restart", SERVICE_NAME])
    elif cmd == "status":
        subprocess.run(["systemctl", "--user", "status", SERVICE_NAME])
    elif cmd == "logs":
        subprocess.run(["journalctl", "--user", "-u", SERVICE_NAME, "-n", "50", "--no-pager"])
    elif cmd == "test-telegram":
        test_telegram()
    else:
        print(f"Comando desconhecido: {cmd}. Execute 'sys-temp daemon help' para ver as opções.")


if __name__ == "__main__":
    handle_daemon_cli(sys.argv[1:])
