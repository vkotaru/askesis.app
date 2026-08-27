"""The login and consent page.

One self-contained HTML document with inline CSS. No SvelteKit, no bundler, no
static assets — the SPA is not in this image and this page must render from a
process that has nothing but Starlette.

**This page is the only place the user ever sees what they are granting.** Claude
shows a connector name and a URL; it does not and cannot enumerate what the
tools return. So the scope list here is written in plain words rather than as a
scope string, and it names the things a person would be surprised by: free-text
notes, mood tags, and body measurements. `askesis:read` means nothing to anyone.
"""

from __future__ import annotations

import html

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
  background:#f6f7f9; color:#111827; padding:24px;
  font:16px/1.5 ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif; }
.card { background:#fff; border-radius:16px; box-shadow:0 1px 3px rgba(0,0,0,.08),0 8px 24px rgba(0,0,0,.06);
  max-width:460px; width:100%; padding:28px; }
h1 { font-size:20px; margin:0 0 4px; }
.sub { color:#6b7280; font-size:14px; margin:0 0 20px; }
.client { background:#f3f4f6; border-radius:10px; padding:12px 14px; margin-bottom:18px; font-size:14px; }
.client b { display:block; font-size:15px; margin-bottom:2px; }
.client code { font-size:12px; color:#6b7280; word-break:break-all; }
ul { margin:0 0 20px; padding-left:20px; font-size:14px; color:#374151; }
li { margin-bottom:5px; }
label { display:block; font-size:13px; font-weight:600; margin:0 0 6px; }
input { width:100%; padding:10px 12px; border:1px solid #d1d5db; border-radius:9px;
  font-size:15px; margin-bottom:14px; background:#fff; color:inherit; }
input:focus { outline:2px solid #16a34a; outline-offset:1px; border-color:#16a34a; }
button { width:100%; padding:11px; border:0; border-radius:9px; background:#16a34a; color:#fff;
  font-size:15px; font-weight:600; cursor:pointer; }
button:hover { background:#15803d; }
.err { background:#fef2f2; border:1px solid #fecaca; color:#991b1b; padding:10px 12px;
  border-radius:9px; font-size:14px; margin-bottom:16px; }
.warn { background:#fffbeb; border:1px solid #fde68a; color:#92400e; padding:10px 12px;
  border-radius:9px; font-size:13px; margin-bottom:16px; }
.foot { color:#9ca3af; font-size:12px; margin-top:16px; text-align:center; }
@media (prefers-color-scheme: dark) {
  body { background:#0b0f14; color:#e5e7eb; }
  .card { background:#111827; box-shadow:none; border:1px solid #1f2937; }
  .client { background:#0b0f14; } input { background:#0b0f14; border-color:#374151; }
  ul { color:#9ca3af; }
}
"""

#: Written for a person, not for a scope registry. Each line is something the
#: connector can actually read back.
_GRANTS = [
    "Daily logs — weight, sleep, steps, water, caffeine, <b>mood tags</b> and your <b>free-text notes</b>",
    "Meals and nutrition — what you ate, calories, macros and meal descriptions",
    "Activities — workouts, durations, distances, exercise sets and their notes",
    "<b>Body measurements</b> — waist, hips, chest and the rest, with their history",
    "Training plans and your weekly targets",
    "Your name, unit preferences and goals",
]


def consent_page(
    *,
    client_name: str,
    redirect_uri: str,
    account_label: str,
    error: str | None = None,
    hidden: dict[str, str],
) -> str:
    """The login + consent form."""
    fields = "".join(
        f'<input type="hidden" name="{html.escape(k)}" value="{html.escape(v)}">'
        for k, v in hidden.items()
    )
    err = f'<div class="err">{html.escape(error)}</div>' if error else ""

    # The MCP spec requires showing the redirect target, and requires an extra
    # warning when it is a loopback address — a local listener can be anything.
    loopback = redirect_uri.startswith(("http://localhost", "http://127.0.0.1"))
    warn = (
        '<div class="warn">This will send your data to an application running on '
        "this machine. Only continue if you started it yourself.</div>"
        if loopback
        else ""
    )
    items = "".join(f"<li>{g}</li>" for g in _GRANTS)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect to Askesis</title><style>{_STYLE}</style></head>
<body><div class="card">
  <h1>Connect to Askesis</h1>
  <p class="sub">Signing in as <b>{html.escape(account_label)}</b></p>
  {err}{warn}
  <div class="client">
    <b>{html.escape(client_name)}</b>
    wants <b>read-only</b> access to your health data.
    <code>{html.escape(redirect_uri)}</code>
  </div>
  <p style="font-size:14px;margin:0 0 8px"><b>It will be able to read:</b></p>
  <ul>{items}</ul>
  <form method="post" autocomplete="on">
    {fields}
    <label for="u">Username or email</label>
    <input id="u" name="username" autocomplete="username" autofocus required>
    <label for="p">Password</label>
    <input id="p" name="password" type="password" autocomplete="current-password" required>
    <button type="submit">Sign in and allow</button>
  </form>
  <p class="foot">It cannot change or delete anything.<br>
  Revoke any time by changing your Askesis password.</p>
</div></body></html>"""


def message_page(title: str, body: str, *, status: str = "error") -> str:
    """A terminal page for a request that cannot proceed to a redirect."""
    cls = "err" if status == "error" else "warn"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{_STYLE}</style></head>
<body><div class="card"><h1>{html.escape(title)}</h1>
<div class="{cls}">{html.escape(body)}</div></div></body></html>"""
