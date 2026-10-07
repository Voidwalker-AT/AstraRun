"""Unit tests for BrowserService DOM extraction and interaction."""

import pytest
from astrarun.browser.service import BrowserService


def test_browser_service_dom_extraction():
    svc = BrowserService()
    raw_html = """
    <!DOCTYPE html>
    <html>
    <head><title>Astra Test Dashboard</title></head>
    <body>
        <h1>Workstation Controls</h1>
        <button id="btn_plot" class="primary" onclick="generatePlot()">Generate CPU Graph</button>
        <a href="/docs/guide" id="link_guide">Documentation</a>
        <input type="text" name="filter" placeholder="Search tasks..." />
        <script>console.log("ignore me");</script>
    </body>
    </html>
    """
    snapshot = svc.inspect_html(raw_html, url="http://127.0.0.1:8080/dashboard", title="Astra Test Dashboard")

    assert snapshot.title == "Astra Test Dashboard"
    assert snapshot.element_count >= 3

    # Check button extraction
    btn = next(e for e in snapshot.interactive_elements if e["tag"] == "button")
    assert btn["id"] == "@e1"
    assert "btn_plot" in btn["attributes"].get("id", "")

    # Check click simulation
    clicked = svc.click_element_by_id("@e1")
    assert clicked is True
