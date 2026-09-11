"""Real Chromium/UI plumbing smoke test; this is not a live Onshape test."""
import asyncio

from playwright.async_api import async_playwright

from onshape_mcp import sketch_state
from onshape_mcp.config import settings
from onshape_mcp.driver import OnshapeDriver
from onshape_mcp.interactive import InteractiveSession


def test_real_browser_preview_edit_and_immutable_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'journal_dir', tmp_path)

    async def read(driver):
        return {'features': [], 'featureStates': {}}
    monkeypatch.setattr(sketch_state, 'read_features', read)

    async def exercise():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={'width': 800, 'height': 600})
                await page.set_content('''<canvas width="700" height="500"></canvas>
                  <input class="os-canvas-text-edit" value="25 mm" style="display:none">
                  <script>
                  const canvas=document.querySelector('canvas'), input=document.querySelector('input');
                  canvas.ondblclick=()=>{input.style.display='block';input.focus()};
                  input.onkeydown=e=>{if(e.key==='Enter'){window.accepted=input.value;input.style.display='none'}};
                  </script>''')
                d = OnshapeDriver()
                d._page = page
                s = InteractiveSession(d, tmp_path / 'requests')
                frame = await s.frame()
                first_bytes = __import__('pathlib').Path(frame['screenshot']).read_bytes()
                target = await s.select('width label', 100, 100, frame['frame_id'])
                assert await page.locator('#onshape-mcp-target').inner_text() == 'width label'
                result = await s.edit(target['handle'], 'dimension', True, value_mm=35)
                assert result['ok'] and not result['verified']
                assert await page.evaluate('window.accepted') == '35 mm'
                after = await s.frame()
                assert frame['screenshot'] != after['screenshot']
                assert __import__('pathlib').Path(frame['screenshot']).read_bytes() == first_bytes
                assert await page.locator('#onshape-mcp-target').count() == 0
            finally:
                await browser.close()
    asyncio.run(exercise())
