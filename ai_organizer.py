"""
AI Context-Based File Categorizer for PyOrganize.
Supports Google Gemini, OpenAI (ChatGPT), DeepSeek, and Anthropic Claude.
Extracts file content snippets and metadata so files are organized by semantic context
rather than just file extension.
"""

import json
import os
import re
import tarfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CONFIG_DIR = Path.home() / ".pyorganize"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "default_model": "gemini-2.0-flash",
        "models": ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "key_placeholder": "AIzaSy...",
        "docs_url": "https://aistudio.google.com/app/apikey",
    },
    "chatgpt": {
        "name": "OpenAI ChatGPT",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
        "key_placeholder": "sk-...",
        "docs_url": "https://platform.openai.com/api-keys",
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "key_placeholder": "sk-...",
        "docs_url": "https://platform.deepseek.com/api_keys",
    },
    "claude": {
        "name": "Anthropic Claude",
        "default_model": "claude-3-5-haiku-latest",
        "models": ["claude-3-5-haiku-latest", "claude-3-7-sonnet-latest", "claude-3-5-sonnet-latest"],
        "key_placeholder": "sk-ant-...",
        "docs_url": "https://console.anthropic.com/settings/keys",
    },
}

TEXT_EXTENSIONS = {
    ".txt", ".md", ".rtf", ".csv", ".tsv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs", ".rb", ".php",
    ".sh", ".bat", ".ps1", ".sql", ".ini", ".cfg", ".conf", ".toml", ".env",
    ".log", ".tex", ".bib", ".r", ".swift", ".kt", ".dart", ".lua", ".dockerfile"
}


def load_config() -> dict:
    """Load saved user settings and API keys from ~/.pyorganize/config.json."""
    default_cfg = {
        "active_provider": "gemini",
        "organization_mode": "extension",
        "custom_instructions": "",
        "api_keys": {
            "gemini": "",
            "chatgpt": "",
            "deepseek": "",
            "claude": "",
        },
        "models": {
            "gemini": PROVIDERS["gemini"]["default_model"],
            "chatgpt": PROVIDERS["chatgpt"]["default_model"],
            "deepseek": PROVIDERS["deepseek"]["default_model"],
            "claude": PROVIDERS["claude"]["default_model"],
        },
        "recent_folders": [],
    }
    if not CONFIG_FILE.exists():
        return default_cfg
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in default_cfg.items():
            if k not in data:
                data[k] = v
            elif isinstance(v, dict) and isinstance(data[k], dict):
                for sub_k, sub_v in v.items():
                    data[k].setdefault(sub_k, sub_v)
        return data
    except Exception:
        return default_cfg


def save_config(config: dict) -> None:
    """Save user settings and API keys to ~/.pyorganize/config.json."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass


def _extract_docx_text(filepath: str, max_chars: int = 1200) -> str:
    """Extract plain text from a .docx file using standard library zipfile + xml."""
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            xml_content = zf.read("word/document.xml")
        tree = ET.fromstring(xml_content)
        texts = [node.text for node in tree.iter() if node.text and node.text.strip()]
        combined = " ".join(texts)
        return re.sub(r"\s+", " ", combined).strip()[:max_chars]
    except Exception:
        return ""


def _extract_pptx_text(filepath: str, max_chars: int = 1200) -> str:
    """Extract slide text from a .pptx file using standard library zipfile + xml."""
    try:
        texts = []
        with zipfile.ZipFile(filepath, "r") as zf:
            slide_files = sorted(
                [name for name in zf.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
            )[:5]
            for slide in slide_files:
                xml_content = zf.read(slide)
                tree = ET.fromstring(xml_content)
                for node in tree.iter():
                    if node.text and node.text.strip():
                        texts.append(node.text.strip())
                if sum(len(t) for t in texts) >= max_chars:
                    break
        combined = " ".join(texts)
        return re.sub(r"\s+", " ", combined).strip()[:max_chars]
    except Exception:
        return ""


def _extract_xlsx_text(filepath: str, max_chars: int = 1200) -> str:
    """Extract shared strings from a .xlsx file using standard library zipfile + xml."""
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            if "xl/sharedStrings.xml" not in zf.namelist():
                return ""
            xml_content = zf.read("xl/sharedStrings.xml")
        tree = ET.fromstring(xml_content)
        texts = [node.text.strip() for node in tree.iter() if node.text and node.text.strip()]
        combined = ", ".join(texts[:80])
        return re.sub(r"\s+", " ", combined).strip()[:max_chars]
    except Exception:
        return ""


def _extract_pdf_text(filepath: str, max_chars: int = 1200) -> str:
    """Extract text from PDF using pypdf if available, or lightweight binary text scan fallback."""
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(filepath)
        pages_text = []
        for page in reader.pages[:3]:
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(txt.strip())
            if sum(len(p) for p in pages_text) >= max_chars:
                break
        if pages_text:
            return re.sub(r"\s+", " ", " ".join(pages_text))[:max_chars]
    except Exception:
        pass

    # Fallback: scan PDF header/body for readable parenthesized strings or metadata
    try:
        with open(filepath, "rb") as f:
            raw = f.read(65536)
        # Extract literal strings inside parentheses that look like human words
        matches = re.findall(rb"\(([A-Za-z0-9 ,.\-_:;/]{4,120})\)", raw)
        decoded = []
        for m in matches[:40]:
            s = m.decode("latin-1", errors="ignore").strip()
            if any(c.isalpha() for c in s):
                decoded.append(s)
        if decoded:
            return re.sub(r"\s+", " ", " ".join(decoded))[:max_chars]
    except Exception:
        pass
    return ""


def _extract_archive_listing(filepath: str, ext: str) -> str:
    """List top entries inside a zip or tar archive to give context."""
    try:
        if ext == ".zip" and zipfile.is_zipfile(filepath):
            with zipfile.ZipFile(filepath, "r") as zf:
                names = zf.namelist()[:20]
            return "Archive contents: " + ", ".join(names)
        if ext in {".tar", ".gz", ".tgz"} and tarfile.is_tarfile(filepath):
            with tarfile.open(filepath, "r:*") as tf:
                names = tf.getnames()[:20]
            return "Archive contents: " + ", ".join(names)
    except Exception:
        pass
    return ""


def _extract_ipynb_text(filepath: str, max_chars: int = 1200) -> str:
    """Extract markdown and code cells from a Jupyter Notebook."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            nb = json.load(f)
        cells = nb.get("cells", [])[:8]
        snippets = []
        for c in cells:
            source = c.get("source", [])
            if isinstance(source, list):
                snippets.append("".join(source))
            elif isinstance(source, str):
                snippets.append(source)
        return re.sub(r"\s+", " ", " ".join(snippets)).strip()[:max_chars]
    except Exception:
        return ""


def extract_file_context(filepath: str, max_chars: int = 1200) -> dict:
    """
    Inspect a file and return rich contextual metadata + content snippet
    for LLM categorization.
    """
    filename = os.path.basename(filepath)
    _, ext = os.path.splitext(filename)
    ext_lower = ext.lower()

    try:
        stat = os.stat(filepath)
        size_bytes = stat.st_size
        modified_date = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
    except Exception:
        size_bytes = 0
        modified_date = "unknown"

    snippet = ""
    if ext_lower == ".ipynb":
        snippet = _extract_ipynb_text(filepath, max_chars)
    elif ext_lower == ".docx":
        snippet = _extract_docx_text(filepath, max_chars)
    elif ext_lower == ".pptx":
        snippet = _extract_pptx_text(filepath, max_chars)
    elif ext_lower == ".xlsx":
        snippet = _extract_xlsx_text(filepath, max_chars)
    elif ext_lower == ".pdf":
        snippet = _extract_pdf_text(filepath, max_chars)
    elif ext_lower in {".zip", ".tar", ".gz", ".tgz"}:
        snippet = _extract_archive_listing(filepath, ext_lower)
    elif ext_lower in TEXT_EXTENSIONS or size_bytes < 32768:
        # Check if file looks like UTF-8/ASCII text
        try:
            with open(filepath, "rb") as f:
                sample = f.read(4096)
            if b"\x00" not in sample:
                text = sample.decode("utf-8", errors="ignore")
                snippet = re.sub(r"\s+", " ", text).strip()[:max_chars]
        except Exception:
            pass

    return {
        "filename": filename,
        "extension": ext_lower or "(no extension)",
        "size_kb": round(size_bytes / 1024, 1),
        "modified": modified_date,
        "content_preview": snippet if snippet else "(Binary or non-text file - infer context from filename & metadata)",
    }


def _sanitize_folder_name(folder: str) -> str:
    """Ensure AI-returned folder name is safe for Windows/macOS/Linux filesystems."""
    if not folder or not isinstance(folder, str):
        return "Uncategorized"
    # Replace path separators or illegal characters
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " - ", folder).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip(". ")
    return cleaned[:60] if cleaned else "Uncategorized"


class AIContextCategorizer:
    """
    Multi-provider LLM client for organizing files by semantic content & context.
    Supports:
      - gemini (Google Gemini API)
      - chatgpt (OpenAI Chat Completions API)
      - deepseek (DeepSeek Chat Completions API)
      - claude (Anthropic Messages API)
    """

    def __init__(
        self,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        custom_instructions: str = "",
        timeout: int = 45,
    ):
        self.provider = provider.lower().strip()
        if self.provider in ("openai", "gpt"):
            self.provider = "chatgpt"
        if self.provider not in PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}. Choose from: {', '.join(PROVIDERS.keys())}")
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise ValueError(f"API key is required for {PROVIDERS[self.provider]['name']}.")
        self.model = (model or PROVIDERS[self.provider]["default_model"]).strip()
        self.custom_instructions = (custom_instructions or "").strip()
        self.timeout = timeout

    def _build_prompts(self, file_contexts: List[dict], existing_folders: List[str]) -> Tuple[str, str]:
        system_prompt = (
            "You are an expert intelligent file organization assistant. "
            "Your task is to organize a user's files into clean, intuitive, semantic folders based on the "
            "CONTENT and CONTEXT of each file (its text snippet, topic, purpose, filename, and metadata), "
            "NOT merely by file extension.\n\n"
            "Rules:\n"
            "1. Group related files together into meaningful contextual categories (for example: "
            "'Finance & Invoices', 'Work & Reports', 'Resumes & Career', 'School & Study Notes', "
            "'Python & Dev Projects', 'Web Development', 'Receipts & Taxes', 'Contracts & Legal', "
            "'Design & Mockups', 'Personal & Photos', 'Installers & Setup', 'Backups & Archives').\n"
            "2. Keep the total number of folders reasonable and consolidated (avoid creating a separate folder "
            "for every single file unless topics are completely distinct). Reuse existing folders when appropriate.\n"
            "3. Folder names must be clean, human-friendly titles (2 to 4 words max) with NO slashes or illegal path characters.\n"
            "4. Return ONLY valid JSON in the exact format requested, with no markdown code fences or extra commentary."
        )
        if self.custom_instructions:
            system_prompt += f"\n\nUser Custom Organization Instructions:\n{self.custom_instructions}"

        existing_str = ", ".join(existing_folders) if existing_folders else "None yet"
        user_prompt = (
            f"Existing folders in target directory: [{existing_str}]\n\n"
            "Analyze the following files and their extracted content previews, then assign each file to the best "
            "contextual folder name and provide a short 1-sentence reason.\n\n"
            "Respond strictly with a JSON object matching this schema:\n"
            '{\n  "files": [\n    {"filename": "exact_filename.ext", "folder": "Contextual Folder Name", "reason": "Brief reason based on content"}\n  ]\n}\n\n'
            f"Files to categorize:\n{json.dumps(file_contexts, ensure_ascii=False, indent=2)}"
        )
        return system_prompt, user_prompt

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Make HTTP request to the configured AI provider and return raw response text."""
        if self.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt)
        elif self.provider == "chatgpt":
            return self._call_openai_compatible(
                url="https://api.openai.com/v1/chat/completions",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        elif self.provider == "deepseek":
            return self._call_openai_compatible(
                url="https://api.deepseek.com/chat/completions",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        elif self.provider == "claude":
            return self._call_claude(system_prompt, user_prompt)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }
        data = self._http_post_json(url, payload, headers={"Content-Type": "application/json"})
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {data}")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts)

    def _call_openai_compatible(self, url: str, system_prompt: str, user_prompt: str) -> str:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        data = self._http_post_json(url, payload, headers=headers)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"API returned no choices: {data}")
        return choices[0].get("message", {}).get("content", "")

    def _call_claude(self, system_prompt: str, user_prompt: str) -> str:
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.2,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        data = self._http_post_json(url, payload, headers=headers)
        content_blocks = data.get("content", [])
        return "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")

    def _http_post_json(self, url: str, payload: dict, headers: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                return json.loads(resp_body)
        except urllib.error.HTTPError as e:
            err_text = ""
            try:
                err_text = e.read().decode("utf-8", errors="ignore")
                err_json = json.loads(err_text)
                if "error" in err_json:
                    msg = err_json["error"]
                    if isinstance(msg, dict):
                        msg = msg.get("message") or str(msg)
                    raise RuntimeError(f"{PROVIDERS[self.provider]['name']} API Error ({e.code}): {msg}")
            except RuntimeError:
                raise
            except Exception:
                pass
            raise RuntimeError(f"{PROVIDERS[self.provider]['name']} HTTP {e.code}: {err_text or e.reason}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error connecting to {PROVIDERS[self.provider]['name']}: {e.reason}")

    def test_connection(self) -> Tuple[bool, str]:
        """Verify that the API key and model work by categorizing a single sample item."""
        try:
            sample = [
                {
                    "filename": "invoice_october_2026.pdf",
                    "extension": ".pdf",
                    "size_kb": 42.0,
                    "modified": "2026-10-22",
                    "content_preview": "INVOICE #1042 - Total Due: $450.00 for Cloud Hosting Services.",
                }
            ]
            result = self.categorize_files(sample, existing_folders=[])
            if "invoice_october_2026.pdf" in result:
                folder, reason = result["invoice_october_2026.pdf"]
                return True, f"Connected to {PROVIDERS[self.provider]['name']} ({self.model})! Sample → '{folder}'"
            return True, f"Connected to {PROVIDERS[self.provider]['name']} ({self.model})!"
        except Exception as e:
            return False, str(e)

    def categorize_files(
        self,
        file_contexts: List[dict],
        existing_folders: Optional[List[str]] = None,
        batch_size: int = 25,
    ) -> Dict[str, Tuple[str, str]]:
        """
        Categorize a list of file context dicts in batches.
        Returns a mapping: { filename: (folder_name, reason) }
        """
        existing = list(existing_folders or [])
        decisions: Dict[str, Tuple[str, str]] = {}

        for i in range(0, len(file_contexts), batch_size):
            batch = file_contexts[i : i + batch_size]
            sys_prompt, usr_prompt = self._build_prompts(batch, existing)
            raw_text = self._call_llm(sys_prompt, usr_prompt)
            parsed = self._parse_llm_json(raw_text)

            items = parsed.get("files", []) if isinstance(parsed, dict) else []
            if isinstance(parsed, list):
                items = parsed

            for entry in items:
                if not isinstance(entry, dict):
                    continue
                fname = entry.get("filename")
                folder = _sanitize_folder_name(entry.get("folder", "Uncategorized"))
                reason = (entry.get("reason") or "Categorized by AI context analysis").strip()
                if fname:
                    decisions[fname] = (folder, reason)
                    if folder not in existing:
                        existing.append(folder)

            # Fallback for any file in batch that LLM omitted
            for ctx in batch:
                fname = ctx["filename"]
                if fname not in decisions:
                    decisions[fname] = ("Uncategorized", "AI did not return a specific category")

        return decisions

    @staticmethod
    def _parse_llm_json(raw_text: str) -> dict:
        """Extract and parse JSON object from LLM response, stripping markdown fences if present."""
        text = (raw_text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Find outermost JSON object
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        raise RuntimeError(f"Failed to parse JSON response from AI: {text[:200]}")
