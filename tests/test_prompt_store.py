"""Kayitli prompt erisim testleri."""

from crypto_deep_research.prompt_store import latest_prompt, prompt_for_report
from crypto_deep_research.storage.db import Database


class _Settings:
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir


def test_latest_prompt_from_db_meta(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "BTC_x_prompt.txt").write_text("PROMPT METNI", encoding="utf-8")
    settings = _Settings(prompts)
    db = Database(tmp_path / "t.db")
    db.save_report(
        "BTC_x", "run1", "bitcoin", "# rapor", {"prompt_path": str(prompts / "BTC_x_prompt.txt")}
    )
    data = latest_prompt(db, settings, "bitcoin")
    assert data["prompt"] == "PROMPT METNI"
    assert data["name"] == "BTC_x"


def test_latest_prompt_falls_back_to_files(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "ETH_2026_prompt.txt").write_text("ETH PROMPT", encoding="utf-8")
    settings = _Settings(prompts)
    db = Database(tmp_path / "t.db")
    data = latest_prompt(db, settings, "ethereum", symbol="ETH")
    assert data["prompt"] == "ETH PROMPT"
    assert latest_prompt(db, settings, "yokcoin") is None


def test_prompt_for_report_without_meta(tmp_path):
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "BTC_y_prompt.txt").write_text("Y PROMPT", encoding="utf-8")
    settings = _Settings(prompts)
    db = Database(tmp_path / "t.db")
    db.save_report("BTC_y", "run2", "bitcoin", "#", {})
    data = prompt_for_report(db, settings, "BTC_y")
    assert data["prompt"] == "Y PROMPT"
    assert prompt_for_report(db, settings, "YOK") is None
