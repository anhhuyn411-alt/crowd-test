"""Make every click land, even where CDP mouse events silently vanish.

On some machines (observed on Windows with Chrome 149/150 headless), the
``Input.dispatchMouseEvent`` commands browser-use issues for clicks are
acknowledged by Chromium but never delivered to the page — reliably so after
the first click-initiated navigation on a real site. Typing works, JavaScript
works — only synthetic mouse clicks vanish. The result is poison for a
testing tool: every persona unanimously convicts every button on the site as
broken, because from where they stand every button IS broken.

Guessing which environments are affected is a losing game, so we don't:
every click gets a witness. Before browser-use dispatches its coordinate
click we plant a one-shot capture listener in the page; afterwards we ask it
whether any mousedown/click arrived (a page navigation also counts — the
click clearly landed). If nothing arrived, we re-fire the click as a
synthesized DOM event sequence (pointerdown → mousedown → pointerup →
mouseup → click()), which is delivered even where CDP input is not.

Override with ``CROWDTEST_CLICK_MODE``: ``auto`` (default, verify + fallback),
``js`` (always synthesize DOM events, skip CDP clicks), or ``cdp`` (leave
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

    DefaultActionWatchdog._click_element_node_impl = witnessed_click_impl
    _patched = True


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


async def _js_click(cdp_session, element_node) -> None:
    """Deliver a click as a synthesized DOM event sequence on the node."""
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
    object_id = result["object"]["objectId"]
    await cdp_session.cdp_client.send.Runtime.callFunctionOn(
        params={"functionDeclaration": _JS_CLICK, "objectId": object_id},
        session_id=cdp_session.session_id,
    )
    await asyncio.sleep(0.05)
