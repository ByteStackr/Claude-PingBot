"""
Claude Ping Bot - GUI Version with System Tray
Pings Claude CLI every 15 minutes with random questions.
Logs Q&A to claude-answers.txt
"""

import os
import sys
import random
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from shutil import which
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# System tray support
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# Configuration
CLAUDE_EXE = "claude"
DEFAULT_MODEL = "haiku"
DEFAULT_INTERVAL = 15
REPLY_TIMEOUT_SECONDS = 120

MODELS = {
    "haiku": "Haiku (fastest)",
    "sonnet": "Sonnet (balanced)",
    "opus": "Opus (most capable)",
}

INTERVALS = [5, 15, 30, 60]

PROMPTS = [
    "Name any color",
    "Pick a planet",
    "Choose a season",
    "Say an animal",
    "Pick a programming language",
    "Name a fruit",
    "Name a country",
    "Pick a number between 1 and 100",
    "Name a musical instrument",
    "Pick a day of the week",
    "Name a vegetable",
    "Choose a month",
    "Name a sport",
    "Pick an ocean",
    "Name a bird",
]


def create_tray_icon_image():
    """Create a simple icon for the system tray"""
    size = 64
    image = Image.new('RGB', (size, size), color=(30, 30, 30))
    draw = ImageDraw.Draw(image)
    # Draw a simple "C" for Claude
    draw.ellipse([8, 8, 56, 56], outline=(100, 180, 255), width=8)
    draw.rectangle([40, 24, 56, 40], fill=(30, 30, 30))
    return image


class ClaudePingBot:
    def __init__(self, root):
        self.root = root
        self.root.title("Claude Ping Bot")
        self.root.geometry("500x400")
        self.root.resizable(True, True)

        # Get script directory for log files
        if getattr(sys, 'frozen', False):
            self.script_dir = Path(sys.executable).parent
        else:
            self.script_dir = Path(__file__).resolve().parent

        self.answers_path = self.script_dir / "claude-answers.txt"

        # State
        self.running = False
        self.bot_thread = None
        self.ping_count = 0
        self.tray_icon = None
        self.minimized_to_tray = False

        # Settings with tkinter variables
        self.current_model = tk.StringVar(value=DEFAULT_MODEL)
        self.interval_var = tk.StringVar(value=str(DEFAULT_INTERVAL))

        self.setup_menu()
        self.setup_ui()
        self.load_existing_answers()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_menu(self):
        """Setup the menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Start Bot", command=self.start_bot)
        file_menu.add_command(label="Stop Bot", command=self.stop_bot)
        file_menu.add_separator()

        # Minimize to Tray with checkmark
        self.tray_var = tk.BooleanVar(value=False)
        file_menu.add_checkbutton(
            label="Minimize to Tray",
            variable=self.tray_var,
            command=self.toggle_tray
        )
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.exit_app)

        # Options menu
        options_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Options", menu=options_menu)

        # Model submenu
        model_menu = tk.Menu(options_menu, tearoff=0)
        options_menu.add_cascade(label="Model", menu=model_menu)

        for model_key, model_label in MODELS.items():
            model_menu.add_radiobutton(
                label=model_label,
                variable=self.current_model,
                value=model_key,
                command=self.on_model_change
            )

        options_menu.add_separator()

        # Interval options
        for interval in INTERVALS:
            options_menu.add_radiobutton(
                label=f"Interval: {interval} min",
                variable=self.interval_var,
                value=str(interval),
                command=self.on_interval_change
            )

        # Actions menu
        actions_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Actions", menu=actions_menu)
        actions_menu.add_command(label="Ping Now", command=self.ping_now)
        actions_menu.add_separator()
        actions_menu.add_command(label="Clear Log Display", command=self.clear_log_display)
        actions_menu.add_command(label="Open Log File", command=self.open_log_file)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self.show_about)

    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="5")
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(status_frame, text="Stopped", foreground="red")
        self.status_label.pack(side=tk.LEFT, padx=5)

        self.ping_count_label = ttk.Label(status_frame, text="Pings: 0")
        self.ping_count_label.pack(side=tk.RIGHT, padx=5)

        self.next_ping_label = ttk.Label(status_frame, text="")
        self.next_ping_label.pack(side=tk.RIGHT, padx=20)

        # Model indicator
        self.model_label = ttk.Label(status_frame, text=f"Model: {self.current_model.get()}")
        self.model_label.pack(side=tk.RIGHT, padx=20)

        # Control frame
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        self.start_btn = ttk.Button(control_frame, text="Start", command=self.start_bot, width=12)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(control_frame, text="Stop", command=self.stop_bot, width=12, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.ping_now_btn = ttk.Button(control_frame, text="Ping Now", command=self.ping_now, width=12)
        self.ping_now_btn.pack(side=tk.LEFT, padx=5)

        tray_text = "To Tray" if TRAY_AVAILABLE else "Minimize"
        self.minimize_btn = ttk.Button(control_frame, text=tray_text, command=self.minimize_to_tray, width=12)
        self.minimize_btn.pack(side=tk.RIGHT, padx=5)

        # Interval setting
        interval_frame = ttk.Frame(main_frame)
        interval_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(interval_frame, text="Interval (minutes):").pack(side=tk.LEFT, padx=5)
        self.interval_entry = ttk.Entry(interval_frame, textvariable=self.interval_var, width=5)
        self.interval_entry.pack(side=tk.LEFT, padx=5)

        # Log display
        log_frame = ttk.LabelFrame(main_frame, text="Recent Q&A", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Bottom info
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(10, 0))

        self.file_label = ttk.Label(info_frame, text=f"Log: {self.answers_path}", foreground="gray")
        self.file_label.pack(side=tk.LEFT)

    def on_model_change(self):
        """Called when model is changed via menu"""
        self.model_label.config(text=f"Model: {self.current_model.get()}")

    def on_interval_change(self):
        """Called when interval is changed via menu"""
        # interval_var is already updated by radiobutton
        pass

    def toggle_tray(self):
        """Toggle minimize to tray state"""
        if self.tray_var.get():
            self.minimize_to_tray()
        else:
            self.restore_from_tray()

    def clear_log_display(self):
        """Clear the log text widget"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)

    def open_log_file(self):
        """Open the log file in default application"""
        if self.answers_path.exists():
            os.startfile(self.answers_path) if os.name == 'nt' else subprocess.run(['xdg-open', str(self.answers_path)])
        else:
            messagebox.showinfo("Info", "Log file does not exist yet.")

    def show_about(self):
        """Show about dialog"""
        messagebox.showinfo(
            "About Claude Ping Bot",
            "Claude Ping Bot v1.0\n\n"
            "Pings Claude CLI periodically with random questions.\n"
            "Logs Q&A to claude-answers.txt\n\n"
            "Uses Claude CLI with -p flag for non-interactive mode."
        )

    def exit_app(self):
        """Exit the application"""
        if self.running:
            if messagebox.askyesno("Confirm Exit", "Bot is running. Stop and exit?"):
                self.running = False
                if self.tray_icon:
                    self.tray_icon.stop()
                    self.tray_icon = None
                time.sleep(0.5)
                self.root.destroy()
        else:
            if self.tray_icon:
                self.tray_icon.stop()
                self.tray_icon = None
            self.root.destroy()

    def load_existing_answers(self):
        """Load existing answers from file"""
        if self.answers_path.exists():
            try:
                with open(self.answers_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    # Show last 20 entries
                    recent = lines[-20:] if len(lines) > 20 else lines
                    for line in recent:
                        self.append_log(line.strip(), save=False)
            except Exception:
                pass

    def append_log(self, message: str, save: bool = True):
        """Add message to log display and optionally save to file"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

        if save:
            with open(self.answers_path, "a", encoding="utf-8") as f:
                f.write(message + "\n")

    def run_single_ping(self) -> tuple[str, str]:
        """Execute a single ping and return (question, answer)"""
        prompt = random.choice(PROMPTS)
        full_prompt = f"{prompt} Respond with exactly one word."
        model = self.current_model.get()

        is_windows = os.name == "nt"

        if is_windows:
            cmd_str = f'claude -p "{full_prompt}" --model {model}'
            try:
                result = subprocess.run(
                    cmd_str,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=REPLY_TIMEOUT_SECONDS,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except subprocess.TimeoutExpired:
                return prompt, "TIMEOUT"
            except Exception as exc:
                return prompt, f"ERROR: {exc}"
        else:
            resolved_exe = which(CLAUDE_EXE) or CLAUDE_EXE
            cmd_list = [resolved_exe, "-p", full_prompt, "--model", model]
            try:
                result = subprocess.run(
                    cmd_list,
                    capture_output=True,
                    text=True,
                    timeout=REPLY_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                return prompt, "TIMEOUT"
            except Exception as exc:
                return prompt, f"ERROR: {exc}"

        if result.returncode == 0:
            stdout_clean = (result.stdout or "").strip()
            reply_lines = stdout_clean.split("\n")
            reply = reply_lines[-1] if reply_lines else stdout_clean
            return prompt, reply
        else:
            error_msg = (result.stderr or result.stdout or "").strip()
            return prompt, f"FAIL: {error_msg}"

    def do_ping(self):
        """Perform ping and update UI"""
        def set_pinging():
            self.status_label.config(text="Pinging...", foreground="orange")
        self.root.after(0, set_pinging)

        question, answer = self.run_single_ping()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] Q: {question} | A: {answer}"

        self.ping_count += 1

        def update_ui():
            self.append_log(log_entry)
            self.ping_count_label.config(text=f"Pings: {self.ping_count}")
            if self.running:
                self.status_label.config(text="Running", foreground="green")
            else:
                self.status_label.config(text="Stopped", foreground="red")

        self.root.after(0, update_ui)

    def bot_loop(self):
        """Main bot loop running in separate thread"""
        while self.running:
            self.do_ping()

            if not self.running:
                break

            # Get interval from UI
            try:
                interval_mins = int(self.interval_var.get())
            except ValueError:
                interval_mins = 15

            interval_secs = interval_mins * 60

            # Countdown with next ping time display
            end_time = time.time() + interval_secs
            while self.running and time.time() < end_time:
                remaining = int(end_time - time.time())
                mins, secs = divmod(remaining, 60)
                self.root.after(0, lambda m=mins, s=secs: self.next_ping_label.config(text=f"Next: {m:02d}:{s:02d}"))
                time.sleep(1)

        self.root.after(0, lambda: self.next_ping_label.config(text=""))

    def start_bot(self):
        """Start the bot"""
        if self.running:
            return

        self.running = True
        self.status_label.config(text="Running", foreground="green")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.interval_entry.config(state=tk.DISABLED)

        self.bot_thread = threading.Thread(target=self.bot_loop, daemon=True)
        self.bot_thread.start()

    def stop_bot(self):
        """Stop the bot"""
        self.running = False
        self.status_label.config(text="Stopping...", foreground="orange")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.interval_entry.config(state=tk.NORMAL)

        # Status will update to "Stopped" when loop exits
        self.root.after(1000, lambda: self.status_label.config(text="Stopped", foreground="red"))

    def ping_now(self):
        """Trigger immediate ping"""
        threading.Thread(target=self.do_ping, daemon=True).start()

    def minimize_to_tray(self):
        """Minimize to system tray"""
        if TRAY_AVAILABLE:
            self.root.withdraw()
            self.minimized_to_tray = True
            self.tray_var.set(True)
            self.create_tray_icon()
        else:
            self.root.iconify()

    def create_tray_icon(self):
        """Create system tray icon with menu"""
        if self.tray_icon is not None:
            return

        image = create_tray_icon_image()

        menu = pystray.Menu(
            pystray.MenuItem("Open", self.restore_from_tray, default=True),
            pystray.MenuItem("Ping Now", self.tray_ping_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Bot", self.tray_start_bot),
            pystray.MenuItem("Stop Bot", self.tray_stop_bot),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self.tray_exit)
        )

        self.tray_icon = pystray.Icon("ClaudePingBot", image, "Claude Ping Bot", menu)

        # Run tray icon in separate thread
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

    def restore_from_tray(self, icon=None, item=None):
        """Restore window from tray"""
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None

        self.minimized_to_tray = False
        self.tray_var.set(False)

        def restore():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

        self.root.after(0, restore)

    def tray_ping_now(self, icon=None, item=None):
        """Ping from tray menu"""
        threading.Thread(target=self.do_ping, daemon=True).start()

    def tray_start_bot(self, icon=None, item=None):
        """Start bot from tray menu"""
        self.root.after(0, self.start_bot)

    def tray_stop_bot(self, icon=None, item=None):
        """Stop bot from tray menu"""
        self.root.after(0, self.stop_bot)

    def tray_exit(self, icon=None, item=None):
        """Exit from tray"""
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.after(0, self.root.destroy)

    def on_close(self):
        """Handle window close - minimize to tray if running"""
        if self.running and TRAY_AVAILABLE:
            self.minimize_to_tray()
        elif self.running:
            if messagebox.askyesno("Confirm Exit", "Bot is running. Stop and exit?"):
                self.running = False
                time.sleep(0.5)
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    app = ClaudePingBot(root)
    root.mainloop()


if __name__ == "__main__":
    main()
