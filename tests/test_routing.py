"""Unit tests for request normalization and deterministic routing."""

import pytest
from astrarun.core.models import AppInfo, FolderInfo, RoutingContext
from astrarun.routing.deterministic import DeterministicRouter, normalize_request


@pytest.fixture
def test_context() -> RoutingContext:
    apps = {
        "notepad": AppInfo("notepad", "Notepad", "C:\\Windows\\System32\\notepad.exe"),
        "calc": AppInfo("calc", "Calculator", "C:\\Windows\\System32\\calc.exe"),
        "code": AppInfo("code", "Visual Studio Code", "C:\\Programs\\VSCode\\Code.exe"),
        "wt": AppInfo("wt", "Windows Terminal", "C:\\WindowsApps\\wt.exe"),
    }
    folders = {
        "downloads": FolderInfo("downloads", "Downloads", "C:\\Users\\Test\\Downloads"),
        "documents": FolderInfo("documents", "Documents", "C:\\Users\\Test\\Documents"),
        "desktop": FolderInfo("desktop", "Desktop", "C:\\Users\\Test\\Desktop"),
        "workspace": FolderInfo("workspace", "Workspace", "E:\\Workspace"),
        "active projects": FolderInfo("active projects", "Active", "E:\\Workspace\\Active"),
    }
    urls = {
        "github": "https://github.com",
        "youtube": "https://youtube.com",
        "google": "https://google.com",
    }
    aliases = {
        "calculator": "calc",
        "editor": "notepad",
        "vscode": "code",
        "vs code": "code",
        "terminal": "wt",
    }
    return RoutingContext(apps=apps, folders=folders, urls=urls, aliases=aliases)


def test_normalization():
    assert normalize_request("open notepad") == ("open", "notepad")
    assert normalize_request("launch notepad") == ("launch", "notepad")
    assert normalize_request("start notepad") == ("start", "notepad")
    assert normalize_request("go to downloads") == ("go to", "downloads")
    assert normalize_request("show downloads") == ("show", "downloads")
    assert normalize_request("notepad") == ("", "notepad")
    assert normalize_request("   open    notepad   ") == ("open", "notepad")


def test_route_applications(test_context):
    router = DeterministicRouter()

    # Exact key
    d1 = router.route("open notepad", test_context)
    assert d1.tool == "open_app"
    assert d1.args["app"] == "notepad"
    assert d1.confidence == 1.0

    # Without verb
    d2 = router.route("calc", test_context)
    assert d2.tool == "open_app"
    assert d2.args["app"] == "calc"

    # Alias
    d3 = router.route("open calculator", test_context)
    assert d3.tool == "open_app"
    assert d3.args["app"] == "calc"

    # Compound alias (vs code)
    d4 = router.route("launch vs code", test_context)
    assert d4.tool == "open_app"
    assert d4.args["app"] == "code"


def test_route_folders(test_context):
    router = DeterministicRouter()

    d1 = router.route("open downloads", test_context)
    assert d1.tool == "open_folder"
    assert d1.args["folder"] == "C:\\Users\\Test\\Downloads"

    d2 = router.route("go to documents", test_context)
    assert d2.tool == "open_folder"
    assert d2.args["folder"] == "C:\\Users\\Test\\Documents"

    d3 = router.route("open workspace", test_context)
    assert d3.tool == "open_folder"
    assert d3.args["folder"] == "E:\\Workspace"

    d4 = router.route("open active projects", test_context)
    assert d4.tool == "open_folder"
    assert d4.args["folder"] == "E:\\Workspace\\Active"


def test_route_urls(test_context):
    router = DeterministicRouter()

    # Configured alias
    d1 = router.route("open github", test_context)
    assert d1.tool == "open_url"
    assert d1.args["url"] == "https://github.com"

    d2 = router.route("youtube", test_context)
    assert d2.tool == "open_url"
    assert d2.args["url"] == "https://youtube.com"

    # Raw URL
    d3 = router.route("open https://news.ycombinator.com", test_context)
    assert d3.tool == "open_url"
    assert d3.args["url"] == "https://news.ycombinator.com"


def test_route_unknown(test_context):
    router = DeterministicRouter()

    d1 = router.route("make me a coffee", test_context)
    assert not d1.is_resolved
    assert d1.tool == "unknown"

    d2 = router.route("", test_context)
    assert not d2.is_resolved
    assert d2.tool == "unknown"
