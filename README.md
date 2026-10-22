# PyOrganize v2.0 — Smart & AI Context File Organizer

**PyOrganize** is a modern Python desktop app (Flet GUI) and CLI tool that cleans up cluttered directories like `Downloads`, `Desktop`, or project workspaces.

In **v2.0**, PyOrganize introduces **AI Context Organization**: supply your **Google Gemini**, **OpenAI ChatGPT**, **DeepSeek**, or **Anthropic Claude** API key to automatically inspect file contents, documents, code, and metadata and sort files into meaningful semantic folders based on context instead of just file extension.

---

## ✨ Key Features

- **🧠 AI Context Mode (Multi-Provider)**:
  - Supports **Google Gemini**, **OpenAI ChatGPT**, **DeepSeek**, and **Anthropic Claude**.
  - Extracts text previews from documents (`.docx`, `.pptx`, `.xlsx`, `.pdf`, `.txt`, `.md`, `.ipynb`), source code, and archive listings (`.zip`, `.tar`) to categorize files by topic and content (e.g., *Finance & Invoices*, *Study Notes*, *Resumes & Career*, *Work Projects*).
  - Supports **Custom Sorting Instructions** (e.g., *"Group files by university course"* or *"Separate paid vs unpaid invoices"*).
- **⚡ Fast Extension Mode**:
  - Instant offline sorting across 15+ categories (`PDF Files`, `Image Files`, `Video Files`, `Programming Files`, `Compressed Files`, `Ebook Files`, `Font Files`, etc.).
- **🎨 Modern Dark Desktop UI**:
  - Interactive **Dry-Run Preview** showing destination folders, file counts, and AI reasoning before moving a single file.
  - Built-in **API Key Manager** (`~/.pyorganize/config.json`) with one-click live API connection testing and model selection.
  - **One-Click Undo** to restore files from the last organization run (`.pyorganize_history.json`).

---

## 🚀 Getting Started

### Installation

```bash
git clone https://github.com/abdullohtariq/pyorganize.git
cd pyorganize
pip install -r requirements.txt
pip install -e .
```

### Launch the Modern GUI

```bash
python gui.py
# or via entry point:
pyorganize-gui
```

### CLI Usage

**1. Organize by Extension (Fast Local Mode):**
```bash
python pyorganize.py --path "C:/Users/You/Downloads" --verbose
```

**2. Preview with Dry Run:**
```bash
python pyorganize.py --path "C:/Users/You/Downloads" --dry-run
```

**3. Organize by File Context using AI (Gemini / ChatGPT / DeepSeek / Claude):**
```bash
python pyorganize.py --path "C:/Users/You/Downloads" --ai --provider gemini --api-key "YOUR_API_KEY" --verbose
```

**4. Undo the Last Organization:**
```bash
python pyorganize.py --path "C:/Users/You/Downloads" --undo
```

---

## 🧪 Running Tests

```bash
pytest -v
```
