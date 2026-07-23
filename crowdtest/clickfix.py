"""Make every click and keystroke land, even where CDP input silently vanishes.

On some machines (observed on Windows with Chrome 149/150 headless), the
``Input.dispatch*Event`` commands browser-use issues are acknowledged by
Chromium but never delivered to the page — reliably so after the first
click-initiated navigation on a real site. JavaScript keeps working — only
synthetic input vanishes. The result is poison for a testing tool: every
persona unanimously convicts every button and form on the site as broken,
because from where they stand they ARE broken.

Guessing which environments are affected is a losing game, so we don't —
every interaction gets verified:

- **Clicks**: before browser-use dispatches its coordinate click we plant a
  one-shot capture listener in the page; afterwards we ask it whether any
  mousedown/click arrived (a page navigation also counts — the click clearly
  landed). If nothing arrived, the click is re-fired as a synthesized DOM
  event sequence (pointerdown → mousedown → pointerup → mouseup → click()).
- **Typing**: after browser-use types, we read the field's actual value; if
  the text never arrived, we set it through the framework-native value setter
  and dispatch input/change events.

Override with ``CROWDTEST_CLICK_MODE``: ``auto`` (default, verify + fallback),
``js`` (always synthesize DOM events, skip CDP input), or ``cdp`` (leave
browser-use untouched).
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid

logger = logging.getLogger("crowdtest")

_patched = False

_ARM_WITNESS = """
window.__ct_token = '{token}';
window.__ct_seen = false;
(function () {{
  const seen = () => {{ window.__ct_seen = true; }};
  document.addEventListener('mousedown', seen, {{capture: true, once: true}});
  document.addEventListener('click', seen, {{capture: true, once: true}});
}})();
'armed'
"""

_READ_WITNESS = "JSON.stringify([window.__ct_token ?? null, window.__ct_seen ?? null])"

_JS_CLICK = """
function() {
  const o = {bubbles: true, cancelable: true, view: window};
  this.dispatchEvent(new PointerEvent('pointerdown', o));
  this.dispatchEvent(new MouseEvent('mousedown', o));
  this.dispatchEvent(new PointerEvent('pointerup', o));
  this.dispatchEvent(new MouseEvent('mouseup', o));
  this.click();
}
"""

_JS_READ_VALUE = """
function() {
  const t = (this.tagName || '').toLowerCase();
  if (t === 'input' || t === 'textarea') return String(this.value ?? '');
  return String(this.textContent ?? '');
}
"""

# Set the value through the native setter so frameworks that hijack the value
# property (React does) see the change, then announce it like a user would.
_JS_TYPE = """
function(text, clear) {
  this.focus();
  const t = (this.tagName || '').toLowerCase();
  if (t === 'input' || t === 'textarea') {
    const proto = t === 'textarea'
      ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    const v = clear ? text : String(this.value ?? '') + text;
    if (desc && desc.set) desc.set.call(this, v); else this.value = v;
  } else if (this.isContentEditable) {
    this.textContent = clear ? text : String(this.textContent ?? '') + text;
  }
  this.dispatchEvent(new Event('input', {bubbles: true}));
  this.dispatchEvent(new Event('change', {bubbles: true}));
}
"""


async def ensure_reliable_clicks(headless: bool = True) -> bool:
    """Install the click witness/fallback patch once per process.

    Returns True when the patch is active.
    """
    mode = os.environ.get("CROWDTEST_CLICK_MODE", "auto").lower()
    if mode == "cdp":
        return False
    _apply_click_patch(js_only=mode == "js")
    return True


def _apply_click_patch(js_only: bool = False) -> None:
    global _patched
    if _patched:
        return
    from browser_use.browser.watchdogs.default_action_watchdog import (
        DefaultActionWatchdog,
    )

    original = DefaultActionWatchdog._click_element_node_impl

    async def witnessed_click_impl(self, element_node):
        tag = element_node.tag_name.lower() if element_node.tag_name else ""
        typ = (
            element_node.attributes.get("type", "").lower()
            if element_node.attributes
            else ""
        )
        # <select> and file inputs have dedicated validation upstream
        if tag == "select" or (tag == "input" and typ == "file"):
            return await original(self, element_node)

        cdp_session = await self.browser_session.cdp_client_for_node(element_node)

        if not js_only:
            token = uuid.uuid4().hex
            armed = await _evaluate(
                cdp_session, _ARM_WITNESS.format(token=token)
            ) == "armed"
            result = await original(self, element_node)
            if not armed:
                return result
            await asyncio.sleep(0.15)
            state = await _evaluate(cdp_session, _READ_WITNESS)
            # Witness gone (navigation) or witness saw the click: it landed.
            if state is None or f'["{token}",false]' != state:
                return result
            logger.debug(
                "CDP click on <%s> was not delivered - refiring as DOM events", tag
            )

        await _js_click(cdp_session, element_node)
        return None

    original_type = DefaultActionWatchdog._input_text_element_node_impl

    async def witnessed_type_impl(
        self, element_node, text, clear=True, is_sensitive=False
    ):
        cdp_session = await self.browser_session.cdp_client_for_node(element_node)

        if not js_only:
            result = None
            try:
                result = await original_type(
                    self, element_node, text, clear=clear, is_sensitive=is_sensitive
                )
            except Exception:
                pass  # fall through to the JS path
            else:
                value = await _call_on_node(cdp_session, element_node, _JS_READ_VALUE)
                if value is None or _typed_text_arrived(value, text, clear):
                    return result
            logger.debug("CDP typing was not delivered - setting value via JS")

        await _js_type(cdp_session, element_node, text, clear)
        return None

    DefaultActionWatchdog._click_element_node_impl = witnessed_click_impl
    DefaultActionWatchdog._input_text_element_node_impl = witnessed_type_impl
    _patched = True


def _typed_text_arrived(value: str, text: str, clear: bool) -> bool:
    """Did the field end up holding what the user typed?"""
    if not text:
        return value == "" if clear else True
    return text in str(value)


async def _evaluate(cdp_session, expression: str):
    """Evaluate JS in the page; None means the page couldn't answer."""
    try:
        res = await cdp_session.cdp_client.send.Runtime.evaluate(
            params={"expression": expression, "returnByValue": True},
            session_id=cdp_session.session_id,
        )
        return res.get("result", {}).get("value")
    except Exception:
        return None


async def _resolve_object_id(cdp_session, element_node) -> str:
    try:
        await cdp_session.cdp_client.send.DOM.scrollIntoViewIfNeeded(
            params={"backendNodeId": element_node.backend_node_id},
            session_id=cdp_session.session_id,
        )
    except Exception:
        pass
    result = await cdp_session.cdp_client.send.DOM.resolveNode(
        params={"backendNodeId": element_node.backend_node_id},
        session_id=cdp_session.session_id,
    )
    return result["object"]["objectId"]


async def _call_on_node(cdp_session, element_node, declaration: str, args=()):
    """Call a JS function on the node; None means the call didn't go through."""
    try:
        object_id = await _resolve_object_id(cdp_session, element_node)
        res = await cdp_session.cdp_client.send.Runtime.callFunctionOn(
            params={
                "functionDeclaration": declaration,
                "objectId": object_id,
                "arguments": [{"value": a} for a in args],
                "returnByValue": True,
            },
            session_id=cdp_session.session_id,
        )
        return res.get("result", {}).get("value")
    except Exception:
        return None


async def _js_click(cdp_session, element_node) -> None:
    """Deliver a click as a synthesized DOM event sequence on the node."""
    object_id = await _resolve_object_id(cdp_session, element_node)
    await cdp_session.cdp_client.send.Runtime.callFunctionOn(
        params={"functionDeclaration": _JS_CLICK, "objectId": object_id},
        session_id=cdp_session.session_id,
    )
    await asyncio.sleep(0.05)


async def _js_type(cdp_session, element_node, text: str, clear: bool) -> None:
    """Set the field's value via JS and announce it with input/change events."""
    object_id = await _resolve_object_id(cdp_session, element_node)
    await cdp_session.cdp_client.send.Runtime.callFunctionOn(
        params={
            "functionDeclaration": _JS_TYPE,
            "objectId": object_id,
            "arguments": [{"value": text}, {"value": bool(clear)}],
        },
        session_id=cdp_session.session_id,
    )
    await asyncio.sleep(0.05)
