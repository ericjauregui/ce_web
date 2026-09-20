"""Conservative Bootstrap subset. Run: uv run --with tinycss2 python scripts/build_site_css.py.

Keep rules with functional/escaped selectors and all framework state classes.
Never modify declarations or their order. A source manifest enables safe fallback
when templates, scripts, or custom styles change before the next rebuild.
"""
from pathlib import Path
import json
import re
import sys
import tinycss2
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from domains.file_cache import get_path_version
from domains.stylesheets import css_inputs

ROOT = Path(__file__).resolve().parents[1]

def build():
    sources = css_inputs(ROOT)
    words = set(re.findall(r'[\w-]+', '\n'.join(p.read_text() for p in sources)))
    words.update('show showing hide hiding collapse collapsing active disabled fade modal-open modal-backdrop offcanvas-backdrop was-validated is-valid is-invalid focus'.split())
    def keep(selector):
        if '\\' in selector or '(' in selector:
            return True
        return all(name in words for name in re.findall(r'\.([a-zA-Z_][\w-]*)', selector))
    def prune(rules):
        output = []
        for rule in rules:
            if rule.type == 'qualified-rule':
                selectors = tinycss2.serialize(rule.prelude)
                # Functional selectors can contain commas; keep the entire rule.
                selected = selectors if '(' in selectors else ','.join(s for s in selectors.split(',') if keep(s))
                if selected.strip():
                    output.append(selected + '{' + tinycss2.serialize(rule.content) + '}')
            elif rule.type == 'at-rule':
                if rule.content is not None and rule.lower_at_keyword in ('media', 'supports', 'layer'):
                    body = prune(tinycss2.parse_rule_list(rule.content, skip_comments=True, skip_whitespace=True))
                    if body:
                        output.append('@' + rule.at_keyword + ' ' + tinycss2.serialize(rule.prelude).strip() + '{' + body + '}')
                else:
                    output.append(rule.serialize())
        return ''.join(output)
    original = ROOT / 'static/vendor/bootstrap/bootstrap.min.css'
    result = '/*! Bootstrap v5.3.3 | Copyright 2011-2024 The Bootstrap Authors | MIT License | https://github.com/twbs/bootstrap/blob/main/LICENSE */\n' + prune(tinycss2.parse_stylesheet(original.read_text(), skip_comments=True, skip_whitespace=True))
    target = ROOT / 'static/css/bootstrap.site.min.css'
    target.write_text(result)
    manifest = {str(p.relative_to(ROOT)): get_path_version(p) for p in [*sources, original, target]}
    (ROOT / 'static/css/bootstrap.site.manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Bootstrap: {original.stat().st_size:,} -> {target.stat().st_size:,} bytes')

if __name__ == '__main__':
    build()
