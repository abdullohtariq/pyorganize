import os
import pytest
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
