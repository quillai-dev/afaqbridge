"""Collect every translatable source string of the application_office app (python _(), JS __()/portal list,
DocType JSON labels/options/descriptions, workflow status labels, shipped default texts).
Usage: python scripts/extract_messages.py [--missing]  (--missing: only strings absent from Frappe/ERPNext ar.po)"""
import ast, glob, json, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
APP = os.path.join(ROOT, "apps/application_office/application_office")
UP = os.path.join(ROOT, "upstream")


def python_msgs():
    out = {}
    for f in glob.glob(APP + "/**/*.py", recursive=True):
        if "/tests/" in f:
            continue
        for node in ast.walk(ast.parse(open(f, encoding="utf8").read())):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("_", "__") and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                out[node.args[0].value] = os.path.relpath(f, APP)
    return out


def js_msgs():
    out = {}
    for f in glob.glob(APP + "/public/js/*.js"):
        for m in re.finditer(r'\b__\(("(?:[^"\\]|\\.)*")', open(f, encoding="utf8").read()):
            out[json.loads(m.group(1))] = os.path.relpath(f, APP)
    return out


def html_msgs():
    out = {}
    for f in glob.glob(APP + "/www/*.html") + glob.glob(APP + "/templates/**/*.html", recursive=True):
        for m in re.finditer(r'_\("((?:[^"\\]|\\.)*)"\)', open(f, encoding="utf8").read()):
            out[m.group(1)] = os.path.relpath(f, APP)
    return out


def doctype_msgs():
    out = {}
    for f in glob.glob(APP + "/application_office/doctype/*/*.json"):
        d = json.load(open(f, encoding="utf8"))
        rel = os.path.relpath(f, APP)
        out[d["name"]] = rel
        for k in ("description",):
            if d.get(k):
                out[d[k]] = rel
        for fld in d.get("fields", []):
            for k in ("label", "description"):
                if fld.get(k):
                    out[fld[k]] = rel
            if fld.get("fieldtype") == "Select":
                for o in (fld.get("options") or "").split("\n"):
                    if o.strip():
                        out[o.strip()] = rel
    out["Application Office"] = "modules.txt"
    return out


def label_msgs():
    sys.path.insert(0, ROOT + "/apps/application_office")
    src = open(APP + "/workflow.py", encoding="utf8").read()
    m = re.search(r"CUSTOMER_STATUS_LABELS = (\{.*?\n\})", src, re.S)
    return {v: "workflow.py" for v in ast.literal_eval(m.group(1)).values()}


def default_texts():
    src = open(APP + "/install.py", encoding="utf8").read()
    import ast as _a
    tree = _a.parse(src)
    out = {}
    for n in tree.body:
        if isinstance(n, _a.Assign) and getattr(n.targets[0], "id", "") in ("DEFAULT_DISCLAIMER", "DEFAULT_SENSITIVE_CONSENT"):
            val = _a.literal_eval(n.value)
            out[re.sub(r"<[^>]+>", "", val)] = "install.py"
    return out


def all_msgs():
    out = {}
    for fn in (python_msgs, js_msgs, html_msgs, doctype_msgs, label_msgs, default_texts):
        out.update(fn())
    return out


def upstream_translated():
    import polib
    have = {}
    for p in (UP + "/frappe/frappe/locale/ar.po", UP + "/erpnext/erpnext/locale/ar.po"):
        if os.path.exists(p):
            for e in polib.pofile(p):
                if e.msgstr and not e.msgctxt:
                    have[e.msgid] = e.msgstr
    return have


if __name__ == "__main__":
    msgs = all_msgs()
    if "--missing" in sys.argv:
        have = upstream_translated()
        miss = [m for m in msgs if m not in have]
        print(json.dumps(miss, ensure_ascii=False, indent=0))
        print(len(miss), "missing of", len(msgs), file=sys.stderr)
    else:
        print(len(msgs))
