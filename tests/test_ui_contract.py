from pathlib import Path
import pytest

BASE = Path(__file__).resolve().parents[1]
PORTALS = [
    ("patient", "Patient Portal"),
    ("doctor", "Doctor Portal"),
    ("admin", "Administrator Portal"),
]


@pytest.mark.parametrize("role,title", PORTALS)
def test_dashboard_file_exists(role, title):
    path = BASE / "app" / "templates" / role / "dashboard.html"
    assert path.is_file(), f"Missing {role} dashboard"


@pytest.mark.parametrize("role,title", PORTALS)
def test_dashboard_contains_mediqueue_brand(role, title):
    path = BASE / "app" / "templates" / role / "dashboard.html"
    content = path.read_text(encoding="utf-8")
    assert "MediQueue" in content


def test_existing_homepage_exists():
    path = BASE / "app" / "templates" / "index.html"
    assert path.is_file()
