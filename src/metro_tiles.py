#!/usr/bin/env python3
"""Ubuntu Metro Tiles — Windows Phone style translucent desktop tile wall (GTK4 prototype).

Design baseline:
- Target platform: Ubuntu 24.04 LTS (GNOME 46 / GTK4 / Wayland)
- Flat, crisp 0px-radius tiles by default; floating elevation is an optional toggle.
"""

import datetime
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ubuntu-metro-tiles"
STATE_PATH = CONFIG_DIR / "state.json"

CELL = 80
GAP = 12
GRID_COLS = 6
WALL_WIDTH = GRID_COLS * CELL + (GRID_COLS - 1) * GAP

PALETTE = [
    ("blue", "钴蓝", (0, 120, 215)),
    ("teal", "深青", (0, 130, 153)),
    ("green", "祖母绿", (16, 124, 16)),
    ("orange", "琥珀橙", (216, 59, 1)),
    ("magenta", "品红", (180, 0, 158)),
    ("purple", "深紫", (92, 45, 145)),
    ("red", "猩红", (209, 52, 56)),
    ("glass-dark", "暗玻璃", (18, 20, 26)),
    ("glass-light", "浅玻璃", (255, 255, 255)),
]

SIZES = [
    ("1x1", "小 1×1", 1, 1),
    ("2x1", "扁 2×1", 2, 1),
    ("2x2", "中 2×2", 2, 2),
    ("4x2", "宽 4×2", 4, 2),
]

WEEKDAYS_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# Candidate desktop entries probed dynamically so the default wall matches installed apps.
APP_CANDIDATES = [
    ("vscode", "VS Code", "2x2", "blue", "vscode", ["code", "/usr/share/code/code"]),
    (
        "browser",
        "浏览器",
        "2x2",
        "orange",
        "google-chrome",
        ["google-chrome-stable", "google-chrome", "chromium", "firefox"],
    ),
    (
        "obsidian",
        "Obsidian",
        "2x2",
        "purple",
        "obsidian",
        ["obsidian", "/opt/Obsidian/obsidian"],
    ),
    ("terminal", "终端", "2x1", "glass-dark", "org.gnome.Terminal", ["gnome-terminal", "x-terminal-emulator"]),
    ("files", "文件", "2x2", "teal", "org.gnome.Nautilus", ["nautilus --new-window", "nautilus"]),
    (
        "settings",
        "系统设置",
        "2x1",
        "blue",
        "org.gnome.Settings",
        ["gnome-control-center"],
    ),
    (
        "wechat",
        "微信",
        "1x1",
        "green",
        "/usr/share/icons/hicolor/256x256/apps/wechat.png",
        ["wechat", "/usr/bin/wechat"],
    ),
    (
        "sysmon-app",
        "监视器",
        "1x1",
        "magenta",
        "org.gnome.SystemMonitor",
        ["gnome-system-monitor"],
    ),
]


def _resolve_command(candidates: list[str]) -> str | None:
    for entry in candidates:
        parts = shlex.split(entry)
        exe = parts[0]
        if exe.startswith("/"):
            if os.path.isfile(exe) and os.access(exe, os.X_OK):
                return entry
        elif shutil.which(exe):
            return entry
    return None


def build_default_state() -> dict:
    tiles = [
        {
            "id": "live-clock",
            "name": "时钟与日程",
            "kind": "clock",
            "size": "4x2",
            "color": "glass-dark",
            "icon": "preferences-system-time-symbolic",
            "cmd": "",
        },
        {
            "id": "live-sys",
            "name": "系统监控",
            "kind": "sysmon",
            "size": "2x2",
            "color": "teal",
            "icon": "utilities-system-monitor-symbolic",
            "cmd": "gnome-system-monitor",
        },
    ]

    for tile_id, name, size, color, icon, cmds in APP_CANDIDATES:
        resolved = _resolve_command(cmds)
        if resolved:
            if tile_id == "browser" and "firefox" in resolved:
                icon = "firefox"
            tiles.append(
                {
                    "id": tile_id,
                    "name": name,
                    "kind": "app",
                    "size": size,
                    "color": color,
                    "icon": icon,
                    "cmd": resolved,
                }
            )

    return {
        "opacity": 0.14,
        "uniform_wp_tint": True,
        "floating_effect": False,
        "tiles": tiles,
    }


def build_css(opacity: float, uniform_wp_tint: bool, floating_effect: bool) -> str:
    a = max(0.0, min(0.75, opacity))
    a_hover = min(0.85, a + 0.14)
    grad_normal = (
        "linear-gradient(145deg, rgba(255, 255, 255, 0.14) 0%, rgba(255, 255, 255, 0.02) 48%, rgba(0, 0, 0, 0.10) 100%)"
        if floating_effect
        else "none"
    )
    grad_hover = (
        "linear-gradient(145deg, rgba(255, 255, 255, 0.24) 0%, rgba(255, 255, 255, 0.05) 50%, rgba(0, 0, 0, 0.06) 100%)"
        if floating_effect
        else "none"
    )

    palette_rules = []
    for key, _label, (r, g, b) in PALETTE:
        if uniform_wp_tint:
            bg = f"rgba(12, 16, 24, {a:.2f})" if a > 0.005 else "transparent"
            bg_h = f"rgba(18, 24, 36, {a_hover:.2f})"
        elif key == "glass-light":
            bg = f"rgba(255, 255, 255, {a * 0.35:.2f})" if a > 0.005 else "transparent"
            bg_h = f"rgba(255, 255, 255, {min(0.45, a * 0.55 + 0.08):.2f})"
        else:
            bg = f"rgba({r}, {g}, {b}, {a:.2f})" if a > 0.005 else "transparent"
            bg_h = f"rgba({r}, {g}, {b}, {a_hover:.2f})"

        palette_rules.append(
            f"""
button.wp-tile.tile-color-{key} {{
    background-color: {bg};
    background-image: {grad_normal};
}}
button.wp-tile.tile-color-{key}:hover {{
    background-color: {bg_h};
    background-image: {grad_hover};
}}
button.swatch-{key} {{
    background-color: rgb({r}, {g}, {b});
    background-image: none;
    border: 1px solid rgba(255, 255, 255, 0.45);
    border-radius: 0px;
    min-width: 22px;
    min-height: 22px;
    padding: 0px;
}}
button.swatch-{key}.swatch-active {{
    border: 2px solid #ffffff;
}}
"""
        )

    tile_block = (
        """
button.wp-tile, button.wp-tile.flat {
    border-style: solid;
    border-width: 1px;
    border-top-color: rgba(255, 255, 255, 0.42);
    border-left-color: rgba(255, 255, 255, 0.28);
    border-right-color: rgba(255, 255, 255, 0.14);
    border-bottom-color: rgba(0, 0, 0, 0.36);
    border-radius: 0px;
    padding: 0px;
    margin-top: 4px;
    margin-bottom: 4px;
    color: #ffffff;
    box-shadow:
        0 8px 20px rgba(0, 0, 0, 0.46),
        0 2px 6px rgba(0, 0, 0, 0.30),
        inset 0 1px 0 rgba(255, 255, 255, 0.26);
    transition: all 140ms ease-out;
}
button.wp-tile:hover, button.wp-tile.flat:hover {
    border-width: 1px;
    border-top-color: rgba(255, 255, 255, 0.92);
    border-left-color: rgba(255, 255, 255, 0.72);
    border-right-color: rgba(255, 255, 255, 0.55);
    border-bottom-color: rgba(255, 255, 255, 0.45);
    margin-top: 0px;
    margin-bottom: 8px;
    box-shadow:
        0 16px 32px rgba(0, 0, 0, 0.62),
        0 6px 12px rgba(0, 0, 0, 0.38),
        inset 0 0 0 1px rgba(255, 255, 255, 0.48);
}
button.wp-tile:active, button.wp-tile.flat:active {
    margin-top: 6px;
    margin-bottom: 2px;
    box-shadow:
        0 3px 8px rgba(0, 0, 0, 0.42),
        inset 0 1px 0 rgba(255, 255, 255, 0.18);
}
button.wp-tile.selected, button.wp-tile.flat.selected {
    border: 1px solid #ffffff;
    box-shadow:
        0 10px 24px rgba(0, 0, 0, 0.52),
        inset 0 0 0 2px #00a8ff;
}
button.wp-tile image {
    -gtk-icon-shadow: 0 5px 12px rgba(0, 0, 0, 0.60);
}
"""
        if floating_effect
        else """
button.wp-tile, button.wp-tile.flat {
    border: 1px solid rgba(255, 255, 255, 0.30);
    border-radius: 0px;
    padding: 0px;
    margin-top: 4px;
    margin-bottom: 4px;
    color: #ffffff;
    box-shadow: none;
    transition: border-color 110ms ease, background-color 110ms ease, box-shadow 110ms ease;
}
button.wp-tile:hover, button.wp-tile.flat:hover {
    border: 1px solid rgba(255, 255, 255, 0.92);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.72);
}
button.wp-tile.selected, button.wp-tile.flat.selected {
    border: 1px solid #ffffff;
    box-shadow: inset 0 0 0 2px #00a8ff;
}
"""
    )

    return (
        """
window, window.background, window.csd, window.solid-csd, .transparent-root {
    background-color: transparent;
    background-image: none;
    box-shadow: none;
    border: none;
    border-radius: 0px;
    color: #ffffff;
}

.hud-bar {
    background-color: rgba(14, 16, 22, 0.62);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 0px;
    padding: 5px 8px;
}

.hud-title {
    font-size: 12px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.94);
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.75);
}

button.hud-btn {
    background-color: rgba(255, 255, 255, 0.10);
    background-image: none;
    color: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 0px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
    min-height: 24px;
}
button.hud-btn:hover {
    background-color: rgba(255, 255, 255, 0.22);
    border-color: rgba(255, 255, 255, 0.55);
}
button.hud-btn.active {
    background-color: rgba(0, 120, 215, 0.85);
    border-color: #ffffff;
}

button.hud-close {
    background-color: transparent;
    background-image: none;
    color: #ffffff;
    border: none;
    border-radius: 0px;
    min-width: 26px;
    min-height: 24px;
    padding: 0px;
    font-size: 14px;
    font-weight: 700;
}
button.hud-close:hover {
    background-color: #E81123;
}

scale.hud-scale trough {
    background-color: rgba(255, 255, 255, 0.22);
    border-radius: 0px;
    min-height: 4px;
}
scale.hud-scale highlight {
    background-color: #ffffff;
    border-radius: 0px;
}
scale.hud-scale slider {
    background-color: #ffffff;
    border-radius: 0px;
    min-width: 10px;
    min-height: 14px;
    margin: -5px 0;
}
"""
        + tile_block
        + """
.tile-label {
    font-size: 12px;
    font-weight: 600;
    color: #ffffff;
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.70);
}
.tile-sub {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.90);
    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.70);
}
.live-time {
    font-size: 36px;
    font-weight: 300;
    color: #ffffff;
    text-shadow: 0 1px 5px rgba(0, 0, 0, 0.65);
}
.live-time-compact {
    font-size: 20px;
    font-weight: 600;
    color: #ffffff;
    text-shadow: 0 1px 4px rgba(0, 0, 0, 0.65);
}

progressbar.wp-bar trough {
    background-color: rgba(0, 0, 0, 0.35);
    border-radius: 0px;
    min-height: 5px;
}
progressbar.wp-bar progress {
    background-color: #ffffff;
    border-radius: 0px;
    min-height: 5px;
}

.editor-strip {
    background-color: rgba(14, 16, 22, 0.88);
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 0px;
    padding: 7px 10px;
}
"""
        + "\n".join(palette_rules)
    )


def load_icon(icon_spec: str, px: int) -> Gtk.Widget:
    if icon_spec.startswith("/") and os.path.exists(icon_spec):
        img = Gtk.Image.new_from_file(icon_spec)
    else:
        img = Gtk.Image.new_from_icon_name(icon_spec)
    img.set_pixel_size(px)
    return img


def read_mem_percent() -> tuple[float, str]:
    info = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
    total = info.get("MemTotal", 1)
    avail = info.get("MemAvailable", 0)
    used = max(0, total - avail)
    pct = used / total * 100.0
    return pct, f"{used / (1024 * 1024):.1f}/{total / (1024 * 1024):.0f}G"


def read_cpu_times() -> tuple[int, int]:
    with open("/proc/stat", "r", encoding="utf-8") as f:
        nums = [int(x) for x in f.readline().split()[1:]]
    idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
    return idle, sum(nums)


def size_to_span(size_key: str) -> tuple[int, int]:
    for key, _label, w, h in SIZES:
        if key == size_key:
            return w, h
    return 2, 2


def pack_tiles(tiles: list[dict], cols: int = GRID_COLS) -> list[tuple[dict, int, int, int, int]]:
    occupied: set[tuple[int, int]] = set()
    placed = []
    for tile in tiles:
        w, h = size_to_span(tile["size"])
        w = min(w, cols)
        r = 0
        found = False
        while not found:
            for c in range(cols - w + 1):
                if all((r + dr, c + dc) not in occupied for dr in range(h) for dc in range(w)):
                    for dr in range(h):
                        for dc in range(w):
                            occupied.add((r + dr, c + dc))
                    placed.append((tile, c, r, w, h))
                    found = True
                    break
            if not found:
                r += 1
    return placed


class MetroTilesWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, provider: Gtk.CssProvider):
        super().__init__(application=app, title="Ubuntu Metro Tiles")
        self.provider = provider
        self.set_decorated(False)
        self.set_resizable(False)

        self.state = self._load_state()
        self.edit_mode = False
        self.selected_id: str | None = None
        self.prev_cpu = read_cpu_times()
        self.cpu_pct = 0.0
        self.mem_pct, self.mem_text = read_mem_percent()

        self.live_clock_widgets: list[tuple[str, Gtk.Label, Gtk.Label | None]] = []
        self.live_sys_widgets: list[
            tuple[str, Gtk.Label, Gtk.ProgressBar | None, Gtk.Label | None, Gtk.ProgressBar | None]
        ] = []

        self._apply_css()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.add_css_class("transparent-root")
        root.set_margin_top(16)
        root.set_margin_bottom(26)
        root.set_margin_start(22)
        root.set_margin_end(22)
        self.set_child(root)

        # Compact draggable HUD aligned to WALL_WIDTH
        handle = Gtk.WindowHandle()
        hud = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hud.add_css_class("hud-bar")
        hud.set_size_request(WALL_WIDTH, -1)
        hud.set_halign(Gtk.Align.START)
        handle.set_child(hud)
        root.append(handle)

        title = Gtk.Label(label="Metro 磁贴", xalign=0)
        title.add_css_class("hud-title")
        title.set_hexpand(True)
        hud.append(title)

        op_lbl = Gtk.Label(label="透度")
        op_lbl.add_css_class("tile-sub")
        hud.append(op_lbl)

        self.op_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.00, 0.75, 0.01)
        self.op_scale.add_css_class("hud-scale")
        self.op_scale.set_draw_value(False)
        self.op_scale.set_size_request(68, -1)
        self.op_scale.set_value(self.state["opacity"])
        self.op_scale.connect("value-changed", self._on_opacity_changed)
        hud.append(self.op_scale)

        self.float_btn = Gtk.Button(label="悬浮：开" if self.state["floating_effect"] else "悬浮：关")
        self.float_btn.add_css_class("hud-btn")
        if self.state["floating_effect"]:
            self.float_btn.add_css_class("active")
        self.float_btn.connect("clicked", self._on_toggle_floating)
        hud.append(self.float_btn)

        self.tint_btn = Gtk.Button(label="透玻璃" if self.state["uniform_wp_tint"] else "彩色透")
        self.tint_btn.add_css_class("hud-btn")
        if self.state["uniform_wp_tint"]:
            self.tint_btn.add_css_class("active")
        self.tint_btn.connect("clicked", self._on_toggle_tint)
        hud.append(self.tint_btn)

        self.edit_btn = Gtk.Button(label="编辑")
        self.edit_btn.add_css_class("hud-btn")
        self.edit_btn.connect("clicked", self._on_toggle_edit)
        hud.append(self.edit_btn)

        close_btn = Gtk.Button(label="×")
        close_btn.add_css_class("hud-close")
        close_btn.connect("clicked", lambda *_: self.close())
        hud.append(close_btn)

        # Transparent tile grid
        self.grid_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.grid_holder.add_css_class("transparent-root")
        self.grid_holder.set_halign(Gtk.Align.START)
        root.append(self.grid_holder)

        # Bottom inline editor bar
        self.editor_strip = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.editor_strip.add_css_class("editor-strip")
        self.editor_strip.set_size_request(WALL_WIDTH, -1)
        self.editor_strip.set_halign(Gtk.Align.START)
        self.editor_strip.set_visible(False)
        root.append(self.editor_strip)

        self._render_grid()

        GLib.timeout_add(1000, self._tick_clock)
        GLib.timeout_add(1500, self._tick_sysmon)
        self._tick_clock()
        self._tick_sysmon()

    def _load_state(self) -> dict:
        if STATE_PATH.exists():
            try:
                data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                data.setdefault("opacity", 0.14)
                data.setdefault("uniform_wp_tint", True)
                data.setdefault("floating_effect", False)
                if data.get("tiles"):
                    return data
            except Exception:
                pass
        return build_default_state()

    def _save_state(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _apply_css(self) -> None:
        css = build_css(
            self.state["opacity"],
            self.state["uniform_wp_tint"],
            self.state["floating_effect"],
        )
        self.provider.load_from_data(css.encode("utf-8"))

    def _on_opacity_changed(self, scale: Gtk.Scale) -> None:
        self.state["opacity"] = round(scale.get_value(), 2)
        self._apply_css()
        self._save_state()

    def _on_toggle_floating(self, *_args) -> None:
        self.state["floating_effect"] = not self.state["floating_effect"]
        if self.state["floating_effect"]:
            self.float_btn.set_label("悬浮：开")
            self.float_btn.add_css_class("active")
        else:
            self.float_btn.set_label("悬浮：关")
            self.float_btn.remove_css_class("active")
        self._apply_css()
        self._save_state()

    def _on_toggle_tint(self, *_args) -> None:
        self.state["uniform_wp_tint"] = not self.state["uniform_wp_tint"]
        if self.state["uniform_wp_tint"]:
            self.tint_btn.set_label("透玻璃")
            self.tint_btn.add_css_class("active")
        else:
            self.tint_btn.set_label("彩色透")
            self.tint_btn.remove_css_class("active")
        self._apply_css()
        self._save_state()

    def _on_toggle_edit(self, *_args) -> None:
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_btn.add_css_class("active")
            self.edit_btn.set_label("完成")
        else:
            self.edit_btn.remove_css_class("active")
            self.edit_btn.set_label("编辑")
            self.selected_id = None
            self.editor_strip.set_visible(False)
        self._render_grid()

    def _launch_cmd(self, cmd: str) -> None:
        if not cmd:
            return
        try:
            subprocess.Popen(shlex.split(cmd), start_new_session=True)
        except Exception:
            pass

    def _find_tile(self, tile_id: str | None) -> tuple[int, dict] | None:
        if not tile_id:
            return None
        for idx, t in enumerate(self.state["tiles"]):
            if t["id"] == tile_id:
                return idx, t
        return None

    def _select_tile(self, tile_id: str) -> None:
        self.selected_id = tile_id
        self._render_grid()
        self._render_editor()

    def _render_editor(self) -> None:
        while child := self.editor_strip.get_first_child():
            self.editor_strip.remove(child)
        found = self._find_tile(self.selected_id)
        if not found:
            self.editor_strip.set_visible(False)
            return
        idx, tile = found
        self.editor_strip.set_visible(True)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl = Gtk.Label(label=tile["name"], xalign=0)
        lbl.add_css_class("hud-title")
        lbl.set_hexpand(True)
        row1.append(lbl)

        for key, label, _w, _h in SIZES:
            btn = Gtk.Button(label=label)
            btn.add_css_class("hud-btn")
            if tile["size"] == key:
                btn.add_css_class("active")
            btn.connect("clicked", lambda _b, k=key: self._set_size(k))
            row1.append(btn)

        left_btn = Gtk.Button(label="←")
        left_btn.add_css_class("hud-btn")
        left_btn.set_sensitive(idx > 0)
        left_btn.connect("clicked", lambda *_: self._move(-1))
        row1.append(left_btn)

        right_btn = Gtk.Button(label="→")
        right_btn.add_css_class("hud-btn")
        right_btn.set_sensitive(idx < len(self.state["tiles"]) - 1)
        right_btn.connect("clicked", lambda *_: self._move(1))
        row1.append(right_btn)
        self.editor_strip.append(row1)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        color_lbl = Gtk.Label(label="配色")
        color_lbl.add_css_class("tile-sub")
        row2.append(color_lbl)
        for key, label, _rgb in PALETTE:
            btn = Gtk.Button()
            btn.add_css_class(f"swatch-{key}")
            if tile["color"] == key:
                btn.add_css_class("swatch-active")
            btn.set_tooltip_text(label)
            btn.connect("clicked", lambda _b, k=key: self._set_color(k))
            row2.append(btn)
        self.editor_strip.append(row2)

    def _set_size(self, size_key: str) -> None:
        found = self._find_tile(self.selected_id)
        if not found:
            return
        _, tile = found
        tile["size"] = size_key
        self._save_state()
        self._render_grid()
        self._render_editor()

    def _set_color(self, color_key: str) -> None:
        found = self._find_tile(self.selected_id)
        if not found:
            return
        _, tile = found
        tile["color"] = color_key
        if self.state["uniform_wp_tint"]:
            self.state["uniform_wp_tint"] = False
            self.tint_btn.set_label("彩色透")
            self.tint_btn.remove_css_class("active")
            self._apply_css()
        self._save_state()
        self._render_grid()
        self._render_editor()

    def _move(self, delta: int) -> None:
        found = self._find_tile(self.selected_id)
        if not found:
            return
        idx, _ = found
        tiles = self.state["tiles"]
        ni = idx + delta
        if 0 <= ni < len(tiles):
            tiles[idx], tiles[ni] = tiles[ni], tiles[idx]
            self._save_state()
            self._render_grid()
            self._render_editor()

    def _render_grid(self) -> None:
        while child := self.grid_holder.get_first_child():
            self.grid_holder.remove(child)
        self.live_clock_widgets.clear()
        self.live_sys_widgets.clear()

        grid = Gtk.Grid()
        grid.set_row_spacing(max(0, GAP - 8))
        grid.set_column_spacing(GAP)
        grid.set_row_homogeneous(True)
        grid.set_column_homogeneous(True)
        grid.set_size_request(WALL_WIDTH, -1)
        grid.add_css_class("transparent-root")

        for tile, col, row, w, h in pack_tiles(self.state["tiles"], GRID_COLS):
            grid.attach(self._build_tile(tile, w, h), col, row, w, h)

        self.grid_holder.append(grid)
        self._refresh_clock_labels()
        self._refresh_sysmon_labels()

    def _build_tile(self, tile: dict, w: int, h: int) -> Gtk.Button:
        btn = Gtk.Button()
        btn.add_css_class("flat")
        btn.add_css_class("wp-tile")
        btn.add_css_class(f"tile-color-{tile['color']}")
        if self.selected_id == tile["id"]:
            btn.add_css_class("selected")

        btn.set_size_request(w * CELL + (w - 1) * GAP, h * CELL + (h - 1) * GAP)
        btn.set_halign(Gtk.Align.FILL)
        btn.set_valign(Gtk.Align.FILL)

        kind = tile["kind"]
        size = tile["size"]
        if kind == "clock":
            btn.set_child(self._build_clock(size))
        elif kind == "sysmon":
            btn.set_child(self._build_sysmon(size))
        else:
            btn.set_child(self._build_app(tile, size))

        btn.connect("clicked", lambda _b, t=tile: self._on_left_click(t))

        rc = Gtk.GestureClick.new()
        rc.set_button(3)
        rc.connect("pressed", lambda _g, _n, _x, _y, tid=tile["id"]: self._select_tile(tid))
        btn.add_controller(rc)
        return btn

    def _on_left_click(self, tile: dict) -> None:
        if self.edit_mode:
            self._select_tile(tile["id"])
        else:
            self._launch_cmd(tile["cmd"])

    def _build_app(self, tile: dict, size: str) -> Gtk.Widget:
        if size == "1x1":
            box = Gtk.Box()
            box.set_halign(Gtk.Align.CENTER)
            box.set_valign(Gtk.Align.CENTER)
            box.append(load_icon(tile["icon"], 36))
            return box
        if size == "2x1":
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_start(12)
            box.set_margin_end(10)
            box.set_valign(Gtk.Align.CENTER)
            box.append(load_icon(tile["icon"], 32))
            lbl = Gtk.Label(label=tile["name"], xalign=0)
            lbl.add_css_class("tile-label")
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            box.append(lbl)
            return box

        ov = Gtk.Overlay()
        center = Gtk.Box()
        center.set_halign(Gtk.Align.CENTER)
        center.set_valign(Gtk.Align.CENTER)
        center.append(load_icon(tile["icon"], 52 if size == "2x2" else 60))
        ov.set_child(center)

        footer = Gtk.Label(label=tile["name"], xalign=0)
        footer.add_css_class("tile-label")
        footer.set_halign(Gtk.Align.START)
        footer.set_valign(Gtk.Align.END)
        footer.set_margin_start(10)
        footer.set_margin_bottom(8)
        ov.add_overlay(footer)
        return ov

    def _build_clock(self, size: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(14)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_margin_bottom(10)
        t_lbl = Gtk.Label(xalign=0)
        t_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        t_lbl.add_css_class("live-time" if size in ("4x2", "2x2") else "live-time-compact")
        box.append(t_lbl)
        s_lbl = None
        if size != "1x1":
            s_lbl = Gtk.Label(xalign=0)
            s_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            s_lbl.add_css_class("tile-sub")
            box.append(s_lbl)
        self.live_clock_widgets.append((size, t_lbl, s_lbl))
        return box

    def _build_sysmon(self, size: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(10)
        box.set_margin_bottom(10)

        cpu_lbl = Gtk.Label(xalign=0)
        cpu_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        cpu_lbl.add_css_class("tile-label" if size != "1x1" else "live-time-compact")
        box.append(cpu_lbl)

        cpu_bar = mem_lbl = mem_bar = None
        if size in ("2x2", "4x2"):
            cpu_bar = Gtk.ProgressBar()
            cpu_bar.add_css_class("wp-bar")
            box.append(cpu_bar)
            mem_lbl = Gtk.Label(xalign=0)
            mem_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            mem_lbl.add_css_class("tile-label")
            box.append(mem_lbl)
            mem_bar = Gtk.ProgressBar()
            mem_bar.add_css_class("wp-bar")
            box.append(mem_bar)
        elif size == "2x1":
            mem_lbl = Gtk.Label(xalign=0)
            mem_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            mem_lbl.add_css_class("tile-sub")
            box.append(mem_lbl)

        self.live_sys_widgets.append((size, cpu_lbl, cpu_bar, mem_lbl, mem_bar))
        return box

    def _refresh_clock_labels(self) -> None:
        now = datetime.datetime.now()
        wd = WEEKDAYS_ZH[now.weekday()]
        for size, t_lbl, s_lbl in self.live_clock_widgets:
            if size == "1x1":
                t_lbl.set_text(now.strftime("%H:%M"))
            elif size == "4x2":
                t_lbl.set_text(now.strftime("%H:%M:%S"))
                if s_lbl:
                    s_lbl.set_text(f"{now.strftime('%Y 年 %m 月 %d 日')} · {wd}")
            else:
                t_lbl.set_text(now.strftime("%H:%M"))
                if s_lbl:
                    s_lbl.set_text(f"{now.strftime('%m/%d')} {wd}")

    def _tick_clock(self) -> bool:
        self._refresh_clock_labels()
        return True

    def _refresh_sysmon_labels(self) -> None:
        for size, cpu_lbl, cpu_bar, mem_lbl, mem_bar in self.live_sys_widgets:
            if size == "1x1":
                cpu_lbl.set_text(f"{self.cpu_pct:.0f}%")
            elif size == "2x1":
                cpu_lbl.set_text(f"CPU {self.cpu_pct:.0f}%")
                if mem_lbl:
                    mem_lbl.set_text(f"内存 {self.mem_text}")
            else:
                cpu_lbl.set_text(f"CPU {self.cpu_pct:.0f}%")
                if cpu_bar:
                    cpu_bar.set_fraction(min(1.0, max(0.0, self.cpu_pct / 100.0)))
                if mem_lbl:
                    mem_lbl.set_text(f"内存 {self.mem_pct:.0f}% ({self.mem_text})")
                if mem_bar:
                    mem_bar.set_fraction(min(1.0, max(0.0, self.mem_pct / 100.0)))

    def _tick_sysmon(self) -> bool:
        cur = read_cpu_times()
        d_idle = cur[0] - self.prev_cpu[0]
        d_total = cur[1] - self.prev_cpu[1]
        self.prev_cpu = cur
        if d_total > 0:
            self.cpu_pct = (1.0 - d_idle / d_total) * 100.0
        self.mem_pct, self.mem_text = read_mem_percent()
        self._refresh_sysmon_labels()
        return True


class MetroTilesApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.wangzhefawang.UbuntuMetroTiles", flags=Gio.ApplicationFlags.NON_UNIQUE)

    def do_activate(self):
        provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
        )
        win = MetroTilesWindow(self, provider)
        win.present()


if __name__ == "__main__":
    MetroTilesApp().run([])
