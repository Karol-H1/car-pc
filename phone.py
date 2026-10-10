"""Calls through your Android phone, over the same USB debugging link as Google Maps.

Reads contacts and recent calls, places, answers and ends calls, and watches for incoming ones.
The call audio itself stays on the phone for now; Bluetooth hands-free (with the car's speakers and a
microphone) comes once those parts arrive. Contacts are only kept in memory, never saved on the Pi.
Nothing in here touches Kivy; callers hand results to the main thread themselves.
"""
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime

POLL_SECONDS = 1.0
# TelephonyManager call states, and which matters most when a phone with two SIMs reports both.
CALL_STATES = {"0": "idle", "1": "ringing", "2": "offhook"}
STATE_PRIORITY = ["idle", "offhook", "ringing"]
# Android call log TYPE values.
CALL_KINDS = {"1": "incoming", "2": "outgoing", "3": "missed", "5": "declined", "6": "blocked"}
RECENT_CALLS = 60

ROW = re.compile(r"^Row: \d+ (.*)$")


def adb_shell(*args, timeout=5):
    """Run a command on the phone. Returns its output, or None if the phone isn't reachable."""
    try:
        result = subprocess.run(["adb", "shell", *args], capture_output=True, text=True,
                                timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def match_key(number):
    """The last 10 digits, so "+1 (508) 555-0100" and "5085550100" count as the same number."""
    return re.sub(r"\D", "", number or "")[-10:]


@dataclass
class Contact:
    name: str
    number: str


@dataclass
class RecentCall:
    name: str      # contact name, or "" for numbers not in contacts
    number: str
    kind: str      # incoming, outgoing, missed, declined, blocked
    when: datetime


def query(uri, columns, sort=None):
    """Rows from one of the phone's content providers, as lists of column values (None for NULL)."""
    args = ["content", "query", "--uri", uri, "--projection", ":".join(columns)]
    if sort:
        args += ["--sort", f"'{sort}'"]
    output = adb_shell(*args, timeout=15)
    if output is None:
        return None
    pattern = re.compile(", ".join(f"{column}=(.*)" for column in columns) + "$")
    rows = []
    for line in output.splitlines():
        row = ROW.match(line.strip())
        fields = pattern.match(row.group(1)) if row else None
        if fields:
            rows.append([None if value == "NULL" else value for value in fields.groups()])
    return rows


def load_contacts():
    """Everyone in the phone's contacts who has a number, A to Z. None if the phone isn't reachable."""
    rows = query("content://com.android.contacts/data/phones", ["display_name", "data1"])
    if rows is None:
        return None
    seen, contacts = set(), []
    for name, number in rows:
        key = (name, match_key(number))
        if name and number and key not in seen:
            seen.add(key)
            contacts.append(Contact(name, number))
    return sorted(contacts, key=lambda contact: contact.name.casefold())


def load_recent_calls():
    rows = query("content://call_log/calls", ["name", "number", "type", "date"], sort="date DESC")
    if rows is None:
        return None
    calls = []
    for name, number, kind, date in rows[:RECENT_CALLS]:
        if number and date and date.isdigit():
            calls.append(RecentCall(name or "", number, CALL_KINDS.get(kind, "incoming"),
                                    datetime.fromtimestamp(int(date) / 1000)))
    return calls


class Phone:
    def __init__(self, on_call_change):
        """on_call_change(state, number) is called from a background thread when the phone starts
        ringing ("ringing"), is on a call ("offhook"), or goes back to "idle"."""
        self.on_call_change = on_call_change
        self.state = "idle"
        threading.Thread(target=self.watch, daemon=True).start()

    def watch(self):
        while True:
            state, number = self.read_call_state()
            if state != self.state:
                self.state = state
                self.on_call_change(state, number)
            time.sleep(POLL_SECONDS)

    @staticmethod
    def read_call_state():
        output = adb_shell("dumpsys", "telephony.registry")
        if output is None:
            return "idle", ""  # phone unplugged: no call to show
        states = [CALL_STATES.get(s, "idle") for s in re.findall(r"mCallState=(\d)", output)]
        state = max(states, key=STATE_PRIORITY.index, default="idle")
        numbers = [n for n in re.findall(r"mCallIncomingNumber=(\S*)", output) if n]
        return state, numbers[0] if numbers else ""

    # ---------- Actions (each on a background thread so the screen never waits on the phone) ----------

    @staticmethod
    def in_background(function, *args):
        threading.Thread(target=function, args=args, daemon=True).start()

    def call(self, number):
        self.in_background(self._call, number)

    @staticmethod
    def _call(number):
        dialable = re.sub(r"[^\d+*#]", "", number).replace("#", "%23")
        output = adb_shell("am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{dialable}")
        if output is None or "Error" in output or "Denial" in output:
            # Not allowed to call directly: open the phone's dialer with the number filled in instead.
            adb_shell("am", "start", "-a", "android.intent.action.DIAL", "-d", f"tel:{dialable}")

    def answer(self):
        self.in_background(adb_shell, "input", "keyevent", "KEYCODE_CALL")

    def hang_up(self):
        self.in_background(adb_shell, "input", "keyevent", "KEYCODE_ENDCALL")
