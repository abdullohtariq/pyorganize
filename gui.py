import flet as ft
import os
import io
import sys
import re
from collections import defaultdict
from pyorganize import FileOrganizer

def main(page: ft.Page):
    page.title = "PyOrganize"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#1f1f1f"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    def pick_folder_result(e: ft.FilePickerResultEvent):
        if e.path:
            folder_path.value = e.path
            picker_view.visible = False
            organizer_view.visible = True
            page.update()

    file_picker = ft.FilePicker(on_result=pick_folder_result)
    page.overlay.append(file_picker)

    folder_path = ft.Text()
    dry_run_data = defaultdict(list)

    def parse_dry_run_output(output):
        dry_run_data.clear()
        pattern = re.compile(r"\[Dry Run\] Would move: (.*) → (.*)")
        for line in output.splitlines():
            match = pattern.match(line)
            if match:
                file, folder = match.groups()
                dry_run_data[folder].append(file)

    def show_files_for_folder(folder_name):
        def back_to_folders(e):
            show_folder_list()

        file_list = ft.ListView(spacing=10, padding=20)
        for file_name in dry_run_data[folder_name]:
            file_list.controls.append(ft.Text(file_name))

        dry_run_content.content = ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=back_to_folders, tooltip="Back to folders"),
                ft.Text(f"Files in {folder_name}", weight=ft.FontWeight.BOLD),
            ]),
            file_list
        ])
        page.update()

    def show_folder_list():
        folder_list = ft.ListView(spacing=10, padding=20)
        for folder_name in sorted(dry_run_data.keys()):
            folder_list.controls.append(
                ft.ListTile(
                    title=ft.Text(folder_name),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    on_click=lambda _, fn=folder_name: show_files_for_folder(fn)
                )
            )
        dry_run_content.content = folder_list
        dry_run_content.visible = True
        page.update()

    def run_dry_run(e):
        path = folder_path.value
        if not path:
            return

        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()
        organizer = FileOrganizer(path, dry_run=True, verbose=False)
        organizer.organize()
        sys.stdout = old_stdout

        output = captured_output.getvalue()
        parse_dry_run_output(output)
        show_folder_list()

    def run_organize(e):
        path = folder_path.value
        if not path:
            return
        
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()
        organizer = FileOrganizer(path, dry_run=False, verbose=True)
        organizer.organize()
        sys.stdout = old_stdout

        output = captured_output.getvalue()
        dry_run_content.content = ft.Text(output)
        dry_run_content.visible = True
        page.update()

    def go_back(e):
        picker_view.visible = True
        organizer_view.visible = False
        dry_run_content.visible = False
        dry_run_content.content = None
        page.update()

    # --- Views ---
    picker_view = ft.Column(
        [
            ft.Text("Organize Your Folders", size=100, weight=ft.FontWeight.BOLD, color="#2196F3"),
            ft.Container(height=20),
            ft.ElevatedButton(
                "Browse Folder",
                icon=ft.Icons.FOLDER_OPEN,
                on_click=lambda _: file_picker.get_directory_path(),
                style=ft.ButtonStyle(
                    color="#ffffff", bgcolor="#2196F3", padding=30,
                    shape=ft.RoundedRectangleBorder(radius=20),
                )
            ),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=30,
    )

    dry_run_content = ft.Container(
        content=None,
        width=500,
        height=400,
        border=ft.border.all(1, "#2196F3"),
        border_radius=ft.border_radius.all(5),
        padding=20,
        visible=False,
    )

    organizer_view = ft.Column(
        [
            ft.Text("Selected Folder:", size=20),
            folder_path,
            ft.Row(
                [
                    ft.ElevatedButton("Go Back", on_click=go_back, icon=ft.Icons.ARROW_BACK),
                    ft.ElevatedButton("See the Dry Run", on_click=run_dry_run, icon=ft.Icons.VISIBILITY),
                    ft.ElevatedButton("Organize", on_click=run_organize, icon=ft.Icons.CHECK_CIRCLE),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=20
            ),
            ft.Container(height=20),
            dry_run_content,
        ],
        visible=False,
        alignment=ft.MainAxisAlignment.CENTER,
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=20
    )

    page.add(
        ft.Container(
            content=ft.Column([picker_view, organizer_view]),
            alignment=ft.alignment.center,
            expand=True,
        )
    )
    page.update()

if __name__ == "__main__":
    ft.app(target=main)