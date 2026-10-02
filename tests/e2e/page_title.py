"""Browser geometry and retained evidence for shared page heading rows."""

import json


TITLE_WIDTHS = (320, 360, 390, 430, 575, 576, 767, 768, 1024, 1280, 1440)


def assert_page_top_gap(test, selector, label, expected=24):
    test.page.evaluate("document.fonts.ready")
    geometry = test.page.locator(selector).evaluate("""e => ({
      topGap: e.getBoundingClientRect().top - document.querySelector('.navbar').getBoundingClientRect().bottom,
      viewport: innerWidth,
    })""")
    test.assertAlmostEqual(geometry["topGap"], expected, delta=1, msg=(label, geometry))
    artifacts = test._artifact_dir()
    artifacts.mkdir(parents=True, exist_ok=True)
    test.page.screenshot(path=str(artifacts / f"{label}.png"), animations="disabled")
    (artifacts / f"{label}.html").write_text(test.page.content(), encoding="utf-8")
    (artifacts / f"{label}.json").write_text(json.dumps(geometry, indent=2) + "\n", encoding="utf-8")


def assert_page_title_row(test, label):
    test.page.evaluate("document.fonts.ready")
    geometry = test.page.locator(".page-title-row").evaluate("""row => {
      const rect = row.getBoundingClientRect();
      const content = [...row.parentElement.querySelectorAll('.card')]
        .filter(e => e.getClientRects().length && e.getBoundingClientRect().top >= rect.bottom)
        .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
      const navbar = document.querySelector('.navbar').getBoundingClientRect();
      const nodes = [...row.querySelectorAll('h1, .page-title-back, .page-title-action')];
      return {
        row: rect.toJSON(),
        viewport: document.documentElement.clientWidth,
        documentWidth: document.documentElement.scrollWidth,
        topGap: rect.top - navbar.bottom,
        bottomGap: content.getBoundingClientRect().top - rect.bottom,
        items: nodes.map(node => {
          const box = node.getBoundingClientRect();
          const range = document.createRange();
          range.selectNodeContents(node);
          return {
            text: node.textContent.trim(),
            isTitle: node.tagName === 'H1',
            box: box.toJSON(),
            centerY: box.top + box.height / 2,
            scrollWidth: node.scrollWidth,
            clientWidth: node.clientWidth,
            textRects: [...range.getClientRects()].map(r => r.toJSON()),
          };
        }),
      };
    }""")
    row = geometry["row"]
    test.assertAlmostEqual(geometry["topGap"], 24, delta=1, msg=(label, geometry))
    test.assertAlmostEqual(geometry["bottomGap"], geometry["topGap"], delta=1, msg=(label, geometry))
    test.assertGreaterEqual(len(geometry["items"]), 2, label)
    title = next(item for item in geometry["items"] if item["isTitle"])
    title_center = (title["box"]["left"] + title["box"]["right"]) / 2
    test.assertLessEqual(abs(title_center - geometry["viewport"] / 2), 1, (label, geometry))
    for text in title["textRects"]:
        test.assertLessEqual(abs((text["left"] + text["right"]) / 2 - geometry["viewport"] / 2), 1, (label, title))
    for item in geometry["items"]:
        box = item["box"]
        test.assertGreater(box["width"], 0, (label, item))
        test.assertLessEqual(abs(item["centerY"] - (row["top"] + row["height"] / 2)), 1, (label, item))
        test.assertGreaterEqual(box["left"], row["left"] - 1, (label, item))
        test.assertLessEqual(box["right"], row["right"] + 1, (label, item))
        test.assertLessEqual(item["scrollWidth"], item["clientWidth"] + 1, (label, item))
        for text in item["textRects"]:
            test.assertGreaterEqual(text["left"], box["left"] - 1, (label, item))
            test.assertLessEqual(text["right"], box["right"] + 1, (label, item))
    ordered = sorted(geometry["items"], key=lambda item: item["box"]["left"])
    for left, right in zip(ordered, ordered[1:]):
        test.assertLessEqual(left["box"]["right"], right["box"]["left"], (label, geometry))
    test.assertLessEqual(geometry["documentWidth"], geometry["viewport"] + 1, label)
    artifact_dir = test._artifact_dir()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    test.page.screenshot(path=str(artifact_dir / f"{label}.png"), animations="disabled")
    (artifact_dir / f"{label}.html").write_text(test.page.content(), encoding="utf-8")
    (artifact_dir / f"{label}.json").write_text(json.dumps(geometry, indent=2) + "\n", encoding="utf-8")
