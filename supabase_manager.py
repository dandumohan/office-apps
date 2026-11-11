#!/usr/bin/env python3
"""Supabase Backup Manager - desktop GUI for Ubuntu (Tkinter, no extra pip packages).

Setup (one time):   sudo apt install -y python3-tk postgresql-client
Run:                python3 supabase_manager.py
"""
import hashlib
import hmac
import json
import math
import os
import queue
import re
import secrets
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

# ----------------------------------------------------------------- settings
BASE_DIR = "/home/tharun/Downloads/msource2026"
BACKUP_SCRIPT = os.path.join(BASE_DIR, "backup-supabase.sh")
BACKUP_DIR = os.path.join(BASE_DIR, "supabase-backups")
LOG_FILE = os.path.join(BACKUP_DIR, "backup.log")
URL_FILE = os.path.expanduser("~/.config/supabase_db_url")
DB_URL = "postgresql://postgres:DanduTahrun@db.ewnrcnfyiulrjritaeam.supabase.co:5432/postgres"

SETTINGS_FILE = os.path.expanduser("~/.config/supabase_manager.json")
USERS_FILE = os.path.expanduser("~/.config/supabase_manager_users.json")
IDLE_LOGOUT_MINUTES = 15      # auto sign-out after this much inactivity (0 = never)
MAX_ATTEMPTS, LOCK_SECONDS = 5, 30


def load_settings():
    """Override the defaults above with anything saved from the Settings screen."""
    global BASE_DIR, BACKUP_SCRIPT, BACKUP_DIR, LOG_FILE, DB_URL
    try:
        with open(SETTINGS_FILE) as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        return
    BACKUP_SCRIPT = cfg.get("backup_script", BACKUP_SCRIPT)
    BACKUP_DIR = cfg.get("backup_dir", BACKUP_DIR)
    DB_URL = cfg.get("db_url", DB_URL)
    LOG_FILE = os.path.join(BACKUP_DIR, "backup.log")


def save_settings(script, folder, url):
    global BACKUP_SCRIPT, BACKUP_DIR, LOG_FILE, DB_URL
    BACKUP_SCRIPT, BACKUP_DIR, DB_URL = script, folder, url
    LOG_FILE = os.path.join(BACKUP_DIR, "backup.log")
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump({"backup_script": script, "backup_dir": folder, "db_url": url}, f, indent=2)
    os.chmod(SETTINGS_FILE, 0o600)


AUDIT_FILE = os.path.expanduser("~/.config/supabase_manager_audit.log")

# What each permission allows. Roles are just ready-made sets of permissions.
PERMS = {
    "backup":    "Run backups",
    "restore":   "Restore databases",
    "backup_delete": "Delete old backup files",
    "cron_view": "View scheduled jobs",
    "cron_edit": "Create / change the schedule",
    "settings":  "Edit settings and backup script",
    "users":     "Manage users and permissions (administrator)",
}
ROLES = {
    "Administrator": list(PERMS),
    "Operator": ["backup", "restore", "cron_view"],
    "Viewer": ["cron_view"],
}
# dropdown entry -> permission needed (None = every signed-in user)
ACTION_PERM = {"Backup": "backup", "Restore": "restore", "Crontab job": "cron_edit",
               "Crontab list": "cron_view", "Settings": "settings", "Users": "users",
               "My account": None}
ACTIONS = list(ACTION_PERM)
PRESETS = {
    "Daily at 2:00 AM": ("0", "2", "*", "*", "*"),
    "Every 6 hours": ("0", "*/6", "*", "*", "*"),
    "Every Sunday at 3:00 AM": ("0", "3", "*", "*", "0"),
    "Weekdays at 9:00 PM": ("0", "21", "*", "*", "1-5"),
    "1st of every month, 1:00 AM": ("0", "1", "1", "*", "*"),
    "Custom": None,
}

# ----------------------------------------------------------------- palette
NAVY, NAVY_2 = "#12263f", "#1c3a5e"
ACCENT, ACCENT_HOVER = "#2f80ed", "#1f6dd8"
BG, CARD, BORDER = "#f2f5f9", "#ffffff", "#dde3ec"
TEXT, MUTED = "#1f2d3d", "#6b7a90"
OK, WARN, ERR = "#1f9d62", "#d98a00", "#d64545"
CONSOLE_BG, CONSOLE_FG = "#0f1722", "#d6e2f0"


def valid_field(value, lo, hi):
    if not re.fullmatch(r"\*|\*/\d+|\d+(-\d+)?(/\d+)?(,\d+(-\d+)?(/\d+)?)*", value):
        return False
    if value.startswith("*/"):
        return True
    return all(lo <= int(n) <= hi for n in re.findall(r"\d+", value))


# DMN SOFT logo (rendered from dmn-soft-logo.svg and embedded, so the app stays a single file)
ICON_PNG = "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"


class AnimatedLogo(tk.Canvas):
    """DMN SOFT logo drawn natively: orbiting pulsing dots, blooming petals, DMN centre, wordmark.
    Geometry and timings follow dmn-soft-logo.svg (orbit 18 s, bloom 9 s, pulse 2.4 s)."""
    K = 0.88                      # display scale of the 254x68 SVG
    W, H = 242, 74                # white panel size

    def __init__(self, master, bg):
        super().__init__(master, width=self.W, height=self.H, bg=bg, highlightthickness=0)
        r, w, h = 14, self.W - 1, self.H - 1
        pts = [r, 1, w - r, 1, w, 1, w, r, w, h - r, w, h, w - r, h, r, h, 1, h, 1, h - r, 1, r, 1, 1]
        self.create_polygon(pts, smooth=True, fill="#ffffff", outline="")
        self.ox = (self.W - 254 * self.K) / 2 + 2 * self.K
        self.oy = (self.H - 68 * self.K) / 2 + 2 * self.K
        self._wordmark()
        self.t0 = datetime.now().timestamp()
        self._tick()

    def _p(self, x, y):
        return self.ox + x * self.K, self.oy + y * self.K

    def _wordmark(self):
        import tkinter.font as tkfont
        px = -round(26 * self.K)
        bold = tkfont.Font(family="Arial", size=px, weight="bold")
        reg = tkfont.Font(family="Arial", size=px, weight="normal")
        x, y = self._p(76, 41)
        for ch in "DMN":
            self.create_text(x, y, text=ch, anchor="sw", font=bold, fill="#c2410c")
            x += bold.measure(ch) + 1.5 * self.K
        x += 8 * self.K
        for ch in "SOFT":
            self.create_text(x, y, text=ch, anchor="sw", font=reg, fill="#e8590c")
            x += reg.measure(ch) + 1.5 * self.K

    @staticmethod
    def _mix(alpha, rgb=(0xe8, 0x59, 0x0c)):
        c = [round(255 + (v - 255) * alpha) for v in rgb]
        return "#%02x%02x%02x" % tuple(c)

    def _tick(self):
        import math
        try:
            if not self.winfo_exists():
                return
            t = datetime.now().timestamp() - self.t0
            self.delete("anim")
            cx, cy = 32, 32
            # orbit: 10 dots, rotating once per 18 s, each pulsing (2.4 s) with staggered delay
            spin = 360 * (t % 18) / 18
            for i in range(10):
                a = math.radians(i * 36 + spin)
                x, y = self._p(cx + 28 * math.sin(a), cy - 28 * math.cos(a))
                rad = (2.3 if i % 2 == 0 else 1.6) * self.K
                op = 0.4 + 0.6 * (1 - math.cos(2 * math.pi * ((t + 0.24 * i) % 2.4) / 2.4)) / 2
                self.create_oval(x - rad, y - rad, x + rad, y + rad, fill=self._mix(op),
                                 outline="", tags="anim")
            # petals: bloom scale 1 -> 1.06 and rotate 0 -> 6 deg over 9 s (ease in/out)
            e = (1 - math.cos(2 * math.pi * (t % 9) / 9)) / 2
            sc, br = 1 + 0.06 * e, math.radians(6 * e)
            for k in range(6):
                ang = math.radians(60 * k) + br
                ca, sa = math.cos(ang), math.sin(ang)
                pts = []
                for j in range(28):
                    u = 2 * math.pi * j / 28
                    px, py = 5.8 * math.cos(u), -12.6 + 11.6 * math.sin(u)
                    px, py = px * sc, py * sc
                    x, y = self._p(cx + px * ca - py * sa, cy + px * sa + py * ca)
                    pts += [x, y]
                self.create_polygon(pts, fill="#e8590c" if k % 2 == 0 else "#ff8a3d",
                                    outline="", tags="anim")
            # centre disc with DMN
            x0, y0 = self._p(cx - 11.6, cy - 11.6)
            x1, y1 = self._p(cx + 11.6, cy + 11.6)
            self.create_oval(x0, y0, x1, y1, fill="#2f4f73", outline="#ffffff", width=1.4, tags="anim")
            mx, my = self._p(cx, cy + 0.2)
            self.create_text(mx, my, text="DMN", fill="#ffffff",
                             font=("Arial", -round(8.6 * self.K), "bold"), tags="anim")
            self.after(40, self._tick)
        except tk.TclError:
            pass


class Auth:
    """Local accounts with roles/permissions: salted PBKDF2 hashes in a private (chmod 600) JSON file."""
    ITER = 200_000

    @staticmethod
    def _load():
        try:
            with open(USERS_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _save(users):
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        with open(USERS_FILE, "w") as f:
            json.dump(users, f, indent=2)
        os.chmod(USERS_FILE, 0o600)

    @staticmethod
    def has_users():
        return bool(Auth._load())

    @staticmethod
    def _hash(password, salt, iters):
        return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iters).hex()

    @staticmethod
    def _norm(rec):
        """Accounts created before roles existed are administrators."""
        role = rec.get("role", "Administrator")
        if role == "Administrator":          # the administrator role always has every permission
            return role, list(PERMS)
        perms = rec.get("perms")
        if perms is None:
            perms = ROLES.get(role, [])
        return role, [p for p in PERMS if p in perms]

    @staticmethod
    def list_users():
        out = []
        for name, rec in sorted(Auth._load().items()):
            role, perms = Auth._norm(rec)
            out.append((name, role, perms))
        return out

    @staticmethod
    def perms(user):
        rec = Auth._load().get(user)
        return Auth._norm(rec)[1] if rec else []

    @staticmethod
    def role(user):
        rec = Auth._load().get(user)
        return Auth._norm(rec)[0] if rec else ""

    @staticmethod
    def create_user(user, password, role="Operator", perms=None):
        users = Auth._load()
        salt = secrets.token_hex(16)
        users[user] = {"salt": salt, "iters": Auth.ITER, "hash": Auth._hash(password, salt, Auth.ITER),
                       "role": role, "perms": list(ROLES.get(role, []) if perms is None else perms)}
        Auth._save(users)

    @staticmethod
    def set_password(user, password):
        users = Auth._load()
        rec = users.get(user, {})
        salt = secrets.token_hex(16)
        rec.update({"salt": salt, "iters": Auth.ITER, "hash": Auth._hash(password, salt, Auth.ITER)})
        users[user] = rec
        Auth._save(users)

    @staticmethod
    def set_access(user, role, perms):
        users = Auth._load()
        if user in users:
            users[user]["role"], users[user]["perms"] = role, list(perms)
            Auth._save(users)

    @staticmethod
    def delete(user):
        users = Auth._load()
        if users.pop(user, None) is not None:
            Auth._save(users)

    @staticmethod
    def admins_other_than(user):
        return [n for n, _, p in Auth.list_users() if n != user and "users" in p]

    @staticmethod
    def verify(user, password):
        rec = Auth._load().get(user)
        if not rec:   # keep timing similar for unknown users
            Auth._hash(password, "00" * 16, Auth.ITER)
            return False
        return hmac.compare_digest(Auth._hash(password, rec["salt"], rec["iters"]), rec["hash"])

    @staticmethod
    def audit(user, text):
        try:
            os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
            with open(AUDIT_FILE, "a") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {user or '-':<14} {text}\n")
            os.chmod(AUDIT_FILE, 0o600)
        except OSError:
            pass


class LoginScreen(tk.Frame):
    """Full-window sign-in page. First run asks to create the administrator account."""

    def __init__(self, master, on_success):
        super().__init__(master, bg=NAVY)
        self.on_success = on_success
        self.fails, self.locked_until = 0, 0
        self.setup_mode = False

        col = tk.Frame(self, bg=NAVY)
        col.place(relx=0.5, rely=0.5, anchor="center")
        AnimatedLogo(col, NAVY).pack(pady=(0, 18))
        tk.Label(col, text="Supabase Backup Manager", bg=NAVY, fg="white",
                 font=("Ubuntu", 18, "bold")).pack()
        self.sub = tk.Label(col, text="", bg=NAVY, fg="#9fb6d3", font=("Ubuntu", 10))
        self.sub.pack(pady=(2, 16))

        border = tk.Frame(col, bg=ACCENT)
        border.pack()
        card = tk.Frame(border, bg=CARD, padx=28, pady=22)
        card.pack(padx=0, pady=(3, 0))
        self.user = tk.StringVar()
        self.pw = tk.StringVar()
        self.pw2 = tk.StringVar()
        self._row(card, "Username", self.user)
        self.e_user = card.winfo_children()[-1]
        self._row(card, "Password", self.pw, show="\u2022")
        self.e_pw = card.winfo_children()[-1]
        self.lbl2 = ttk.Label(card, text="Confirm password", style="Card.TLabel")
        self.e_pw2 = ttk.Entry(card, textvariable=self.pw2, show="\u2022", width=32)
        self.msg = tk.Label(card, text="", bg=CARD, fg=ERR, font=("Ubuntu", 9), wraplength=270,
                            justify="left")
        self.msg.pack(anchor="w", pady=(10, 0))
        self.btn = ttk.Button(card, text="Sign in", style="Accent.TButton", command=self.submit)
        self.btn.pack(fill="x", pady=(12, 0))
        tk.Label(col, text="\u00A9 DMN SOFT", bg=NAVY, fg="#6f87a8", font=("Ubuntu", 9)).pack(pady=(16, 0))
        for e in (self.e_user, self.e_pw, self.e_pw2):
            e.bind("<Return>", lambda ev: self.submit())

    def _row(self, parent, label, var, show=None):
        ttk.Label(parent, text=label, style="Card.TLabel").pack(anchor="w", pady=(8, 3))
        ttk.Entry(parent, textvariable=var, show=show or "", width=32).pack(fill="x")

    def reset(self, message=None, ok=False):
        """Show the page ready for a new sign-in (or first-run account creation)."""
        self.setup_mode = not Auth.has_users()
        self.pw.set("")
        self.pw2.set("")
        if self.setup_mode:
            self.sub.config(text="First-time setup \u2022 create the administrator account")
            self.lbl2.pack(anchor="w", pady=(8, 3), before=self.msg)
            self.e_pw2.pack(fill="x", before=self.msg)
            self.btn.config(text="Create account")
        else:
            self.sub.config(text="Sign in to continue")
            self.lbl2.pack_forget()
            self.e_pw2.pack_forget()
            self.btn.config(text="Sign in")
        self.msg.config(text=message or "", fg=OK if ok else ERR)
        self.lift()
        self.e_pw.focus_set() if self.user.get() else self.e_user.focus_set()

    def submit(self):
        user, pw = self.user.get().strip(), self.pw.get()
        now = time.time()
        if now < self.locked_until:
            return
        if not user or not pw:
            return self.msg.config(text="Enter username and password.", fg=ERR)
        if self.setup_mode:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", user):
                return self.msg.config(text="Username: 3-32 letters, numbers, . _ -", fg=ERR)
            if len(pw) < 8:
                return self.msg.config(text="Password must be at least 8 characters.", fg=ERR)
            if pw != self.pw2.get():
                return self.msg.config(text="Passwords do not match.", fg=ERR)
            try:
                Auth.create_user(user, pw, "Administrator", list(PERMS))
            except OSError as e:
                return self.msg.config(text=f"Could not save account: {e}", fg=ERR)
            Auth.audit(user, "administrator account created")
            return self._ok(user)
        if Auth.verify(user, pw):
            return self._ok(user)
        self.fails += 1
        Auth.audit(user, "login FAILED")
        self.pw.set("")
        left = MAX_ATTEMPTS - self.fails
        if left <= 0:
            self.fails = 0
            self.locked_until = time.time() + LOCK_SECONDS
            self._countdown()
        else:
            self.msg.config(text=f"Incorrect username or password. {left} attempt(s) left.", fg=ERR)

    def _countdown(self):
        left = math.ceil(self.locked_until - time.time())
        if left > 0:
            self.btn.config(state="disabled")
            self.msg.config(text=f"Too many attempts. Try again in {left}s.", fg=ERR)
            self.after(500, self._countdown)
        else:
            self.btn.config(state="normal")
            self.msg.config(text="")

    def _ok(self, user):
        self.fails = 0
        self.pw.set("")
        self.pw2.set("")
        self.msg.config(text="")
        self.on_success(user)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Supabase Backup Manager")
        self.geometry("980x720")
        self.minsize(900, 640)
        self.configure(bg=BG)
        try:
            self.icon_img = tk.PhotoImage(data=ICON_PNG)
            self.iconphoto(True, self.icon_img)
        except tk.TclError:
            pass
        self.q = queue.Queue()
        self.busy = False
        self._style()
        self._build()
        self.on_action_change()
        self.after(100, self._drain)
        # ---- authentication
        self.current_user = None
        self.perms = set()
        self.last_active = time.time()
        self.login = LoginScreen(self, self._on_login)
        self.login.place(x=0, y=0, relwidth=1, relheight=1)
        self.login.reset()
        for ev in ("<Key>", "<Button>", "<Motion>"):
            self.bind_all(ev, self._touch, add="+")
        self.after(15000, self._idle_check)

    # ------------------------------------------------------------------ style
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", font=("Ubuntu", 10), background=BG, foreground=TEXT)
        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=BG, foreground=TEXT)
        s.configure("Card.TLabel", background=CARD, foreground=TEXT)
        s.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=("Ubuntu", 9))
        s.configure("Section.TLabel", background=CARD, foreground=NAVY, font=("Ubuntu", 12, "bold"))
        s.configure("TEntry", fieldbackground="#ffffff", bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, padding=6)
        s.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
              darkcolor=[("focus", ACCENT)])
        s.configure("TCombobox", fieldbackground="#ffffff", bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, arrowcolor=NAVY, padding=6)
        s.map("TCombobox", fieldbackground=[("readonly", "#ffffff")],
              bordercolor=[("focus", ACCENT)])
        s.configure("Accent.TButton", background=ACCENT, foreground="white",
                    font=("Ubuntu", 10, "bold"), padding=(18, 9), borderwidth=0)
        s.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#9db9e0")])
        s.configure("Logout.TButton", background=NAVY_2, foreground="white", padding=(14, 7),
                    borderwidth=0, font=("Ubuntu", 10, "bold"))
        s.map("Logout.TButton", background=[("active", "#27507d")])
        s.configure("Danger.TButton", background=ERR, foreground="white", font=("Ubuntu", 10, "bold"),
                    padding=(18, 9), borderwidth=0)
        s.map("Danger.TButton", background=[("active", "#b83232"), ("disabled", "#e8a5a5")])
        s.configure("Ghost.TButton", background="#e8edf4", foreground=NAVY,
                    padding=(12, 7), borderwidth=0)
        s.map("Ghost.TButton", background=[("active", "#d8e0ec")])
        s.configure("TCheckbutton", background=CARD, foreground=TEXT)
        s.configure("Horizontal.TProgressbar", troughcolor="#dfe6f0", background=ACCENT,
                    bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT, thickness=6)
        s.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=TEXT,
                    rowheight=26, borderwidth=0, font=("Ubuntu", 10))
        s.configure("Treeview.Heading", background="#e8edf4", foreground=NAVY, relief="flat",
                    font=("Ubuntu", 9, "bold"), padding=6)
        s.map("Treeview", background=[("selected", "#dbe8fb")], foreground=[("selected", NAVY)])
        s.map("Treeview.Heading", background=[("active", "#dde5f0")])
        self.option_add("*TCombobox*Listbox.font", ("Ubuntu", 10))
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    # ----------------------------------------------------------------- layout
    def _build(self):
        # Header
        head = tk.Frame(self, bg=NAVY)
        head.pack(fill="x")
        tk.Frame(head, bg=ACCENT, height=3).pack(fill="x", side="bottom")
        inner = tk.Frame(head, bg=NAVY)
        inner.pack(fill="x", padx=24, pady=16)
        badge = AnimatedLogo(inner, NAVY)
        badge.pack(side="left")
        titles = tk.Frame(inner, bg=NAVY)
        titles.pack(side="left", padx=14)
        tk.Label(titles, text="Supabase Backup Manager", bg=NAVY, fg="white",
                 font=("Ubuntu", 17, "bold")).pack(anchor="w")
        tk.Label(titles, text="Backup  •  Restore  •  Schedule", bg=NAVY, fg="#9fb6d3",
                 font=("Ubuntu", 10)).pack(anchor="w")
        self.logout_btn = ttk.Button(inner, text="\u23FB  Logout", style="Logout.TButton",
                                     command=self.logout)
        self.logout_btn.pack(side="right", padx=(16, 0))
        right_info = tk.Frame(inner, bg=NAVY)
        right_info.pack(side="right")
        self.user_lbl = tk.Label(right_info, bg=NAVY, fg="white", font=("Ubuntu", 11, "bold"), anchor="e")
        self.user_lbl.pack(anchor="e")
        self.clock = tk.Label(right_info, bg=NAVY, fg="#9fb6d3", font=("Ubuntu", 9), anchor="e")
        self.clock.pack(anchor="e")
        self._tick()

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=20, pady=16)
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ---- left: control card
        left = self._card(body, 0)
        ttk.Label(left, text="Action", style="Section.TLabel").pack(anchor="w", padx=20, pady=(18, 6))
        self.action = tk.StringVar(value=ACTIONS[0])
        self.combo = ttk.Combobox(left, textvariable=self.action, values=ACTIONS, state="readonly")
        self.combo.pack(fill="x", padx=20)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._on_pick())
        ttk.Separator(left).pack(fill="x", padx=20, pady=16)

        self.opts = ttk.Frame(left, style="Card.TFrame")
        self.opts.pack(fill="both", expand=True, padx=20)

        self.run_btn = ttk.Button(left, text="▶  Run", style="Accent.TButton", command=self.run)
        self.run_btn.pack(fill="x", padx=20, pady=18)

        # ---- right: output card
        right = self._card(body, 1)
        bh = ttk.Frame(right, style="Card.TFrame")
        bh.pack(fill="x", padx=20, pady=(18, 8))
        ttk.Label(bh, text="Backups", style="Section.TLabel").pack(side="left")
        self.del_btns = ttk.Frame(bh, style="Card.TFrame")
        ttk.Button(self.del_btns, text="\U0001F5D1  Clean up...", style="Ghost.TButton",
                   command=self.cleanup_dialog).pack(side="right", padx=(6, 0))
        ttk.Button(self.del_btns, text="Delete selected", style="Ghost.TButton",
                   command=self.delete_selected).pack(side="right")
        tw = tk.Frame(right, bg=BORDER)
        tw.pack(fill="x", padx=20)
        self.tree = ttk.Treeview(tw, columns=("n", "file", "size", "created"), show="headings",
                                 height=5, selectmode="extended")
        for col, text, w, anc in (("n", "#", 34, "center"), ("file", "File", 200, "w"),
                                  ("size", "Size", 70, "e"), ("created", "Created", 110, "center")):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, minwidth=w if col != "file" else 150, anchor=anc, stretch=(col == "file"))
        tsb = ttk.Scrollbar(tw, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="x", expand=True, padx=1, pady=1)
        self.bk_summary = ttk.Label(right, text="", style="Muted.TLabel")
        self.bk_summary.pack(anchor="w", padx=20, pady=(4, 0))
        self.tree.tag_configure("latest", foreground=OK, font=("Ubuntu", 10, "bold"))
        self.tree.tag_configure("new", background="#e3f6ec", foreground=OK, font=("Ubuntu", 10, "bold"))
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._pick_backup())
        top = ttk.Frame(right, style="Card.TFrame")
        top.pack(fill="x", padx=20, pady=(16, 8))
        ttk.Label(top, text="Output", style="Section.TLabel").pack(side="left")
        ttk.Button(top, text="Clear", style="Ghost.TButton", command=self.clear).pack(side="right")
        wrap = tk.Frame(right, bg=CONSOLE_BG)
        wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.console = tk.Text(wrap, bg=CONSOLE_BG, fg=CONSOLE_FG, insertbackground=CONSOLE_FG,
                               font=("Ubuntu Mono", 10), relief="flat", wrap="word",
                               padx=12, pady=10, state="disabled")
        sb = ttk.Scrollbar(wrap, command=self.console.yview)
        self.console.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.console.pack(side="left", fill="both", expand=True)
        for tag, color in (("ok", "#4ade80"), ("err", "#ff7b7b"), ("warn", "#fbbf24"),
                           ("info", "#7cb6ff"), ("dim", "#7f8ea3")):
            self.console.tag_configure(tag, foreground=color)

        # ---- status bar
        bar = tk.Frame(self, bg="#e9eef5")
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text="Ready", bg="#e9eef5", fg=MUTED, anchor="w",
                               font=("Ubuntu", 9))
        self.status.pack(side="left", padx=20, pady=6)
        self.pb = ttk.Progressbar(bar, mode="indeterminate", length=160)

        self.log("Welcome. Choose an action on the left and press Run.", "dim")
        self.refresh_backups()

    def _card(self, parent, column):
        outer = tk.Frame(parent, bg=BORDER)
        outer.grid(row=0, column=column, sticky="nsew", padx=(0, 14) if column == 0 else 0)
        if column == 0:
            outer.configure(width=400)
            outer.pack_propagate(False)
        card = ttk.Frame(outer, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=1, pady=1)
        return card

    # ---------------------------------------------------------------- auth
    def _touch(self, _e=None):
        self.last_active = time.time()

    def _on_login(self, user):
        self.current_user = user
        self.perms = set(Auth.perms(user))
        self.user_lbl.config(text=f"\u25CF  {user}  \u2022  {Auth.role(user)}")
        self.login.place_forget()
        self._touch()
        self._apply_perms()
        Auth.audit(user, "signed in")
        self.log(f"Signed in as {user} ({Auth.role(user)}) at {datetime.now():%H:%M:%S}.", "ok")

    def allowed_actions(self):
        return [a for a in ACTIONS if ACTION_PERM[a] is None or ACTION_PERM[a] in self.perms]

    def _apply_perms(self):
        """Show only the dropdown entries this user is allowed to use."""
        allowed = self.allowed_actions()
        if "backup_delete" in self.perms:
            self.del_btns.pack(side="right")
        else:
            self.del_btns.pack_forget()
        self.combo.config(values=allowed)
        if self.action.get() not in allowed:
            self.action.set(allowed[0])
        self.on_action_change()
        self.refresh_backups()

    def logout(self, auto=False):
        if self.current_user is None:
            return
        if self.busy:
            return messagebox.showwarning("Logout", "A task is still running. Wait for it to finish first.")
        who = self.current_user
        Auth.audit(who, "signed out (inactivity)" if auto else "signed out")
        self.current_user = None
        self.perms = set()
        self.del_btns.pack_forget()
        self.user_lbl.config(text="")
        self.clear()
        self.log("Welcome. Choose an action on the left and press Run.", "dim")
        self.action.set(ACTIONS[0])
        self.on_action_change()          # rebuilds panels, wiping any typed passwords
        self.refresh_backups()
        self.login.place(x=0, y=0, relwidth=1, relheight=1)
        self.login.reset("Signed out automatically after inactivity." if auto
                         else f"{who} signed out.", ok=not auto)

    # ------------------------------------------------------- user management
    def _modal(self, title):
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=CARD)
        win.transient(self)
        win.resizable(False, False)
        body = ttk.Frame(win, style="Card.TFrame")
        body.pack(padx=24, pady=20)
        win.after(50, lambda: (win.winfo_exists() and win.grab_set()))
        return win, body

    def _fill_users(self):
        self.utree.delete(*self.utree.get_children())
        for name, role, perms in Auth.list_users():
            self.utree.insert("", "end", iid=name, values=(name, role, f"{len(perms)} of {len(PERMS)}"))

    def _selected_user(self):
        sel = self.utree.selection()
        if not sel:
            messagebox.showinfo("Users", "Select a user in the list first.")
            return None
        return sel[0]

    def user_dialog(self, existing=None):
        """Add a user (existing=None) or edit a user's role and permissions."""
        win, body = self._modal("Edit access" if existing else "Add user")
        cur_role = Auth.role(existing) if existing else "Operator"
        cur_perms = set(Auth.perms(existing)) if existing else set(ROLES["Operator"])
        name_v, pw_v, pw2_v, role_v = tk.StringVar(value=existing or ""), tk.StringVar(), tk.StringVar(), tk.StringVar(value=cur_role)
        ttk.Label(body, text="Username", style="Card.TLabel").pack(anchor="w", pady=(0, 3))
        e = ttk.Entry(body, textvariable=name_v, width=36, state="disabled" if existing else "normal")
        e.pack(fill="x")
        if not existing:
            for label, v in (("Password (min 8 characters)", pw_v), ("Confirm password", pw2_v)):
                ttk.Label(body, text=label, style="Card.TLabel").pack(anchor="w", pady=(8, 3))
                ttk.Entry(body, textvariable=v, show="\u2022", width=36).pack(fill="x")
        ttk.Label(body, text="Role", style="Card.TLabel").pack(anchor="w", pady=(10, 3))
        rc = ttk.Combobox(body, textvariable=role_v, values=list(ROLES) + ["Custom"], state="readonly")
        rc.pack(fill="x")
        ttk.Label(body, text="Permissions", style="Card.TLabel").pack(anchor="w", pady=(10, 2))
        pvars = {k: tk.BooleanVar(value=(k in cur_perms)) for k in PERMS}

        def sync_role(_=None):
            chosen = {k for k, v in pvars.items() if v.get()}
            role_v.set(next((r for r, p in ROLES.items() if set(p) == chosen), "Custom"))

        def apply_role(_=None):
            if role_v.get() in ROLES:
                for k, v in pvars.items():
                    v.set(k in ROLES[role_v.get()])
        rc.bind("<<ComboboxSelected>>", apply_role)
        for k, label in PERMS.items():
            ttk.Checkbutton(body, text=label, variable=pvars[k], command=sync_role).pack(anchor="w", pady=1)
        err = tk.Label(body, text="", bg=CARD, fg=ERR, font=("Ubuntu", 9), wraplength=320, justify="left")
        err.pack(anchor="w", pady=(8, 0))

        def save():
            perms = [k for k in PERMS if pvars[k].get()]
            role = role_v.get()
            if existing:
                if "users" not in perms and not Auth.admins_other_than(existing):
                    return err.config(text="This is the only administrator. Keep 'Manage users' on, or make another administrator first.")
                Auth.set_access(existing, role, perms)
                Auth.audit(self.current_user, f"changed access of {existing}: {role} {perms}")
                if existing == self.current_user:
                    self.perms = set(perms)
                    self.user_lbl.config(text=f"\u25CF  {existing}  \u2022  {role}")
                    self._apply_perms()
                    self.action.set("Users" if "users" in perms else self.allowed_actions()[0])
                    self.on_action_change()
            else:
                u, p1, p2 = name_v.get().strip(), pw_v.get(), pw2_v.get()
                if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", u):
                    return err.config(text="Username: 3-32 letters, numbers, . _ -")
                if u in {n for n, _, _ in Auth.list_users()}:
                    return err.config(text="That username already exists.")
                if len(p1) < 8:
                    return err.config(text="Password must be at least 8 characters.")
                if p1 != p2:
                    return err.config(text="Passwords do not match.")
                Auth.create_user(u, p1, role, perms)
                Auth.audit(self.current_user, f"created user {u}: {role} {perms}")
                self.log(f"\u2714 User '{u}' created as {role}.", "ok")
            self._fill_users()
            win.destroy()
        ttk.Button(body, text="Save", style="Accent.TButton", command=save).pack(fill="x", pady=(10, 0))

    def user_add(self):
        self.user_dialog(None)

    def user_edit(self):
        u = self._selected_user()
        if u:
            self.user_dialog(u)

    def user_reset_pw(self):
        u = self._selected_user()
        if not u:
            return
        win, body = self._modal(f"Reset password - {u}")
        vs = []
        for label in ("New password (min 8 characters)", "Confirm new password"):
            ttk.Label(body, text=label, style="Card.TLabel").pack(anchor="w", pady=(8, 3))
            v = tk.StringVar()
            ttk.Entry(body, textvariable=v, show="\u2022", width=34).pack(fill="x")
            vs.append(v)
        err = tk.Label(body, text="", bg=CARD, fg=ERR, font=("Ubuntu", 9))
        err.pack(anchor="w", pady=(8, 0))

        def save():
            p1, p2 = vs[0].get(), vs[1].get()
            if len(p1) < 8:
                return err.config(text="Password must be at least 8 characters.")
            if p1 != p2:
                return err.config(text="Passwords do not match.")
            Auth.set_password(u, p1)
            Auth.audit(self.current_user, f"reset password of {u}")
            self.log(f"\u2714 Password reset for '{u}'.", "ok")
            win.destroy()
        ttk.Button(body, text="Reset password", style="Accent.TButton", command=save).pack(fill="x", pady=(10, 0))

    def user_delete(self):
        u = self._selected_user()
        if not u:
            return
        if u == self.current_user:
            return messagebox.showerror("Delete user", "You cannot delete the account you are signed in with.")
        if "users" in Auth.perms(u) and not Auth.admins_other_than(u):
            return messagebox.showerror("Delete user", "That is the only administrator.")
        if messagebox.askyesno("Delete user", f"Delete user '{u}'? This cannot be undone."):
            Auth.delete(u)
            Auth.audit(self.current_user, f"deleted user {u}")
            self.log(f"User '{u}' deleted.", "warn")
            self._fill_users()

    def show_audit(self):
        win = tk.Toplevel(self)
        win.title("Activity log")
        win.geometry("760x420")
        win.transient(self)
        txt = tk.Text(win, font=("Ubuntu Mono", 10), wrap="none", bg=CONSOLE_BG, fg=CONSOLE_FG, relief="flat", padx=10, pady=8)
        sb = ttk.Scrollbar(win, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        try:
            with open(AUDIT_FILE) as f:
                lines = f.readlines()[-300:]
        except OSError:
            lines = ["(no activity recorded yet)\n"]
        txt.insert("1.0", "".join(lines))
        txt.see("end")
        txt.config(state="disabled")

    def _idle_check(self):
        if (IDLE_LOGOUT_MINUTES and self.current_user and not self.busy
                and time.time() - self.last_active > IDLE_LOGOUT_MINUTES * 60):
            self.logout(auto=True)
        self.after(15000, self._idle_check)

    def change_password(self):
        win = tk.Toplevel(self)
        win.title("Change password")
        win.configure(bg=CARD)
        win.transient(self)
        win.resizable(False, False)
        body = ttk.Frame(win, style="Card.TFrame")
        body.pack(padx=24, pady=20)
        vars_ = []
        for label in ("Current password", "New password (min 8 characters)", "Confirm new password"):
            ttk.Label(body, text=label, style="Card.TLabel").pack(anchor="w", pady=(8, 3))
            v = tk.StringVar()
            ttk.Entry(body, textvariable=v, show="\u2022", width=34).pack(fill="x")
            vars_.append(v)
        err = tk.Label(body, text="", bg=CARD, fg=ERR, font=("Ubuntu", 9))
        err.pack(anchor="w", pady=(8, 0))

        def save():
            old, new, conf = (v.get() for v in vars_)
            if not Auth.verify(self.current_user, old):
                return err.config(text="Current password is incorrect.")
            if len(new) < 8:
                return err.config(text="New password must be at least 8 characters.")
            if new != conf:
                return err.config(text="New passwords do not match.")
            Auth.set_password(self.current_user, new)
            Auth.audit(self.current_user, "changed own password")
            self.log("\u2714 Password changed.", "ok")
            win.destroy()
        ttk.Button(body, text="Change password", style="Accent.TButton", command=save).pack(fill="x", pady=(10, 0))

    def _tick(self):
        self.clock.config(text=datetime.now().strftime("%a %d %b %Y   %H:%M"))
        self.after(30000, self._tick)

    # --------------------------------------------------------- option panels
    def _clear_opts(self):
        for w in self.opts.winfo_children():
            w.destroy()

    def _field(self, label, var=None, show=None, width=None):
        ttk.Label(self.opts, text=label, style="Card.TLabel").pack(anchor="w", pady=(8, 3))
        e = ttk.Entry(self.opts, textvariable=var, show=show or "", width=width or 30)
        e.pack(fill="x")
        return e

    def on_action_change(self):
        self._clear_opts()
        a = self.action.get()
        if a == "Backup":
            ttk.Label(self.opts, text="Create a full database backup now.",
                      style="Card.TLabel", wraplength=320).pack(anchor="w")
            masked = re.sub(r"(postgresql://[^:]+:)[^@]+(@)", r"\1••••••\2", DB_URL)
            ttk.Label(self.opts, text="Connection", style="Card.TLabel").pack(anchor="w", pady=(14, 3))
            ttk.Label(self.opts, text=masked, style="Muted.TLabel", wraplength=330).pack(anchor="w")
            ttk.Label(self.opts, text="Saved to", style="Card.TLabel").pack(anchor="w", pady=(12, 3))
            ttk.Label(self.opts, text=URL_FILE, style="Muted.TLabel", wraplength=330).pack(anchor="w")
            ttk.Label(self.opts, text="Backup folder", style="Card.TLabel").pack(anchor="w", pady=(12, 3))
            ttk.Label(self.opts, text=BACKUP_DIR, style="Muted.TLabel", wraplength=330).pack(anchor="w")
        elif a == "Restore":
            ttk.Label(self.opts, text="Backup file", style="Card.TLabel").pack(anchor="w", pady=(0, 3))
            row = ttk.Frame(self.opts, style="Card.TFrame")
            row.pack(fill="x")
            self.rfile = tk.StringVar(value=self._latest_dump())
            self.rcombo = ttk.Combobox(row, textvariable=self.rfile, values=self._dumps())
            self.rcombo.pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Browse", style="Ghost.TButton",
                       command=self.browse).pack(side="left", padx=(8, 0))
            self.rdb = tk.StringVar(value="testdb")
            self._field("Local database name", self.rdb)
            self.rpw = tk.StringVar()
            self._field("Ubuntu password (for local PostgreSQL)", self.rpw, show="•")
            ttk.Label(self.opts, text="Restores only the public schema into LOCAL PostgreSQL. "
                      "The target database is dropped and recreated.",
                      style="Muted.TLabel", wraplength=330).pack(anchor="w", pady=(12, 0))
        elif a == "Crontab job":
            ttk.Label(self.opts, text="Preset", style="Card.TLabel").pack(anchor="w", pady=(0, 3))
            self.preset = tk.StringVar(value="Daily at 2:00 AM")
            pc = ttk.Combobox(self.opts, textvariable=self.preset, values=list(PRESETS), state="readonly")
            pc.pack(fill="x")
            pc.bind("<<ComboboxSelected>>", lambda e: self._apply_preset())
            grid = ttk.Frame(self.opts, style="Card.TFrame")
            grid.pack(fill="x", pady=(12, 0))
            self.cron_vars = []
            for i, (name, default) in enumerate((("Minute", "0"), ("Hour", "2"), ("Day of\nmonth", "*"),
                                                 ("Month", "*"), ("Day of\nweek", "*"))):
                grid.columnconfigure(i, weight=1)
                ttk.Label(grid, text=name, style="Muted.TLabel", justify="center").grid(row=0, column=i)
                v = tk.StringVar(value=default)
                v.trace_add("write", lambda *a: self._cron_preview())
                ttk.Entry(grid, textvariable=v, width=5, justify="center").grid(
                    row=1, column=i, padx=3, pady=(3, 0), sticky="ew")
                self.cron_vars.append(v)
            ttk.Label(self.opts, text="Allowed: *  */5  7  1-5  1,15", style="Muted.TLabel").pack(
                anchor="w", pady=(8, 0))
            ttk.Label(self.opts, text="Resulting line", style="Card.TLabel").pack(anchor="w", pady=(12, 3))
            self.cron_prev = tk.Label(self.opts, text="", bg="#eef2f8", fg=NAVY, justify="left",
                                      anchor="w", wraplength=330, font=("Ubuntu Mono", 9), padx=8, pady=8)
            self.cron_prev.pack(fill="x")
            self._cron_preview()
        elif a == "Settings":
            self.set_url = tk.StringVar(value=DB_URL)
            self.set_script = tk.StringVar(value=BACKUP_SCRIPT)
            self.set_dir = tk.StringVar(value=BACKUP_DIR)
            self._field("Connection string", self.set_url, show="\u2022")
            self.url_entry = self.opts.winfo_children()[-1]
            self.show_url = tk.BooleanVar(value=False)
            ttk.Checkbutton(self.opts, text="Show connection string", variable=self.show_url,
                            command=lambda: self.url_entry.config(show="" if self.show_url.get() else "\u2022")
                            ).pack(anchor="w", pady=(4, 0))
            ttk.Label(self.opts, text="Backup script", style="Card.TLabel").pack(anchor="w", pady=(10, 3))
            r1 = ttk.Frame(self.opts, style="Card.TFrame")
            r1.pack(fill="x")
            ttk.Entry(r1, textvariable=self.set_script).pack(side="left", fill="x", expand=True)
            ttk.Button(r1, text="Browse", style="Ghost.TButton",
                       command=lambda: self._browse_into(self.set_script, False)).pack(side="left", padx=(8, 0))
            ttk.Label(self.opts, text="Backup folder", style="Card.TLabel").pack(anchor="w", pady=(10, 3))
            r2 = ttk.Frame(self.opts, style="Card.TFrame")
            r2.pack(fill="x")
            ttk.Entry(r2, textvariable=self.set_dir).pack(side="left", fill="x", expand=True)
            ttk.Button(r2, text="Browse", style="Ghost.TButton",
                       command=lambda: self._browse_into(self.set_dir, True)).pack(side="left", padx=(8, 0))
            ttk.Button(self.opts, text="\u270E  Edit backup script text...", style="Ghost.TButton",
                       command=self.edit_script).pack(fill="x", pady=(16, 0))
        elif a == "Users":
            ttk.Label(self.opts, text="Accounts (double-click to edit access)", style="Card.TLabel").pack(anchor="w", pady=(0, 6))
            tw = tk.Frame(self.opts, bg=BORDER)
            tw.pack(fill="x")
            self.utree = ttk.Treeview(tw, columns=("user", "role", "perm"), show="headings", height=7, selectmode="browse")
            for col, text, w in (("user", "User", 130), ("role", "Role", 110), ("perm", "Permissions", 90)):
                self.utree.heading(col, text=text)
                self.utree.column(col, width=w, anchor="w" if col != "perm" else "center", stretch=(col == "user"))
            self.utree.pack(fill="x", padx=1, pady=1)
            self.utree.bind("<Double-1>", lambda e: self.user_edit())
            grid = ttk.Frame(self.opts, style="Card.TFrame")
            grid.pack(fill="x", pady=(10, 0))
            for i, (text, cmd) in enumerate((("Edit access", self.user_edit), ("Reset password", self.user_reset_pw),
                                             ("Delete user", self.user_delete), ("Activity log", self.show_audit))):
                grid.columnconfigure(i % 2, weight=1)
                ttk.Button(grid, text=text, style="Ghost.TButton", command=cmd).grid(
                    row=i // 2, column=i % 2, sticky="ew", padx=3, pady=3)
            self._fill_users()
        elif a == "My account":
            ttk.Label(self.opts, text="Signed in as", style="Card.TLabel").pack(anchor="w")
            ttk.Label(self.opts, text=f"{self.current_user or '-'}  \u2022  {Auth.role(self.current_user) if self.current_user else ''}",
                      style="Section.TLabel").pack(anchor="w", pady=(2, 10))
            ttk.Label(self.opts, text="You can", style="Card.TLabel").pack(anchor="w")
            for k, label in PERMS.items():
                ok = k in self.perms
                ttk.Label(self.opts, text=("\u2714  " if ok else "\u2716  ") + label,
                          style="Card.TLabel" if ok else "Muted.TLabel").pack(anchor="w", pady=1)
        else:
            ttk.Label(self.opts, text="Show the scheduled jobs for your user (crontab -l).",
                      style="Card.TLabel", wraplength=320).pack(anchor="w")
        self.run_btn.config(text={"Backup": "▶  Run backup", "Restore": "↺  Restore database",
                                  "Crontab job": "✓  Apply schedule",
                                  "Crontab list": "☰  Show crontab",
                                  "Settings": "\u2713  Save settings",
                                  "Users": "\uFF0B  Add user",
                                  "My account": "\U0001F511  Change password"}[a])

    def _browse_into(self, var, folder):
        start = var.get() if os.path.exists(var.get()) else BASE_DIR
        p = (filedialog.askdirectory(initialdir=start) if folder
             else filedialog.askopenfilename(initialdir=os.path.dirname(start) or BASE_DIR))
        if p:
            var.set(p)

    def edit_script(self):
        """Open the backup script in a small built-in text editor."""
        path = self.set_script.get().strip() if hasattr(self, "set_script") else BACKUP_SCRIPT
        try:
            with open(path) as f:
                content = f.read()
        except OSError as e:
            return messagebox.showerror("Edit script", f"Cannot open:\n{path}\n\n{e}")
        win = tk.Toplevel(self)
        win.title(f"Edit - {os.path.basename(path)}")
        win.geometry("820x560")
        win.configure(bg=BG)
        win.transient(self)
        txt = tk.Text(win, font=("Ubuntu Mono", 10), wrap="none", undo=True, relief="flat",
                      bg="#ffffff", fg=TEXT, padx=10, pady=8)
        ysb = ttk.Scrollbar(win, command=txt.yview)
        txt.configure(yscrollcommand=ysb.set)
        bar = ttk.Frame(win)
        bar.pack(side="bottom", fill="x", padx=12, pady=10)
        ttk.Label(bar, text=path, foreground=MUTED).pack(side="left")

        def save():
            try:
                with open(path, "w") as f:
                    f.write(txt.get("1.0", "end-1c") + "\n" if not txt.get("1.0", "end-1c").endswith("\n")
                            else txt.get("1.0", "end-1c"))
                os.chmod(path, 0o755)
            except OSError as e:
                return messagebox.showerror("Save", str(e))
            self.log(f"Saved script: {path}", "ok")
            win.destroy()
        ttk.Button(bar, text="Save", style="Accent.TButton", command=save).pack(side="right")
        ttk.Button(bar, text="Cancel", style="Ghost.TButton", command=win.destroy).pack(side="right", padx=8)
        ysb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", content)
        txt.edit_reset()

    def _on_pick(self):
        self.on_action_change()
        self.refresh_backups()

    def _apply_preset(self):
        vals = PRESETS.get(self.preset.get())
        if vals:
            for v, x in zip(self.cron_vars, vals):
                v.set(x)

    def _cron_line(self):
        f = [v.get().strip() or d for v, d in zip(self.cron_vars, ("0", "2", "*", "*", "*"))]
        return " ".join(f) + f" {BACKUP_SCRIPT} >> {LOG_FILE} 2>&1", f

    def _cron_preview(self):
        if hasattr(self, "cron_prev") and self.cron_prev.winfo_exists():
            self.cron_prev.config(text=self._cron_line()[0])

    def _dumps(self):
        try:
            fs = [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".dump")]
            return sorted(fs, reverse=True)
        except OSError:
            return []

    def refresh_backups(self, highlight_new=False):
        """Refresh the single Backups table. Files not seen before are marked as new."""
        files = []
        for p in self._dumps():
            try:
                st = os.stat(p)
                files.append((st.st_mtime, st.st_size, p))
            except OSError:
                pass
        files.sort(reverse=True)
        known = getattr(self, "_known", None)
        self.tree.delete(*self.tree.get_children())
        for i, (mt, size, p) in enumerate(files, 1):
            tags = ()
            if highlight_new and known is not None and p not in known:
                tags = ("new",)
            elif i == 1:
                tags = ("latest",)
            when = datetime.fromtimestamp(mt).strftime("%d %b %H:%M")
            self.tree.insert("", "end", iid=p, tags=tags,
                             values=(i, os.path.basename(p), f"{size / 1048576:.1f} MB", when))
        self._known = {p for _, _, p in files}
        total = sum(f[1] for f in files) / 1048576
        self.bk_summary.config(text=f"{len(files)} file(s) \u2022 {total:.1f} MB \u2022 {BACKUP_DIR}"
                               if files else f"No backups yet \u2022 {BACKUP_DIR}")

    # ---------------------------------------------------- delete old backups
    def _backup_files(self):
        out = []
        for p in self._dumps():
            try:
                st = os.stat(p)
                out.append((st.st_mtime, st.st_size, p))
            except OSError:
                pass
        return sorted(out, reverse=True)          # newest first

    def _can_delete(self):
        if "backup_delete" not in self.perms:
            Auth.audit(self.current_user, "DENIED: delete backups")
            messagebox.showerror("Access denied", "Your account is not allowed to delete backups.")
            return False
        if self.busy:
            messagebox.showwarning("Delete", "A task is running. Try again when it finishes.")
            return False
        return True

    def _remove_files(self, paths):
        done, freed, failed = 0, 0, []
        for p in paths:
            try:
                size = os.path.getsize(p)
                os.remove(p)
                done, freed = done + 1, freed + size
                Auth.audit(self.current_user, f"deleted backup {os.path.basename(p)}")
            except OSError as e:
                failed.append(f"{os.path.basename(p)}: {e}")
        self.refresh_backups()
        self.log(f"\U0001F5D1 Deleted {done} backup file(s), freed {freed / 1048576:.1f} MB.", "warn")
        for f in failed:
            self.log(f"\u2718 {f}", "err")

    def delete_selected(self):
        if not self._can_delete():
            return
        paths = list(self.tree.selection())
        if not paths:
            return messagebox.showinfo("Delete", "Select one or more backups in the list first.")
        newest = (self._backup_files() or [(0, 0, "")])[0][2]
        names = "\n".join("  " + os.path.basename(p) for p in paths[:8]) + ("\n  ..." if len(paths) > 8 else "")
        extra = "\n\nThis includes the NEWEST backup." if newest in paths else ""
        if messagebox.askyesno("Delete backups", f"Permanently delete {len(paths)} file(s)?\n\n{names}{extra}\n\nThis cannot be undone."):
            self._remove_files(paths)

    def cleanup_dialog(self):
        """Delete backups by age or keep only the newest N. The newest backup is always kept."""
        if not self._can_delete():
            return
        win, body = self._modal("Clean up old backups")
        mode, days, keep = tk.StringVar(value="age"), tk.StringVar(value="30"), tk.StringVar(value="7")
        ttk.Label(body, text="Choose which backups to remove", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        r1 = ttk.Frame(body, style="Card.TFrame")
        r1.pack(fill="x", pady=3)
        ttk.Radiobutton(r1, text="Older than", variable=mode, value="age").pack(side="left")
        ttk.Spinbox(r1, from_=1, to=3650, textvariable=days, width=6).pack(side="left", padx=6)
        ttk.Label(r1, text="days", style="Card.TLabel").pack(side="left")
        r2 = ttk.Frame(body, style="Card.TFrame")
        r2.pack(fill="x", pady=3)
        ttk.Radiobutton(r2, text="Keep only the newest", variable=mode, value="count").pack(side="left")
        ttk.Spinbox(r2, from_=1, to=999, textvariable=keep, width=6).pack(side="left", padx=6)
        ttk.Label(r2, text="backups", style="Card.TLabel").pack(side="left")
        ttk.Label(body, text="The newest backup is always kept.", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        summary = ttk.Label(body, text="", style="Card.TLabel")
        summary.pack(anchor="w")
        lb_wrap = tk.Frame(body, bg=BORDER)
        lb_wrap.pack(fill="x", pady=(6, 0))
        lb = tk.Listbox(lb_wrap, height=7, width=52, relief="flat", activestyle="none",
                        font=("Ubuntu Mono", 9), bg="#ffffff", fg=TEXT, selectbackground="#ffffff")
        lb.pack(fill="x", padx=1, pady=1)
        state = {"victims": []}
        btn = ttk.Button(body, text="Delete", style="Danger.TButton")

        def compute(*_):
            files = self._backup_files()
            try:
                if mode.get() == "age":
                    cutoff = time.time() - int(days.get()) * 86400
                    victims = [f for f in files[1:] if f[0] < cutoff]
                else:
                    victims = files[max(int(keep.get()), 1):]
            except ValueError:
                victims = []
            state["victims"] = [f[2] for f in victims]
            lb.delete(0, "end")
            for mt, size, p in victims:
                lb.insert("end", f"{os.path.basename(p):<34}{size / 1048576:>6.1f} MB  {datetime.fromtimestamp(mt):%d %b %Y}")
            mb = sum(f[1] for f in victims) / 1048576
            summary.config(text=f"{len(victims)} of {len(files)} backup(s) will be deleted ({mb:.1f} MB)"
                           if victims else "Nothing matches - no backups would be deleted.")
            btn.config(state="normal" if victims else "disabled", text=f"Delete {len(victims)} backup(s)" if victims else "Delete")
        for v in (mode, days, keep):
            v.trace_add("write", compute)
        compute()

        def go():
            n = len(state["victims"])
            if n and messagebox.askyesno("Confirm delete", f"Permanently delete {n} backup file(s)?\nThis cannot be undone.", parent=win):
                Auth.audit(self.current_user, f"cleanup: {mode.get()} rule, {n} file(s)")
                self._remove_files(state["victims"])
                win.destroy()
        btn.config(command=go)
        btn.pack(fill="x", pady=(12, 0))

    def _pick_backup(self):
        sel = self.tree.selection()
        if sel and hasattr(self, "rfile") and self.action.get() == "Restore":
            try:
                self.rfile.set(sel[0])
            except tk.TclError:
                pass

    def _latest_dump(self):
        d = self._dumps()
        return d[0] if d else ""

    def browse(self):
        f = filedialog.askopenfilename(initialdir=BACKUP_DIR if os.path.isdir(BACKUP_DIR) else BASE_DIR,
                                       filetypes=[("Dump files", "*.dump"), ("All files", "*.*")])
        if f:
            self.rfile.set(f)

    # ----------------------------------------------------------------- output
    def log(self, text, tag=None):
        self.console.config(state="normal")
        self.console.insert("end", text + "\n", tag)
        self.console.see("end")
        self.console.config(state="disabled")

    def clear(self):
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

    def set_busy(self, busy, text):
        self.busy = busy
        self.run_btn.config(state="disabled" if busy else "normal")
        self.combo.config(state="disabled" if busy else "readonly")
        self.status.config(text=text)
        if busy:
            self.pb.pack(side="right", padx=20)
            self.pb.start(12)
        else:
            self.pb.stop()
            self.pb.pack_forget()

    def _drain(self):
        try:
            while True:
                kind, a, b = self.q.get_nowait()
                if kind == "log":
                    self.log(a, b)
                elif kind == "refresh":
                    self.refresh_backups(highlight_new=True)
                elif kind == "done":
                    self.set_busy(False, a)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    # ---------------------------------------------------------------- actions
    def run(self):
        if self.busy:
            return
        a = self.action.get()
        need = ACTION_PERM.get(a)
        if self.current_user is None or (need and need not in self.perms):
            Auth.audit(self.current_user, f"DENIED: {a}")
            return messagebox.showerror("Access denied", f"Your account is not allowed to use '{a}'.")
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log(f"\n[{stamp}] ── {a} ──", "info")
        if a in ("Backup", "Restore", "Crontab job", "Settings"):
            Auth.audit(self.current_user, f"started: {a}")
        if a == "Users":
            return self.user_add()
        if a == "My account":
            return self.change_password()
        if a == "Backup":
            self._start("Backing up...", self._job_backup)
        elif a == "Restore":
            f, db, pw = self.rfile.get().strip(), self.rdb.get().strip(), self.rpw.get()
            if not f or not os.path.isfile(f):
                return messagebox.showerror("Restore", "Please choose a valid .dump file.")
            if not re.fullmatch(r"\w+", db):
                return messagebox.showerror("Restore", "Database name: letters, numbers and _ only.")
            if not pw:
                return messagebox.showerror("Restore", "Enter your Ubuntu password.")
            if not messagebox.askyesno("Confirm restore",
                                       f"Restore\n{os.path.basename(f)}\ninto LOCAL database '{db}'?\n\n"
                                       f"'{db}' will be dropped and recreated."):
                return self.log("Cancelled.", "warn")
            self._start("Restoring...", lambda: self._job_restore(f, db, pw))
        elif a == "Crontab job":
            line, fields = self._cron_line()
            for val, lo, hi, name in zip(fields, (0, 0, 1, 1, 0), (59, 23, 31, 12, 7),
                                         ("Minute", "Hour", "Day of month", "Month", "Day of week")):
                if not valid_field(val, lo, hi):
                    return messagebox.showerror("Invalid value", f"{name}: '{val}' is not valid ({lo}-{hi}).")
            if not messagebox.askyesno("Confirm", f"Add this entry to your crontab?\n\n{line}\n\n"
                                       "Any existing backup-supabase entry is replaced."):
                return self.log("Cancelled.", "warn")
            self._start("Updating crontab...", lambda: self._job_cron(line))
        elif a == "Settings":
            url, script, folder = self.set_url.get().strip(), self.set_script.get().strip(), self.set_dir.get().strip()
            if not url.startswith(("postgresql://", "postgres://")):
                return messagebox.showerror("Settings", "Connection string must start with postgresql://")
            if not script or not folder:
                return messagebox.showerror("Settings", "Backup script and folder cannot be empty.")
            try:
                save_settings(script, folder, url)
            except OSError as e:
                return messagebox.showerror("Settings", str(e))
            self.log("\u2714 Settings saved.", "ok")
            self.log(f"  script : {script}", "dim")
            self.log(f"  folder : {folder}", "dim")
            self.refresh_backups()
        else:
            self._start("Reading crontab...", self._job_cron_list)

    def _start(self, text, fn):
        self.set_busy(True, text)
        threading.Thread(target=fn, daemon=True).start()

    def _emit(self, text, tag=None):
        self.q.put(("log", text, tag))

    def _exec(self, args, stdin=None, env_ok=True):
        """Run a command, stream output into the console, return exit code."""
        try:
            p = subprocess.Popen(args, stdin=subprocess.PIPE if stdin is not None else None,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        except FileNotFoundError as e:
            self._emit(f"Command not found: {e.filename}", "err")
            return 127
        if stdin is not None:
            try:
                p.stdin.write(stdin)
                p.stdin.close()
            except BrokenPipeError:
                pass
        for line in p.stdout:
            line = line.rstrip()
            low = line.lower()
            tag = "err" if ("error" in low or "failed" in low) else ("ok" if "backup ok" in low else None)
            self._emit(line, tag)
        return p.wait()

    def _job_backup(self):
        try:
            os.makedirs(os.path.dirname(URL_FILE), exist_ok=True)
            os.makedirs(BACKUP_DIR, exist_ok=True)
            with open(URL_FILE, "w") as f:
                f.write(DB_URL + "\n")
            os.chmod(URL_FILE, 0o600)
            self._emit(f"Saved connection string to {URL_FILE}", "dim")
            if not os.path.isfile(BACKUP_SCRIPT):
                self._emit(f"Cannot find {BACKUP_SCRIPT}", "err")
                return self.q.put(("done", "Backup failed", None))
            os.chmod(BACKUP_SCRIPT, 0o755)
            rc = self._exec([BACKUP_SCRIPT])
            if rc == 0:
                self._emit("✔ Backup completed successfully.", "ok")
                self.q.put(("refresh", None, None))
                self.q.put(("done", "Backup completed", None))
            else:
                self._emit(f"✘ Backup failed (exit code {rc}).", "err")
                self.q.put(("done", "Backup failed", None))
        except Exception as e:  # noqa
            self._emit(f"✘ {e}", "err")
            self.q.put(("done", "Backup failed", None))

    def _job_restore(self, f, db, pw):
        tmp = "/tmp/" + os.path.basename(f)
        try:
            subprocess.run(["cp", f, tmp], check=True)
            os.chmod(tmp, 0o644)
            pg = lambda *a: ["sudo", "-S", "-p", "", "-u", "postgres", *a]
            pwin = pw + "\n"
            steps = [("Dropping old database", pg("dropdb", "--if-exists", db)),
                     ("Creating database", pg("createdb", db)),
                     ("Restoring public schema", pg("pg_restore", "--no-owner", "--no-privileges",
                                                    "-n", "public", f"--dbname={db}", tmp))]
            rc_final = 0
            for i, (label, cmd) in enumerate(steps):
                self._emit(f"• {label}...", "dim")
                rc = self._exec(cmd, stdin=pwin)
                if i < 2 and rc != 0:
                    self._emit(f"✘ {label} failed (exit {rc}). Check the password / PostgreSQL.", "err")
                    return self.q.put(("done", "Restore failed", None))
                rc_final = rc
            self._emit("• Tables now in the database:", "dim")
            self._exec(pg("psql", "-d", db, "-c", r"\dt public.*"), stdin=pwin)
            if rc_final == 0:
                self._emit("✔ Restore completed successfully.", "ok")
            else:
                self._emit("⚠ Restore finished with some ignored errors (normal for Supabase dumps). "
                           "Verify your tables above.", "warn")
            self.q.put(("done", "Restore finished", None))
        except Exception as e:  # noqa
            self._emit(f"✘ {e}", "err")
            self.q.put(("done", "Restore failed", None))
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def _crontab_current(self):
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""

    def _job_cron(self, line):
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            keep = [l for l in self._crontab_current().splitlines() if BACKUP_SCRIPT not in l]
            new = "\n".join(keep + [line]) + "\n"
            r = subprocess.run(["crontab", "-"], input=new, text=True, capture_output=True)
            if r.returncode != 0:
                self._emit(r.stderr.strip() or "crontab failed", "err")
                return self.q.put(("done", "Crontab failed", None))
            self._emit("✔ Crontab updated. Current entries:", "ok")
            for l in self._crontab_current().splitlines():
                self._emit("  " + l)
            self.q.put(("done", "Crontab updated", None))
        except Exception as e:  # noqa
            self._emit(f"✘ {e}", "err")
            self.q.put(("done", "Crontab failed", None))

    def _job_cron_list(self):
        cur = self._crontab_current().strip()
        if cur:
            for l in cur.splitlines():
                self._emit(l)
        else:
            self._emit(f"(no crontab entries for this user)", "warn")
        self.q.put(("done", "Crontab listed", None))


if __name__ == "__main__":
    load_settings()
    App().mainloop()
