import asyncio
import inspect
import io
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import flet as ft

from ai_organizer import (
    AIContextCategorizer,
    PROVIDERS,
    load_config,
    save_config,
)
from pyorganize import FILE_MAP, HISTORY_FILENAME, FileOrganizer

# --- Theme Palette ---
BG_DARK = "#0B0F19"
SURFACE_CARD = "#111827"
SURFACE_ELEVATED = "#1E293B"
BORDER_SUBTLE = "#334155"
PRIMARY_ACCENT = "#6366F1"
SECONDARY_ACCENT = "#3B82F6"
SUCCESS_GREEN = "#10B981"
WARNING_AMBER = "#F59E0B"
ERROR_RED = "#EF4444"
TEXT_PRIMARY = "#F8FAFC"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#64748B"

PROVIDER_COLORS = {
    "gemini": "#3B82F6",
    "chatgpt": "#10B981",
    "deepseek": "#6366F1",
    "claude": "#F59E0B",
}


_Button = getattr(ft, "ElevatedButton", None) or ft.Button


def _border_all(width: float, color: str):
    if hasattr(ft, "Border") and hasattr(ft.Border, "all"):
        return ft.Border.all(width, color)
    return ft.border.all(width, color)


def _align_center():
    if hasattr(ft, "Alignment") and hasattr(ft.Alignment, "CENTER"):
        return ft.Alignment.CENTER
    return ft.alignment.center


def main(page: ft.Page):
    page.title = "PyOrganize — Smart & AI Context File Organizer"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = BG_DARK
    page.padding = 0
    if hasattr(page, "window") and page.window is not None:
        try:
            page.window.width = 1120
            page.window.height = 800
            page.window.min_width = 900
            page.window.min_height = 660
        except Exception:
            pass

    config = load_config()
    selected_path = {"value": ""}
    current_tab = {"value": "workspace"}  # "workspace" | "settings"
    include_unmatched_state = {"value": False}
    dry_run_data: Dict[str, List[dict]] = defaultdict(list)

    # Set up FilePicker compatibly across Flet versions
    file_picker = None
    try:
        sig = inspect.signature(ft.FilePicker.__init__)
        if "on_result" in sig.parameters:
            def _on_legacy_picker_result(e):
                if getattr(e, "path", None):
                    set_selected_folder(e.path)

            file_picker = ft.FilePicker(on_result=_on_legacy_picker_result)
            page.overlay.append(file_picker)
        else:
            file_picker = ft.FilePicker()
            if hasattr(page, "services"):
                page.services.append(file_picker)
            else:
                page.overlay.append(file_picker)
    except Exception:
        file_picker = None

    # --- UI State Controls ---
    status_banner_text = ft.Text(
        "Ready — Select a folder to preview or organize your files.",
        size=13,
        color=TEXT_SECONDARY,
    )
    status_banner_icon = ft.Icon(ft.Icons.INFO_OUTLINE, size=18, color=SECONDARY_ACCENT)
    progress_ring = ft.ProgressRing(width=16, height=16, stroke_width=2, color=PRIMARY_ACCENT, visible=False)

    status_bar = ft.Container(
        content=ft.Row(
            [
                progress_ring,
                status_banner_icon,
                status_banner_text,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=SURFACE_CARD,
        border=_border_all(1, BORDER_SUBTLE),
        border_radius=10,
        padding=ft.Padding(14, 10, 14, 10) if hasattr(ft, "Padding") else 12,
    )

    def set_status(message: str, kind: str = "info", busy: bool = False):
        progress_ring.visible = busy
        status_banner_text.value = message
        if kind == "success":
            status_banner_icon.name = ft.Icons.CHECK_CIRCLE_OUTLINE
            status_banner_icon.color = SUCCESS_GREEN
            status_banner_text.color = "#A7F3D0"
        elif kind == "error":
            status_banner_icon.name = ft.Icons.ERROR_OUTLINE
            status_banner_icon.color = ERROR_RED
            status_banner_text.color = "#FECACA"
        elif kind == "warning":
            status_banner_icon.name = ft.Icons.WARNING_AMBER_ROUNDED
            status_banner_icon.color = WARNING_AMBER
            status_banner_text.color = "#FDE68A"
        else:
            status_banner_icon.name = ft.Icons.AUTO_AWESOME if config.get("organization_mode") == "ai" else ft.Icons.INFO_OUTLINE
            status_banner_icon.color = PRIMARY_ACCENT if config.get("organization_mode") == "ai" else SECONDARY_ACCENT
            status_banner_text.color = TEXT_SECONDARY
        page.update()

    # --- Stat Cards ---
    stat_total_files = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
    stat_subfolders = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY)
    stat_categories = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=PRIMARY_ACCENT)
    stat_planned = ft.Text("0", size=24, weight=ft.FontWeight.BOLD, color=SUCCESS_GREEN)

    def make_stat_card(label: str, value_ctrl: ft.Text, icon_name, accent_color: str):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Container(
                        content=ft.Icon(icon_name, color=accent_color, size=22),
                        bgcolor=f"{accent_color}22",
                        border_radius=10,
                        padding=10,
                    ),
                    ft.Column(
                        [
                            ft.Text(label, size=12, color=TEXT_SECONDARY),
                            value_ctrl,
                        ],
                        spacing=2,
                    ),
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=SURFACE_CARD,
            border=_border_all(1, BORDER_SUBTLE),
            border_radius=12,
            padding=14,
            expand=True,
        )

    def refresh_folder_stats():
        path = selected_path["value"]
        if not path or not os.path.isdir(path):
            stat_total_files.value = "0"
            stat_subfolders.value = "0"
            return
        try:
            items = os.listdir(path)
            files_count = sum(
                1
                for x in items
                if x != HISTORY_FILENAME and not x.startswith(".") and os.path.isfile(os.path.join(path, x))
            )
            dirs_count = sum(1 for x in items if os.path.isdir(os.path.join(path, x)))
            stat_total_files.value = str(files_count)
            stat_subfolders.value = str(dirs_count)
        except Exception:
            stat_total_files.value = "0"
            stat_subfolders.value = "0"

    # --- Path Input & Quick Folder Chips ---
    path_input = ft.TextField(
        hint_text="Select or paste a folder path (e.g. C:\\Users\\You\\Downloads)...",
        bgcolor=SURFACE_ELEVATED,
        border_color=BORDER_SUBTLE,
        focused_border_color=PRIMARY_ACCENT,
        border_radius=10,
        color=TEXT_PRIMARY,
        text_size=14,
        expand=True,
    )

    def on_path_input_change(e):
        val = (path_input.value or "").strip()
        selected_path["value"] = val
        if os.path.isdir(val):
            refresh_folder_stats()
            undo_btn.disabled = not os.path.exists(os.path.join(val, HISTORY_FILENAME))
            set_status(f"Folder loaded: {val} ({stat_total_files.value} files found)", "info")
        else:
            page.update()

    path_input.on_change = on_path_input_change

    def set_selected_folder(path: str):
        if not path:
            return
        selected_path["value"] = path
        path_input.value = path
        refresh_folder_stats()
        stat_categories.value = "0"
        stat_planned.value = "0"
        undo_btn.disabled = not os.path.exists(os.path.join(path, HISTORY_FILENAME))
        render_empty_results()
        set_status(f"Selected folder: {path} ({stat_total_files.value} files ready)", "info")

    async def browse_folder_click(e):
        chosen = None
        if file_picker is not None:
            try:
                if inspect.iscoroutinefunction(file_picker.get_directory_path):
                    chosen = await file_picker.get_directory_path(dialog_title="Select Folder to Organize")
                else:
                    file_picker.get_directory_path(dialog_title="Select Folder to Organize")
                    return
            except Exception:
                chosen = None

        if not chosen:
            # Native Tkinter fallback if Flet desktop service didn't return a path
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                chosen = filedialog.askdirectory(title="Select Folder to Organize")
                root.destroy()
            except Exception:
                chosen = None

        if chosen:
            set_selected_folder(chosen)

    def make_quick_folder_btn(label: str, folder_path: Path, icon_name):
        return ft.Container(
            content=ft.Row(
                [
                    ft.Icon(icon_name, size=15, color=SECONDARY_ACCENT),
                    ft.Text(label, size=12, color=TEXT_PRIMARY, weight=ft.FontWeight.W_500),
                ],
                spacing=6,
                tight=True,
            ),
            bgcolor=SURFACE_ELEVATED,
            border=_border_all(1, BORDER_SUBTLE),
            border_radius=8,
            padding=ft.Padding(10, 6, 10, 6) if hasattr(ft, "Padding") else 8,
            on_click=lambda _: set_selected_folder(str(folder_path)) if folder_path.exists() else set_status(f"{folder_path} not found", "warning"),
            ink=True,
        )

    # --- Mode & AI Provider Controls ---
    custom_instructions_input = ft.TextField(
        label="Custom AI Sorting Instructions (Optional)",
        hint_text="e.g., Group by university subject, separate paid vs unpaid invoices, or group by project...",
        value=config.get("custom_instructions", ""),
        bgcolor=SURFACE_ELEVATED,
        border_color=BORDER_SUBTLE,
        focused_border_color=PRIMARY_ACCENT,
        border_radius=10,
        text_size=13,
        color=TEXT_PRIMARY,
        expand=True,
    )

    def on_custom_instructions_change(e):
        config["custom_instructions"] = custom_instructions_input.value or ""
        save_config(config)

    custom_instructions_input.on_change = on_custom_instructions_change

    provider_pills_row = ft.Row(spacing=10, wrap=True)
    ai_options_panel = ft.Container(visible=(config.get("organization_mode") == "ai"))
    mode_buttons_row = ft.Row(spacing=12)
    header_mode_badge = ft.Container()

    def update_header_badge():
        is_ai = config.get("organization_mode") == "ai"
        prov_key = config.get("active_provider", "gemini")
        prov_name = PROVIDERS.get(prov_key, {}).get("name", "AI")
        has_key = bool(config.get("api_keys", {}).get(prov_key, "").strip())

        if is_ai:
            badge_text = f"AI Context Mode • {prov_name}" + ("" if has_key else " (Key Needed)")
            badge_color = PRIMARY_ACCENT if has_key else WARNING_AMBER
            badge_icon = ft.Icons.AUTO_AWESOME
        else:
            badge_text = "Extension Mode • Fast Local Rules"
            badge_color = SECONDARY_ACCENT
            badge_icon = ft.Icons.CATEGORY_OUTLINED

        header_mode_badge.content = ft.Row(
            [
                ft.Icon(badge_icon, size=15, color=badge_color),
                ft.Text(badge_text, size=12, weight=ft.FontWeight.W_600, color=badge_color),
            ],
            spacing=6,
            tight=True,
        )
        header_mode_badge.bgcolor = f"{badge_color}1A"
        header_mode_badge.border = _border_all(1, f"{badge_color}55")
        header_mode_badge.border_radius = 20
        header_mode_badge.padding = ft.Padding(12, 6, 12, 6) if hasattr(ft, "Padding") else 8

    def select_mode(mode_name: str):
        config["organization_mode"] = mode_name
        save_config(config)
        ai_options_panel.visible = mode_name == "ai"
        rebuild_mode_selector()
        update_header_badge()
        if mode_name == "ai":
            prov = config.get("active_provider", "gemini")
            has_key = bool(config.get("api_keys", {}).get(prov, "").strip())
            if not has_key:
                set_status(
                    f"AI Context Mode selected — Add your {PROVIDERS[prov]['name']} API key in 'API Keys & AI' settings.",
                    "warning",
                )
            else:
                set_status(
                    f"AI Context Mode active — Using {PROVIDERS[prov]['name']} ({config['models'].get(prov)}) to organize by file content.",
                    "info",
                )
        else:
            set_status("Extension Mode active — Files will be organized rapidly by file extension.", "info")
        page.update()

    def select_active_provider(prov_key: str):
        config["active_provider"] = prov_key
        save_config(config)
        rebuild_provider_pills()
        update_header_badge()
        has_key = bool(config.get("api_keys", {}).get(prov_key, "").strip())
        if has_key:
            set_status(
                f"Switched AI provider to {PROVIDERS[prov_key]['name']} ({config['models'].get(prov_key)}).",
                "info",
            )
        else:
            set_status(
                f"Selected {PROVIDERS[prov_key]['name']} — Please enter your API key in the 'API Keys & AI' tab.",
                "warning",
            )
        page.update()

    def rebuild_mode_selector():
        is_ai = config.get("organization_mode") == "ai"

        def make_mode_card(title: str, subtitle: str, icon_name, selected: bool, target_mode: str, accent: str):
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(icon_name, color=accent if selected else TEXT_SECONDARY, size=22),
                            bgcolor=f"{accent}25" if selected else SURFACE_CARD,
                            border_radius=10,
                            padding=10,
                        ),
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            title,
                                            size=14,
                                            weight=ft.FontWeight.BOLD,
                                            color=TEXT_PRIMARY if selected else TEXT_SECONDARY,
                                        ),
                                        ft.Icon(
                                            ft.Icons.CHECK_CIRCLE if selected else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                            size=16,
                                            color=accent if selected else TEXT_MUTED,
                                        ),
                                    ],
                                     spacing=8,
                                ),
                                ft.Text(subtitle, size=12, color=TEXT_SECONDARY),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=12,
                ),
                bgcolor=f"{accent}15" if selected else SURFACE_ELEVATED,
                border=_border_all(2 if selected else 1, accent if selected else BORDER_SUBTLE),
                border_radius=12,
                padding=14,
                expand=True,
                on_click=lambda _: select_mode(target_mode),
                ink=True,
            )

        mode_buttons_row.controls = [
            make_mode_card(
                "By File Extension",
                "Fast rule-based sorting (.pdf → PDF Files, .jpg → Image Files, etc.)",
                ft.Icons.FOLDER_COPY_OUTLINED,
                not is_ai,
                "extension",
                SECONDARY_ACCENT,
            ),
            make_mode_card(
                "By File Context (AI Powered)",
                "Reads file content & metadata using Gemini, ChatGPT, DeepSeek, or Claude",
                ft.Icons.AUTO_AWESOME,
                is_ai,
                "ai",
                PRIMARY_ACCENT,
            ),
        ]

    def rebuild_provider_pills():
        active_prov = config.get("active_provider", "gemini")
        pills = []
        for prov_key, meta in PROVIDERS.items():
            is_selected = prov_key == active_prov
            has_key = bool(config.get("api_keys", {}).get(prov_key, "").strip())
            accent = PROVIDER_COLORS.get(prov_key, PRIMARY_ACCENT)

            pills.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(
                                ft.Icons.VERIFIED if has_key else ft.Icons.KEY_OFF_OUTLINED,
                                size=15,
                                color=SUCCESS_GREEN if has_key else WARNING_AMBER,
                            ),
                            ft.Text(
                                meta["name"],
                                size=13,
                                weight=ft.FontWeight.BOLD if is_selected else ft.FontWeight.W_500,
                                color=TEXT_PRIMARY if is_selected else TEXT_SECONDARY,
                            ),
                            ft.Text(
                                "Ready" if has_key else "No Key",
                                size=11,
                                color=SUCCESS_GREEN if has_key else WARNING_AMBER,
                            ),
                        ],
                        spacing=6,
                        tight=True,
                    ),
                    bgcolor=f"{accent}22" if is_selected else SURFACE_ELEVATED,
                    border=_border_all(2 if is_selected else 1, accent if is_selected else BORDER_SUBTLE),
                    border_radius=10,
                    padding=ft.Padding(12, 8, 12, 8) if hasattr(ft, "Padding") else 10,
                    on_click=lambda _, pk=prov_key: select_active_provider(pk),
                    ink=True,
                )
            )

        pills.append(
            ft.TextButton(
                "Configure API Keys →",
                icon=ft.Icons.KEY,
                on_click=lambda _: switch_tab("settings"),
            )
        )
        provider_pills_row.controls = pills

    ai_options_panel.content = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.PSYCHOLOGY, color=PRIMARY_ACCENT, size=20),
                        ft.Text("Active AI Provider:", size=13, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                        provider_pills_row,
                    ],
                    spacing=12,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                custom_instructions_input,
            ],
            spacing=12,
        ),
        bgcolor=SURFACE_CARD,
        border=_border_all(1, PRIMARY_ACCENT),
        border_radius=12,
        padding=16,
    )

    # --- Results Explorer Area ---
    results_container = ft.Container(
        bgcolor=SURFACE_CARD,
        border=_border_all(1, BORDER_SUBTLE),
        border_radius=14,
        padding=18,
        expand=True,
    )

    def render_empty_results():
        results_container.content = ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons. DRIVE_FILE_MOVE_OUTLINE, size=48, color=TEXT_MUTED),
                    ft.Text(
                        "Preview or Organize Your Files",
                        size=18,
                        weight=ft.FontWeight.BOLD,
                        color=TEXT_PRIMARY,
                    ),
                    ft.Text(
                        "Click 'Preview (Dry Run)' to inspect how files will be grouped before moving anything,\n"
                        "or click 'Organize Now' to sort your folder immediately.",
                        size=13,
                        color=TEXT_SECONDARY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            alignment=_align_center(),
            padding=40,
        )
        page.update()

    def show_files_for_folder(folder_name: str, is_dry_run: bool = True):
        items = dry_run_data.get(folder_name, [])
        file_rows = ft.ListView(spacing=8, expand=True)
        for item in items:
            fname = item["file"] if isinstance(item, dict) else str(item)
            reason = item.get("reason", "") if isinstance(item, dict) else ""
            file_rows.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.INSERT_DRIVE_FILE_OUTLINED, size=18, color=SECONDARY_ACCENT),
                            ft.Column(
                                [
                                    ft.Text(fname, size=14, weight=ft.FontWeight.W_600, color=TEXT_PRIMARY),
                                    ft.Text(reason, size=12, color=TEXT_SECONDARY) if reason else ft.Container(),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Container(
                                content=ft.Text(
                                    "Preview" if is_dry_run else "Moved",
                                    size=11,
                                    color=WARNING_AMBER if is_dry_run else SUCCESS_GREEN,
                                ),
                                bgcolor=f"{WARNING_AMBER if is_dry_run else SUCCESS_GREEN}20",
                                border_radius=6,
                                padding=ft.Padding(8, 4, 8, 4) if hasattr(ft, "Padding") else 6,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=SURFACE_ELEVATED,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=10,
                    padding=12,
                )
            )

        results_container.content = ft.Column(
            [
                ft.Row(
                    [
                        _Button(
                            "← All Categories",
                            on_click=lambda _: show_folder_list(is_dry_run=is_dry_run),
                            bgcolor=SURFACE_ELEVATED,
                            color=TEXT_PRIMARY,
                        ),
                        ft.Icon(ft.Icons.FOLDER_SPECIAL, color=PRIMARY_ACCENT, size=22),
                        ft.Text(
                            f"{folder_name} ({len(items)} file{'s' if len(items) != 1 else ''})",
                            size=16,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_PRIMARY,
                        ),
                    ],
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(color=BORDER_SUBTLE, height=1),
                file_rows,
            ],
            spacing=12,
            expand=True,
        )
        page.update()

    def show_folder_list(is_dry_run: bool = True):
        if not dry_run_data:
            results_container.content = ft.Container(
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=44, color=SUCCESS_GREEN),
                        ft.Text("No matching files needed moving.", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ft.Text(
                            "Either the folder is already organized or no matching files were found.",
                            size=13,
                            color=TEXT_SECONDARY,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                ),
                alignment=_align_center(),
                padding=35,
            )
            page.update()
            return

        cards_list = ft.ListView(spacing=10, expand=True)
        for folder_name in sorted(dry_run_data.keys()):
            files_in_cat = dry_run_data[folder_name]
            sample_names = ", ".join(
                (f["file"] if isinstance(f, dict) else str(f)) for f in files_in_cat[:4]
            )
            if len(files_in_cat) > 4:
                sample_names += f" +{len(files_in_cat) - 4} more"

            sample_reason = ""
            if files_in_cat and isinstance(files_in_cat[0], dict):
                sample_reason = files_in_cat[0].get("reason", "")

            cards_list.controls.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.FOLDER_OUTLINED, color=PRIMARY_ACCENT, size=24),
                                bgcolor=f"{PRIMARY_ACCENT}20",
                                border_radius=10,
                                padding=10,
                            ),
                            ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                folder_name,
                                                size=15,
                                                weight=ft.FontWeight.BOLD,
                                                color=TEXT_PRIMARY,
                                            ),
                                            ft.Container(
                                                content=ft.Text(
                                                    f"{len(files_in_cat)} file{'s' if len(files_in_cat) != 1 else ''}",
                                                    size=11,
                                                    weight=ft.FontWeight.W_600,
                                                    color=PRIMARY_ACCENT,
                                                ),
                                                bgcolor=f"{PRIMARY_ACCENT}22",
                                                border_radius=12,
                                                padding=ft.Padding(8, 3, 8, 3) if hasattr(ft, "Padding") else 5,
                                            ),
                                        ],
                                        spacing=10,
                                    ),
                                    ft.Text(sample_names, size=12, color=TEXT_SECONDARY),
                                    ft.Text(sample_reason, size=11, color=TEXT_MUTED, italic=True)
                                    if sample_reason
                                    else ft.Container(),
                                ],
                                spacing=3,
                                expand=True,
                            ),
                            ft.Icon(ft.Icons.CHEVRON_RIGHT, color=TEXT_SECONDARY),
                        ],
                        spacing=14,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=SURFACE_ELEVATED,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=12,
                    padding=14,
                    on_click=lambda _, fn=folder_name: show_files_for_folder(fn, is_dry_run=is_dry_run),
                    ink=True,
                )
            )

        title_prefix = "Dry Run Preview" if is_dry_run else "Organization Complete"
        badge_color = WARNING_AMBER if is_dry_run else SUCCESS_GREEN
        results_container.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.VISIBILITY_OUTLINED if is_dry_run else ft.Icons.TASK_ALT,
                            color=badge_color,
                            size=20,
                        ),
                        ft.Text(
                            f"{title_prefix} — {len(dry_run_data)} Destination Folder(s)",
                            size=15,
                            weight=ft.FontWeight.BOLD,
                            color=TEXT_PRIMARY,
                        ),
                        ft.Container(expand=True),
                        ft.Text("Click any folder to inspect files & AI context reasons", size=12, color=TEXT_SECONDARY),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(color=BORDER_SUBTLE, height=1),
                cards_list,
            ],
            spacing=10,
            expand=True,
        )
        page.update()

    # --- Execute Dry Run or Organize ---
    def execute_organization(dry_run: bool):
        path = (selected_path["value"] or path_input.value or "").strip()
        if not path or not os.path.isdir(path):
            set_status("Please select a valid folder first.", "error")
            return

        is_ai = config.get("organization_mode") == "ai"
        prov = config.get("active_provider", "gemini")
        api_key = config.get("api_keys", {}).get(prov, "").strip()
        model = config.get("models", {}).get(prov, PROVIDERS[prov]["default_model"])
        instructions = (custom_instructions_input.value or "").strip()

        if is_ai and not api_key:
            set_status(
                f"Missing API key for {PROVIDERS[prov]['name']}! Click 'API Keys & AI' at the top to enter your key.",
                "error",
            )
            return

        action_label = "Analyzing & previewing" if dry_run else "Organizing"
        mode_label = f"with {PROVIDERS[prov]['name']} AI context" if is_ai else "by file extension"
        set_status(f"{action_label} files {mode_label}...", "info", busy=True)

        try:
            old_stdout = sys.stdout
            sys.stdout = captured_output = io.StringIO()
            try:
                organizer = FileOrganizer(
                    path,
                    dry_run=dry_run,
                    verbose=True,
                    use_ai=is_ai,
                    ai_provider=prov if is_ai else None,
                    api_key=api_key if is_ai else None,
                    ai_model=model if is_ai else None,
                    custom_instructions=instructions,
                    include_unmatched=include_unmatched_state["value"],
                )
                results = organizer.organize()
            finally:
                sys.stdout = old_stdout

            dry_run_data.clear()
            for r in results:
                dry_run_data[r["folder"]].append(r)

            stat_categories.value = str(len(dry_run_data))
            stat_planned.value = str(organizer.moved_count)
            refresh_folder_stats()
            undo_btn.disabled = not os.path.exists(os.path.join(path, HISTORY_FILENAME))

            show_folder_list(is_dry_run=dry_run)
            if dry_run:
                set_status(
                    f"Preview ready: {organizer.moved_count} file(s) grouped into {len(dry_run_data)} folder(s). Click 'Organize Now' to apply.",
                    "success",
                    busy=False,
                )
            else:
                set_status(
                    f"Success! Moved {organizer.moved_count} file(s) into {len(dry_run_data)} folder(s).",
                    "success",
                    busy=False,
                )
        except Exception as ex:
            set_status(f"Error: {ex}", "error", busy=False)

    def handle_undo(e):
        path = (selected_path["value"] or path_input.value or "").strip()
        if not path or not os.path.isdir(path):
            set_status("Select a valid folder first.", "warning")
            return
        restored, msg = FileOrganizer.undo_last(path, verbose=False)
        refresh_folder_stats()
        dry_run_data.clear()
        stat_categories.value = "0"
        stat_planned.value = "0"
        undo_btn.disabled = not os.path.exists(os.path.join(path, HISTORY_FILENAME))
        render_empty_results()
        set_status(msg, "success" if restored > 0 else "warning")

    # --- Action Buttons ---
    preview_btn = _Button(
        "Preview (Dry Run)",
        icon=ft.Icons.VISIBILITY_OUTLINED,
        bgcolor=SURFACE_ELEVATED,
        color=TEXT_PRIMARY,
        on_click=lambda _: execute_organization(dry_run=True),
    )

    organize_btn = _Button(
        "Organize Now",
        icon=ft.Icons.ROCKET_LAUNCH,
        bgcolor=PRIMARY_ACCENT,
        color="#FFFFFF",
        on_click=lambda _: execute_organization(dry_run=False),
    )

    undo_btn = _Button(
        "Undo Last",
        icon=ft.Icons.UNDO,
        bgcolor=SURFACE_ELEVATED,
        color=TEXT_PRIMARY,
        disabled=True,
        on_click=handle_undo,
    )

    unmatched_switch = ft.Switch(
        label="Move unknown extensions to 'Uncategorized Files'",
        value=False,
        active_color=PRIMARY_ACCENT,
        on_change=lambda e: include_unmatched_state.__setitem__("value", bool(e.control.value)),
    )

    # --- API Keys & AI Settings View ---
    key_fields: Dict[str, ft.TextField] = {}
    model_dropdowns: Dict[str, ft.Dropdown] = {}
    test_status_texts: Dict[str, ft.Text] = {}

    def build_provider_settings_card(prov_key: str, meta: dict):
        accent = PROVIDER_COLORS.get(prov_key, PRIMARY_ACCENT)
        current_key = config.get("api_keys", {}).get(prov_key, "")
        current_model = config.get("models", {}).get(prov_key, meta["default_model"])

        tf = ft.TextField(
            label=f"{meta['name']} API Key",
            hint_text=f"Paste your {meta['name']} key ({meta['key_placeholder']})",
            value=current_key,
            password=True,
            can_reveal_password=True,
            bgcolor=SURFACE_ELEVATED,
            border_color=BORDER_SUBTLE,
            focused_border_color=accent,
            border_radius=10,
            text_size=13,
            color=TEXT_PRIMARY,
            expand=True,
        )
        key_fields[prov_key] = tf

        dd_options = [ft.dropdown.Option(m) for m in meta["models"]]
        dd = ft.Dropdown(
            label="Model",
            value=current_model if current_model in meta["models"] else meta["default_model"],
            options=dd_options,
            bgcolor=SURFACE_ELEVATED,
            border_color=BORDER_SUBTLE,
            border_radius=10,
            color=TEXT_PRIMARY,
            width=230,
        )
        model_dropdowns[prov_key] = dd

        status_txt = ft.Text(
            "Key saved" if current_key else "No key configured",
            size=12,
            color=SUCCESS_GREEN if current_key else TEXT_MUTED,
        )
        test_status_texts[prov_key] = status_txt

        def save_single_provider(pk=prov_key):
            config.setdefault("api_keys", {})[pk] = (key_fields[pk].value or "").strip()
            config.setdefault("models", {})[pk] = model_dropdowns[pk].value or PROVIDERS[pk]["default_model"]
            save_config(config)
            has_k = bool(config["api_keys"][pk])
            test_status_texts[pk].value = "Saved locally ✓" if has_k else "Cleared key"
            test_status_texts[pk].color = SUCCESS_GREEN if has_k else TEXT_MUTED
            rebuild_provider_pills()
            update_header_badge()
            page.update()

        def test_provider_click(e, pk=prov_key):
            save_single_provider(pk)
            k = config["api_keys"].get(pk, "")
            m = config["models"].get(pk, PROVIDERS[pk]["default_model"])
            if not k:
                test_status_texts[pk].value = "Please enter an API key first."
                test_status_texts[pk].color = WARNING_AMBER
                page.update()
                return
            test_status_texts[pk].value = f"Testing {PROVIDERS[pk]['name']} connection..."
            test_status_texts[pk].color = SECONDARY_ACCENT
            page.update()

            categorizer = AIContextCategorizer(provider=pk, api_key=k, model=m)
            ok, msg = categorizer.test_connection()
            test_status_texts[pk].value = msg
            test_status_texts[pk].color = SUCCESS_GREEN if ok else ERROR_RED
            page.update()

        def use_this_provider_click(e, pk=prov_key):
            save_single_provider(pk)
            config["active_provider"] = pk
            config["organization_mode"] = "ai"
            save_config(config)
            ai_options_panel.visible = True
            rebuild_mode_selector()
            rebuild_provider_pills()
            update_header_badge()
            switch_tab("workspace")
            set_status(f"Activated {PROVIDERS[pk]['name']} for AI Context Organization!", "success")

        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                content=ft.Icon(ft.Icons.AUTO_AWESOME, color=accent, size=20),
                                bgcolor=f"{accent}22",
                                border_radius=8,
                                padding=8,
                            ),
                            ft.Column(
                                [
                                    ft.Text(meta["name"], size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    ft.Text(f"Get API key: {meta['docs_url']}", size=11, color=TEXT_SECONDARY),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            _Button(
                                "Use for AI Sort",
                                icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                                bgcolor=accent,
                                color="#FFFFFF",
                                on_click=use_this_provider_click,
                            ),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        [
                            tf,
                            dd,
                        ],
                        spacing=12,
                    ),
                    ft.Row(
                        [
                            _Button(
                                "Save Key",
                                icon=ft.Icons.SAVE_OUTLINED,
                                bgcolor=SURFACE_ELEVATED,
                                color=TEXT_PRIMARY,
                                on_click=lambda _, pk=prov_key: save_single_provider(pk),
                            ),
                            _Button(
                                "Test API Key",
                                icon=ft.Icons.WIFI_TETHERING,
                                bgcolor=SURFACE_ELEVATED,
                                color=TEXT_PRIMARY,
                                on_click=test_provider_click,
                            ),
                            status_txt,
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=12,
            ),
            bgcolor=SURFACE_CARD,
            border=_border_all(1, BORDER_SUBTLE),
            border_radius=14,
            padding=18,
        )

    def save_all_keys_click(e):
        for pk in PROVIDERS:
            config.setdefault("api_keys", {})[pk] = (key_fields[pk].value or "").strip()
            config.setdefault("models", {})[pk] = model_dropdowns[pk].value or PROVIDERS[pk]["default_model"]
            has_k = bool(config["api_keys"][pk])
            test_status_texts[pk].value = "Saved ✓" if has_k else "No key configured"
            test_status_texts[pk].color = SUCCESS_GREEN if has_k else TEXT_MUTED
        save_config(config)
        rebuild_provider_pills()
        update_header_badge()
        set_status("All API keys and model preferences saved locally to ~/.pyorganize/config.json", "success")

    settings_view = ft.Container(
        content=ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Column(
                                [
                                    ft.Text(
                                        "AI Context Providers & API Keys",
                                        size=22,
                                        weight=ft.FontWeight.BOLD,
                                        color=TEXT_PRIMARY,
                                    ),
                                    ft.Text(
                                        "Provide your API key for Google Gemini, OpenAI ChatGPT, DeepSeek, or Anthropic Claude. "
                                        "PyOrganize will inspect file contents and organize files into smart contextual folders.",
                                        size=13,
                                        color=TEXT_SECONDARY,
                                    ),
                                ],
                                spacing=4,
                                expand=True,
                            ),
                            _Button(
                                "Save All Keys",
                                icon=ft.Icons.SAVE,
                                bgcolor=SUCCESS_GREEN,
                                color="#FFFFFF",
                                on_click=save_all_keys_click,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=SURFACE_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=14,
                    padding=18,
                ),
                ft.ListView(
                    controls=[build_provider_settings_card(pk, meta) for pk, meta in PROVIDERS.items()],
                    spacing=14,
                    expand=True,
                ),
            ],
            spacing=16,
            expand=True,
        ),
        visible=False,
        expand=True,
    )

    # --- Workspace View ---
    home_dir = Path.home()
    workspace_view = ft.Container(
        content=ft.Column(
            [
                # Folder Selection Card
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.Icons.FOLDER_OPEN, color=PRIMARY_ACCENT, size=22),
                                    ft.Text("Target Directory", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    ft.Container(expand=True),
                                    ft.Text("Quick Select:", size=12, color=TEXT_SECONDARY),
                                    make_quick_folder_btn("Downloads", home_dir / "Downloads", ft.Icons.DOWNLOAD),
                                    make_quick_folder_btn("Desktop", home_dir / "Desktop", ft.Icons.DESKTOP_WINDOWS),
                                    make_quick_folder_btn("Documents", home_dir / "Documents", ft.Icons.DESCRIPTION),
                                ],
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    path_input,
                                    _Button(
                                        "Browse Folder",
                                        icon=ft.Icons.CREATE_NEW_FOLDER_OUTLINED,
                                        bgcolor=PRIMARY_ACCENT,
                                        color="#FFFFFF",
                                        on_click=browse_folder_click,
                                    ),
                                ],
                                spacing=12,
                            ),
                        ],
                        spacing=12,
                    ),
                    bgcolor=SURFACE_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=14,
                    padding=16,
                ),
                # Organization Mode Selector
                mode_buttons_row,
                ai_options_panel,
                # Stats Row
                ft.Row(
                    [
                        make_stat_card("Files in Folder", stat_total_files, ft.Icons.INSERT_DRIVE_FILE, SECONDARY_ACCENT),
                        make_stat_card("Existing Subfolders", stat_subfolders, ft.Icons.FOLDER_SHARED, WARNING_AMBER),
                        make_stat_card("Target Categories", stat_categories, ft.Icons.CATEGORY, PRIMARY_ACCENT),
                        make_stat_card("Files Planned / Moved", stat_planned, ft.Icons.DRIVE_FILE_MOVE, SUCCESS_GREEN),
                    ],
                    spacing=12,
                ),
                # Action Bar
                ft.Container(
                    content=ft.Row(
                        [
                            preview_btn,
                            organize_btn,
                            undo_btn,
                            ft.Container(expand=True),
                            unmatched_switch,
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    bgcolor=SURFACE_CARD,
                    border=_border_all(1, BORDER_SUBTLE),
                    border_radius=12,
                    padding=12,
                ),
                # Results Explorer
                results_container,
            ],
            spacing=14,
            expand=True,
        ),
        visible=True,
        expand=True,
    )

    # --- Top Navigation Header ---
    tab_workspace_btn = _Button(
        "Workspace",
        icon=ft.Icons.DASHBOARD_OUTLINED,
        bgcolor=PRIMARY_ACCENT,
        color="#FFFFFF",
        on_click=lambda _: switch_tab("workspace"),
    )
    tab_settings_btn = _Button(
        "API Keys & AI",
        icon=ft.Icons.KEY,
        bgcolor=SURFACE_ELEVATED,
        color=TEXT_PRIMARY,
        on_click=lambda _: switch_tab("settings"),
    )

    def switch_tab(tab_name: str):
        current_tab["value"] = tab_name
        is_ws = tab_name == "workspace"
        workspace_view.visible = is_ws
        settings_view.visible = not is_ws
        tab_workspace_btn.bgcolor = PRIMARY_ACCENT if is_ws else SURFACE_ELEVATED
        tab_workspace_btn.color = "#FFFFFF" if is_ws else TEXT_PRIMARY
        tab_settings_btn.bgcolor = PRIMARY_ACCENT if not is_ws else SURFACE_ELEVATED
        tab_settings_btn.color = "#FFFFFF" if not is_ws else TEXT_PRIMARY
        page.update()

    top_header = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.AUTO_AWESOME_MOTION, color="#FFFFFF", size=22),
                            bgcolor=PRIMARY_ACCENT,
                            border_radius=10,
                            padding=8,
                        ),
                        ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text("PyOrganize", size=20, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                        ft.Container(
                                            content=ft.Text("v2.0 AI", size=11, weight=ft.FontWeight.BOLD, color=PRIMARY_ACCENT),
                                            bgcolor=f"{PRIMARY_ACCENT}22",
                                            border_radius=6,
                                            padding=ft.Padding(6, 2, 6, 2) if hasattr(ft, "Padding") else 4,
                                        ),
                                    ],
                                    spacing=8,
                                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                ft.Text(
                                    "Organize files by extension or AI content analysis (Gemini • ChatGPT • DeepSeek • Claude)",
                                    size=11,
                                    color=TEXT_SECONDARY,
                                ),
                            ],
                            spacing=1,
                        ),
                    ],
                    spacing=12,
                ),
                ft.Container(expand=True),
                header_mode_badge,
                tab_workspace_btn,
                tab_settings_btn,
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=SURFACE_CARD,
        border=_border_all(1, BORDER_SUBTLE),
        padding=ft.Padding(24, 14, 24, 14) if hasattr(ft, "Padding") else 16,
    )

    # Initialize components
    rebuild_mode_selector()
    rebuild_provider_pills()
    update_header_badge()
    render_empty_results()

    page.add(
        ft.Column(
            [
                top_header,
                ft.Container(
                    content=ft.Column(
                        [
                            workspace_view,
                            settings_view,
                            status_bar,
                        ],
                        spacing=12,
                        expand=True,
                    ),
                    padding=ft.Padding(24, 16, 24, 16) if hasattr(ft, "Padding") else 20,
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )
    )
    page.update()


def run_gui():
    ft.app(target=main)


if __name__ == "__main__":
    run_gui()
    run_gui()
