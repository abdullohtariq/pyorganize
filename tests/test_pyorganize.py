import json
import os
import zipfile
from unittest.mock import patch

import pytest

import ai_organizer
import pyorganize


@pytest.fixture
def temp_dir(tmp_path):
    # Create sample files and a subfolder
    for name in ["a.pdf", "b.jpg", "c.txt", "d.exe"]:
        (tmp_path / name).write_text("dummy")
    (tmp_path / "subfolder").mkdir()
    return tmp_path


def test_dry_run_does_not_move_files(temp_dir, capsys):
    organizer = pyorganize.FileOrganizer(str(temp_dir), dry_run=True, verbose=False)
    organizer.organize()
    # Original files still exist
    for fname in ["a.pdf", "b.jpg", "c.txt", "d.exe"]:
        assert (temp_dir / fname).exists()
    # Dry‑run summary printed
    captured = capsys.readouterr()
    assert "[Dry Run Complete]" in captured.out


def test_move_files(temp_dir):
    organizer = pyorganize.FileOrganizer(str(temp_dir), dry_run=False, verbose=False)
    organizer.organize()
    assert (temp_dir / "PDF Files" / "a.pdf").exists()
    assert (temp_dir / "Image Files" / "b.jpg").exists()
    assert (temp_dir / "Text Files" / "c.txt").exists()
    assert (temp_dir / "Software Files" / "d.exe").exists()


def test_verbose_output(temp_dir, capsys):
    organizer = pyorganize.FileOrganizer(str(temp_dir), dry_run=False, verbose=True)
    organizer.organize()
    captured = capsys.readouterr()
    assert "Moved: a.pdf → PDF Files" in captured.out
    assert "Moved: b.jpg → Image Files" in captured.out


def test_ignores_directories(temp_dir):
    organizer = pyorganize.FileOrganizer(str(temp_dir), dry_run=False, verbose=True)
    organizer.organize()
    assert (temp_dir / "subfolder").exists()


def test_undo_last_restores_files(temp_dir):
    organizer = pyorganize.FileOrganizer(str(temp_dir), dry_run=False, verbose=False)
    organizer.organize()
    assert (temp_dir / "PDF Files" / "a.pdf").exists()

    restored_count, _ = pyorganize.FileOrganizer.undo_last(str(temp_dir), verbose=False)
    assert restored_count == 4
    for fname in ["a.pdf", "b.jpg", "c.txt", "d.exe"]:
        assert (temp_dir / fname).exists()


def test_extract_file_context_text_and_docx(tmp_path):
    txt_file = tmp_path / "meeting_notes.txt"
    txt_file.write_text("Q4 financial budget review and revenue projections for 2027.")
    ctx = ai_organizer.extract_file_context(str(txt_file))
    assert ctx["filename"] == "meeting_notes.txt"
    assert "Q4 financial budget" in ctx["content_preview"]

    # Create a minimal .docx zip containing word/document.xml
    docx_file = tmp_path / "resume_john.docx"
    with zipfile.ZipFile(docx_file, "w") as zf:
        zf.writestr(
            "word/document.xml",
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            "<w:body><w:p><w:r><w:t>Senior Python Software Engineer Resume</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
    docx_ctx = ai_organizer.extract_file_context(str(docx_file))
    assert "Senior Python Software Engineer Resume" in docx_ctx["content_preview"]


@pytest.mark.parametrize("provider", ["gemini", "chatgpt", "deepseek", "claude"])
def test_ai_context_organization_all_providers(tmp_path, provider):
    (tmp_path / "aws_invoice_oct.txt").write_text("AWS Cloud Hosting Invoice #9812 Total: $125.00")
    (tmp_path / "biology_lecture_1.md").write_text("Cell structure, mitosis, and molecular biology notes")

    mock_llm_response = json.dumps(
        {
            "files": [
                {
                    "filename": "aws_invoice_oct.txt",
                    "folder": "Finance & Invoices",
                    "reason": "Contains AWS billing invoice details",
                },
                {
                    "filename": "biology_lecture_1.md",
                    "folder": "Biology Study Notes",
                    "reason": "Contains lecture notes on cell biology",
                },
            ]
        }
    )

    with patch.object(ai_organizer.AIContextCategorizer, "_call_llm", return_value=mock_llm_response):
        organizer = pyorganize.FileOrganizer(
            str(tmp_path),
            dry_run=False,
            verbose=True,
            use_ai=True,
            ai_provider=provider,
            api_key=f"test-{provider}-key-123",
        )
        results = organizer.organize()

    assert len(results) == 2
    assert (tmp_path / "Finance & Invoices" / "aws_invoice_oct.txt").exists()
    assert (tmp_path / "Biology Study Notes" / "biology_lecture_1.md").exists()
