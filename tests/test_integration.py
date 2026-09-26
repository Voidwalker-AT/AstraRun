"""Integration tests validating live system discovery and routing."""

import pytest
from astrarun.config.loader import load_config
from astrarun.core.models import RoutingContext
from astrarun.discovery.apps import AppDiscoveryCache
from astrarun.discovery.folders import FolderResolver
from astrarun.routing.deterministic import DeterministicRouter


@pytest.fixture(scope="module")
def live_context() -> RoutingContext:
    config = load_config("config")
    app_cache = AppDiscoveryCache(config.configured_apps)
    folder_resolver = FolderResolver()
    return RoutingContext(
        apps=app_cache.apps,
        folders=folder_resolver.folders,
        urls=config.urls,
        aliases=config.aliases,
    )


def test_live_app_discovery(live_context: RoutingContext):
    # Standard tools must be found on Windows
    assert "notepad" in live_context.apps, "Notepad should be discovered"
    assert "calc" in live_context.apps, "Calculator should be discovered"
    assert "explorer" in live_context.apps, "Explorer should be discovered"
    assert "cmd" in live_context.apps, "CMD should be discovered"


def test_live_folder_discovery(live_context: RoutingContext):
    assert "downloads" in live_context.folders, "Downloads should be resolved"
    assert "documents" in live_context.folders, "Documents should be resolved"
    assert "desktop" in live_context.folders, "Desktop should be resolved"
    assert "workspace" in live_context.folders, "Workspace should be resolved"
    assert "active" in live_context.folders, "Active projects should be resolved"


def test_live_routing_apps(live_context: RoutingContext):
    router = DeterministicRouter()

    d_notepad = router.route("open notepad", live_context)
    assert d_notepad.tool == "open_app"
    assert d_notepad.args["app"] == "notepad"

    d_calc = router.route("open calculator", live_context)
    assert d_calc.tool == "open_app"
    assert d_calc.args["app"] == "calc"

    d_explorer = router.route("explorer", live_context)
    assert d_explorer.tool == "open_app"


def test_live_routing_folders(live_context: RoutingContext):
    router = DeterministicRouter()

    d_dl = router.route("open downloads", live_context)
    assert d_dl.tool == "open_folder"
    assert "Downloads" in d_dl.args["folder"]

    d_docs = router.route("open documents", live_context)
    assert d_docs.tool == "open_folder"
    assert "Documents" in d_docs.args["folder"]

    d_ws = router.route("open workspace", live_context)
    assert d_ws.tool == "open_folder"

    d_act = router.route("open active projects", live_context)
    assert d_act.tool == "open_folder"


def test_live_routing_urls(live_context: RoutingContext):
    router = DeterministicRouter()

    d_gh = router.route("open github", live_context)
    assert d_gh.tool == "open_url"
    assert d_gh.args["url"] == "https://github.com"

    d_yt = router.route("open youtube", live_context)
    assert d_yt.tool == "open_url"
    assert d_yt.args["url"] == "https://youtube.com"


def test_live_routing_unknown(live_context: RoutingContext):
    router = DeterministicRouter()
    d = router.route("arbitrary unknown request xyz", live_context)
    assert not d.is_resolved
    assert d.tool == "unknown"
