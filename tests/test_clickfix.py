"""Tests for the click witness/fallback patch and the report salvage call."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

import crowdtest.clickfix as clickfix
from crowdtest.clickfix import ensure_reliable_clicks
from crowdtest.runner import _history_digest, _salvage_report


class FakeCDP:
    """Records CDP traffic and scripts the witness answers."""

    def __init__(self, witness_saw_click: bool, field_value: str = ""):
        self.witness_saw_click = witness_saw_click
        self.field_value = field_value
        self.token = None
        self.calls = []
        self.session_id = "sess"
        send = SimpleNamespace(
            Runtime=SimpleNamespace(
                evaluate=self._evaluate, callFunctionOn=self._call_function_on
            ),
            DOM=SimpleNamespace(
                resolveNode=self._resolve_node,
                scrollIntoViewIfNeeded=self._scroll,
            ),
        )
        self.cdp_client = SimpleNamespace(send=send)

    async def _evaluate(self, params, session_id=None):
        expr = params["expression"]
        if "__ct_token = " in expr:
            self.token = re.search(r"__ct_token = '([0-9a-f]+)'", expr).group(1)
            self.calls.append("arm")
            return {"result": {"value": "armed"}}
        self.calls.append("read")
        seen = "true" if self.witness_saw_click else "false"
        return {"result": {"value": f'["{self.token}",{seen}]'}}

    async def _call_function_on(self, params, session_id=None):
        decl = params["functionDeclaration"]
        if "dispatchEvent(new Event('input'" in decl:
            self.calls.append("js_type")
            return {}
        if "String(this.value" in decl:  # the value read-back probe
            self.calls.append("read_value")
            return {"result": {"value": self.field_value}}
        self.calls.append("js_click")
        return {}

    async def _resolve_node(self, params, session_id=None):
        self.calls.append("resolve")
        return {"object": {"objectId": "obj1"}}

    async def _scroll(self, params, session_id=None):
        return {}


def make_node(tag="button", type_=""):
    return SimpleNamespace(
        tag_name=tag, attributes={"type": type_} if type_ else {}, backend_node_id=42
    )


@pytest.fixture()
def patched_watchdog(monkeypatch):
    """Apply the patch against stubbed original impls; undo everything after."""
    from browser_use.browser.watchdogs.default_action_watchdog import (
        DefaultActionWatchdog,
    )

    original_calls = []

    async def fake_click(self, element_node):
        original_calls.append(element_node.tag_name)
        return {"from": "original"}

    async def fake_type(self, element_node, text, clear=True, is_sensitive=False):
        original_calls.append(f"type:{text}")
        return {"from": "original-type"}

    saved_click = DefaultActionWatchdog._click_element_node_impl
    saved_type = DefaultActionWatchdog._input_text_element_node_impl
    monkeypatch.setattr(DefaultActionWatchdog, "_click_element_node_impl", fake_click)
    monkeypatch.setattr(
        DefaultActionWatchdog, "_input_text_element_node_impl", fake_type
    )
    monkeypatch.setattr(clickfix, "_patched", False)
    yield DefaultActionWatchdog, original_calls
    DefaultActionWatchdog._click_element_node_impl = saved_click
    DefaultActionWatchdog._input_text_element_node_impl = saved_type


def make_self(cdp):
    async def cdp_client_for_node(node):
        return cdp

    return SimpleNamespace(
        browser_session=SimpleNamespace(cdp_client_for_node=cdp_client_for_node)
    )


async def test_mode_cdp_leaves_browser_use_untouched(monkeypatch, patched_watchdog):
    monkeypatch.setenv("CROWDTEST_CLICK_MODE", "cdp")
    assert await ensure_reliable_clicks() is False
    assert clickfix._patched is False


async def test_landed_click_is_not_refired(monkeypatch, patched_watchdog):
    watchdog, original_calls = patched_watchdog
    monkeypatch.delenv("CROWDTEST_CLICK_MODE", raising=False)
    assert await ensure_reliable_clicks() is True

    cdp = FakeCDP(witness_saw_click=True)
    result = await watchdog._click_element_node_impl(make_self(cdp), make_node())
    assert original_calls == ["button"]
    assert result == {"from": "original"}
    assert "js_click" not in cdp.calls


async def test_missed_click_falls_back_to_dom_events(monkeypatch, patched_watchdog):
    watchdog, original_calls = patched_watchdog
    monkeypatch.delenv("CROWDTEST_CLICK_MODE", raising=False)
    await ensure_reliable_clicks()

    cdp = FakeCDP(witness_saw_click=False)
    result = await watchdog._click_element_node_impl(make_self(cdp), make_node())
    assert original_calls == ["button"]  # CDP click was attempted first
    assert "js_click" in cdp.calls
    assert result is None


async def test_mode_js_skips_cdp_click_entirely(monkeypatch, patched_watchdog):
    watchdog, original_calls = patched_watchdog
    monkeypatch.setenv("CROWDTEST_CLICK_MODE", "js")
    await ensure_reliable_clicks()

    cdp = FakeCDP(witness_saw_click=False)
    result = await watchdog._click_element_node_impl(make_self(cdp), make_node())
    assert original_calls == []
    assert "js_click" in cdp.calls
    assert result is None


async def test_select_elements_still_use_upstream_handling(
    monkeypatch, patched_watchdog
):
    watchdog, original_calls = patched_watchdog
    monkeypatch.delenv("CROWDTEST_CLICK_MODE", raising=False)
    await ensure_reliable_clicks()

    cdp = FakeCDP(witness_saw_click=False)
    result = await watchdog._click_element_node_impl(
        make_self(cdp), make_node(tag="select")
    )
    assert original_calls == ["select"]
    assert result == {"from": "original"}
    assert cdp.calls == []


async def test_typed_text_that_arrived_is_left_alone(monkeypatch, patched_watchdog):
    watchdog, original_calls = patched_watchdog
    monkeypatch.delenv("CROWDTEST_CLICK_MODE", raising=False)
    await ensure_reliable_clicks()

    cdp = FakeCDP(witness_saw_click=True, field_value="hello world")
    result = await watchdog._input_text_element_node_impl(
        make_self(cdp), make_node(tag="input"), "hello", clear=True
    )
    assert original_calls == ["type:hello"]
    assert result == {"from": "original-type"}
    assert "js_type" not in cdp.calls


async def test_swallowed_typing_is_reset_via_js(monkeypatch, patched_watchdog):
    watchdog, original_calls = patched_watchdog
    monkeypatch.delenv("CROWDTEST_CLICK_MODE", raising=False)
    await ensure_reliable_clicks()

    cdp = FakeCDP(witness_saw_click=True, field_value="")  # field stayed empty
    result = await watchdog._input_text_element_node_impl(
        make_self(cdp), make_node(tag="input"), "hello", clear=True
    )
    assert original_calls == ["type:hello"]
    assert "js_type" in cdp.calls
    assert result is None


def test_history_digest_collects_thoughts_and_content():
    history = SimpleNamespace(
        model_thoughts=lambda: [
            SimpleNamespace(
                evaluation_previous_goal="clicked login",
                memory="cart is broken",
                next_goal="give up",
            )
        ],
        extracted_content=lambda: ["Clicked button add-to-cart"],
    )
    digest = _history_digest(history)
    assert "cart is broken" in digest
    assert "Clicked button add-to-cart" in digest


async def test_salvage_report_converts_prose_via_llm():
    report = {
        "goal_achieved": False,
        "satisfaction_score": 2,
        "summary": "Cart was broken.",
        "findings": [],
    }

    class FakeLLM:
        async def ainvoke(self, messages):
            assert "Cart never updated" in messages[0].content
            return SimpleNamespace(completion=json.dumps(report))

    data = await _salvage_report("Cart never updated no matter what.", FakeLLM)
    assert data == report


async def test_salvage_report_rejects_empty_answer():
    with pytest.raises(ValueError):
        await _salvage_report("   ", lambda: None)
