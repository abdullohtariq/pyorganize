# pyorganize - A Python CLI & GUI tool to organize files by extension or AI context
#
# 📁 Project Goal:
# Scan a directory and organize files either by their extensions into clean
# categorized subfolders OR using AI (Gemini, ChatGPT, DeepSeek, Claude)
# to inspect file contents and organize them by semantic context.

import argparse
import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ai_organizer import (
    AIContextCategorizer,
    PROVIDERS,
    extract_file_context,
    load_config,
)

HISTORY_FILENAME = ".pyorganize_history.json"

# 🔖 File Type Mapping (Extension Mode)
FILE_MAP: Dict[str, List[str]] = {
    # Documents
    "PDF Files": [".pdf"],
    "Word Files": [".doc", ".docx", ".odt"],
    "PowerPoint Files": [".ppt", ".pptx", ".odp", ".key"],
    "Excel Files": [".xls", ".xlsx", ".csv", ".tsv", ".ods"],
    "Text Files": [".txt", ".md", ".rtf", ".tex"],
    "Ebook Files": [".epub", ".mobi", ".azw3"],

    # Images
    "Image Files": [
        ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
        ".tiff", ".tif", ".svg", ".ico", ".heic", ".raw"
    ],

    # Videos
    "Video Files": [".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm", ".m4v"],

    # Audio
    "Audio Files": [".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"],

    # Archives & Installers
    "Software Files": [".exe", ".msi", ".apk", ".deb", ".rpm", ".dmg", ".pkg", ".appimage"],
    "Compressed Files": [".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".iso"],

    # Programming & Dev
    "Programming Files": [
        ".py", ".ipynb", ".java", ".cpp", ".c", ".h", ".hpp", ".cs", ".go", ".rs",
        ".html", ".htm", ".css", ".scss", ".js", ".ts", ".jsx", ".tsx", ".json",
        ".xml", ".yaml", ".yml", ".toml", ".ini", ".sql", ".sh", ".bat", ".ps1",
        ".php", ".rb", ".swift", ".kt", ".dart", ".lua", ".r"
    ],

    # Design & Fonts
    "Design Files": [".psd", ".ai", ".xd", ".fig", ".sketch", ".indd", ".blend"],
    "Font Files": [".ttf", ".otf", ".woff", ".woff2"],

    # Misc
    "Other Files": [".log", ".bak", ".tmp", ".torrent"],
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Organize your files by Extension or AI Content Context (Gemini, ChatGPT, DeepSeek, Claude)"
    )
    parser.add_argument("--path", type=str, required=True, help="Folder to scan and organize")
    parser.add_argument("--dry_run", "--dry-run", dest="dry_run", action="store_true", help="Preview changes without moving files")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output for each file")
    parser.add_argument("--ai", action="store_true", help="Organize files by context using AI instead of extension")
    parser.add_argument(
        "--provider",
        type=str,
        choices=list(PROVIDERS.keys()),
        default=None,
        help="AI provider to use (gemini, chatgpt, deepseek, claude)",
    )
    parser.add_argument("--api-key", dest="api_key", type=str, default=None, help="API key for the selected AI provider")
    parser.add_argument("--model", type=str, default=None, help="Optional model name override for the AI provider")
    parser.add_argument(
        "--instructions",
        type=str,
        default="",
        help="Optional custom instructions for AI context organization",
    )
    parser.add_argument("--undo", action="store_true", help="Undo the last organization performed in --path")
    return parser.parse_args()


class FileOrganizer:
    def __init__(
        self,
        path: str,
        dry_run: bool = False,
        verbose: bool = False,
        use_ai: bool = False,
        ai_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        ai_model: Optional[str] = None,
        custom_instructions: str = "",
        include_unmatched: bool = False,
    ):
        self.path = path
        self.dry_run = dry_run
        self.verbose = verbose
        self.use_ai = use_ai or bool(ai_provider and api_key)
        self.ai_provider = ai_provider
        self.api_key = api_key
        self.ai_model = ai_model
        self.custom_instructions = custom_instructions
        self.include_unmatched = include_unmatched

        self.moved_count = 0
        self.skipped_count = 0
        # Structured records: list of dicts with keys:
        # {"file": str, "folder": str, "reason": str, "src": str, "dest": str, "moved": bool}
        self.results: List[dict] = []

    @staticmethod
    def _resolve_unique_dest(destination_folder: str, filename: str, dry_run: bool) -> str:
        dest_path = os.path.join(destination_folder, filename)
        if dry_run:
            return dest_path
        base, extn = os.path.splitext(filename)
        counter = 1
        while os.path.exists(dest_path):
            new_name = f"{base}_{counter}{extn}"
            dest_path = os.path.join(destination_folder, new_name)
            counter += 1
        return dest_path

    def _execute_move(self, item: str, full_path: str, folder: str, reason: str = "") -> None:
        destination_folder = os.path.join(self.path, folder)
        if not self.dry_run:
            os.makedirs(destination_folder, exist_ok=True)
        dest_path = self._resolve_unique_dest(destination_folder, item, self.dry_run)

        if self.dry_run:
            print(f"[Dry Run] Would move: {item} → {folder}")
        else:
            os.makedirs(destination_folder, exist_ok=True)
            shutil.move(full_path, dest_path)
            if self.verbose:
                print(f"Moved: {item} → {folder}")

        self.moved_count += 1
        self.results.append(
            {
                "file": item,
                "folder": folder,
                "reason": reason or f"Matched category '{folder}'",
                "src": full_path,
                "dest": dest_path,
                "moved": not self.dry_run,
            }
        )

    def _save_history(self) -> None:
        if self.dry_run or not self.results:
            return
        history_path = os.path.join(self.path, HISTORY_FILENAME)
        payload = {
            "timestamp": datetime.now().isoformat(),
            "mode": "ai" if self.use_ai else "extension",
            "provider": self.ai_provider if self.use_ai else None,
            "moves": [
                {"file": r["file"], "folder": r["folder"], "src": r["src"], "dest": r["dest"]}
                for r in self.results
                if r.get("moved")
            ],
        }
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    @staticmethod
    def undo_last(path: str, verbose: bool = True) -> Tuple[int, str]:
        """Undo the most recent organization in `path` using .pyorganize_history.json."""
        history_path = os.path.join(path, HISTORY_FILENAME)
        if not os.path.exists(history_path):
            msg = "No organization history found in this folder to undo."
            if verbose:
                print(msg)
            return 0, msg

        try:
            with open(history_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            msg = f"Failed to read undo history: {e}"
            if verbose:
                print(msg)
            return 0, msg

        moves = data.get("moves", [])
        restored = 0
        touched_folders = set()

        for entry in reversed(moves):
            src = entry.get("src")
            dest = entry.get("dest")
            if dest and src and os.path.exists(dest):
                try:
                    shutil.move(dest, src)
                    restored += 1
                    touched_folders.add(os.path.dirname(dest))
                    if verbose:
                        print(f"Restored: {os.path.basename(src)}")
                except Exception as e:
                    if verbose:
                        print(f"Could not restore {dest}: {e}")

        # Remove created folders if they are now empty
        for folder_dir in touched_folders:
            try:
                if os.path.isdir(folder_dir) and not os.listdir(folder_dir):
                    os.rmdir(folder_dir)
            except Exception:
                pass

        try:
            os.remove(history_path)
        except Exception:
            pass

        summary = f"Restored {restored} file(s) to their original locations."
        if verbose:
            print(f"✅ {summary}")
        return restored, summary

    def _organize_by_ai(self, files: List[str], existing_subfolders: List[str]) -> None:
        cfg = load_config()
        provider = self.ai_provider or cfg.get("active_provider", "gemini")
        api_key = self.api_key or cfg.get("api_keys", {}).get(provider, "")
        model = self.ai_model or cfg.get("models", {}).get(provider)
        instructions = self.custom_instructions or cfg.get("custom_instructions", "")

        categorizer = AIContextCategorizer(
            provider=provider,
            api_key=api_key,
            model=model,
            custom_instructions=instructions,
        )

        file_contexts = []
        for item in files:
            full_path = os.path.join(self.path, item)
            ctx = extract_file_context(full_path)
            file_contexts.append(ctx)

        if self.verbose:
            print(
                f"[AI Mode] Analyzing context of {len(file_contexts)} file(s) using "
                f"{PROVIDERS[categorizer.provider]['name']} ({categorizer.model})..."
            )

        decisions = categorizer.categorize_files(file_contexts, existing_folders=existing_subfolders)

        for item in files:
            full_path = os.path.join(self.path, item)
            folder, reason = decisions.get(item, ("Uncategorized", "Categorized by AI context"))
            self._execute_move(item, full_path, folder, reason=reason)

    def _organize_by_extension(self, items: List[str]) -> None:
        for item in items:
            if item == HISTORY_FILENAME:
                continue

            full_path = os.path.join(self.path, item)

            if not os.path.isfile(full_path):
                if self.verbose:
                    print(f"[Verbose] Skipping non-file: {item}")
                continue

            ext = os.path.splitext(item)[1].lower()
            if self.verbose:
                print(f"[Verbose] Checking file: {item} (.{ext})")

            for folder, extensions in FILE_MAP.items():
                if ext in extensions:
                    # Preserve original behavior where destination folder is created during scan
                    destination_folder = os.path.join(self.path, folder)
                    os.makedirs(destination_folder, exist_ok=True)
                    self._execute_move(
                        item,
                        full_path,
                        folder,
                        reason=f"Extension {ext or '(none)'} → {folder}",
                    )
                    break
            else:
                if self.include_unmatched:
                    self._execute_move(
                        item,
                        full_path,
                        "Uncategorized Files",
                        reason=f"Unrecognized extension {ext or '(none)'}",
                    )
                else:
                    self.skipped_count += 1
                    if self.verbose:
                        print(f"[Verbose] No category for: {item}")

    def organize(self) -> List[dict]:
        self.moved_count = 0
        self.skipped_count = 0
        self.results.clear()

        try:
            items = os.listdir(self.path)
            print("Number of Items Found:", len(items))
        except FileNotFoundError:
            print("❌ Folder not found. Check your path.")
            return []

        if self.use_ai:
            files = []
            existing_subfolders = []
            for item in items:
                if item == HISTORY_FILENAME or item.startswith("."):
                    continue
                full_path = os.path.join(self.path, item)
                if os.path.isfile(full_path):
                    files.append(item)
                elif os.path.isdir(full_path):
                    existing_subfolders.append(item)
                    if self.verbose:
                        print(f"[Verbose] Skipping non-file: {item}")

            if files:
                self._organize_by_ai(files, existing_subfolders)
        else:
            self._organize_by_extension(items)

        if not self.dry_run and self.moved_count > 0:
            self._save_history()

        # Print summary
        if self.dry_run:
            print(f"[Dry Run Complete] {self.moved_count} files would have been moved.")
        else:
            print(f"✅ {self.moved_count} files moved.")

        return self.results


def main():
    args = parse_args()
    if args.undo:
        FileOrganizer.undo_last(args.path, verbose=True)
        return

    organizer = FileOrganizer(
        args.path,
        dry_run=args.dry_run,
        verbose=args.verbose,
        use_ai=args.ai or bool(args.provider or args.api_key),
        ai_provider=args.provider,
        api_key=args.api_key,
        ai_model=args.model,
        custom_instructions=args.instructions,
    )
    organizer.organize()


if __name__ == "__main__":
    main()
