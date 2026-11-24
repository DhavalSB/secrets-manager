"""The few HTML pages people see in a browser: login result and API docs.

Styled after dhavalbiradar.com: dark-only Flexoki palette, light-weight Inter,
an orange wordmark with `/ section` breadcrumbs, and a narrow 720px column.
"""

from html import escape

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,100..900&display=swap">'
)

# Orange "sm" on near-black, like the "db" favicon on the personal site.
FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
    "%3Crect width='100' height='100' fill='%23100F0F'/%3E"
    "%3Ctext x='50' y='66' text-anchor='middle' font-family='Inter,sans-serif' font-size='52' "
    "font-weight='300' letter-spacing='-2' fill='%23EC8B49'%3Esm%3C/text%3E%3C/svg%3E"
)

THEME_CSS = """
:root {
  --bg: #100F0F;          /* flexoki black */
  --surface: #1C1B1A;     /* flexoki 950 */
  --surface-2: #282726;   /* flexoki 900 */
  --border: #282726;
  --divider: #222;
  --text: #CECDC3;        /* flexoki 200 */
  --muted: #878580;       /* flexoki 500 */
  --faint: #575653;       /* flexoki 700 */
  --accent: #EC8B49;      /* flexoki orange 300 */
  --accent-strong: #DA702C;
  --red: #D14D41;
  --green: #879A39;
  --blue: #4385BE;
  --yellow: #D0A215;
  --purple: #8B7EC8;
  --code-bg: #333;
  color-scheme: dark;
}
* { box-sizing: border-box; }
html { background: var(--bg); }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  margin: auto;
  padding: 20px;
  max-width: 720px;
  background: var(--bg);
  color: var(--text);
  line-height: 1.4;
  -webkit-font-smoothing: antialiased;
}
a { color: var(--accent); text-decoration: none; transition: color 100ms cubic-bezier(0.4, 0, 0.2, 1); }
a:hover { color: var(--accent-strong); }
code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.9em;
  padding: 2px 5px;
  background: var(--code-bg);
  color: #f2f2f2;
}
header {
  padding: 1rem 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 250;
}
.crumbs { display: flex; align-items: baseline; gap: 0.3rem; font-size: 1.25rem; font-weight: 300; }
.crumbs .mark { color: var(--accent); }
.crumbs .sep, .crumbs .here { color: var(--text); }
header nav { display: flex; gap: 1rem; }
header nav a { color: var(--text); font-weight: 250; font-size: 1.05rem; }
header nav a:hover { color: var(--muted); }
hr { border: none; border-top: 1px solid var(--divider); margin: 2rem 0; }
footer { color: var(--muted); font-weight: 300; font-size: 0.95rem; }
footer a { color: var(--muted); }
footer a:hover { color: var(--text); }

.notice { padding: 3.5rem 0 1rem; }
.notice h1 { font-weight: 400; font-size: clamp(1.6rem, 3vw, 2.1rem); line-height: 1.15; margin: 0 0 0.8rem; }
.notice h1.ok { color: var(--text); }
.notice h1.error { color: var(--red); }
.notice p { color: var(--muted); font-weight: 300; margin: 0.4rem 0; }
.notice p strong { color: var(--text); font-weight: 400; }
.notice .hint { margin-top: 1.6rem; }
"""


def _header(section: str, nav: str = "") -> str:
    return (
        '<header><div class="crumbs">'
        '<a class="mark" href="/docs">sm</a>'
        f'<span class="sep">/</span><span class="here">{escape(section)}</span>'
        f"</div><nav>{nav}</nav></header>"
    )


FOOTER = '<footer><hr><p>secretsmanager · <a href="/docs">api docs</a></p></footer>'


def page(section: str, body: str, *, title: str, nav: str = "") -> str:
    """A full page in the site style. `body` is trusted HTML; escape any user input first."""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
{FONT_LINK}
<style>{THEME_CSS}</style>
</head><body>
{_header(section, nav)}
<main>{body}</main>
{FOOTER}
</body></html>"""


def login_result(login: str = "", error: str = "") -> str:
    if error:
        body = (
            '<section class="notice">'
            '<h1 class="error">login failed</h1>'
            f"<p>{escape(error)}</p>"
            '<p class="hint">run <code>sm login</code> to try again.</p>'
            "</section>"
        )
        return page("login", body, title="sm · login failed")
    who = f" as <strong>{escape(login)}</strong>" if login else ""
    body = (
        '<section class="notice">'
        '<h1 class="ok">you\'re logged in.</h1>'
        f"<p>signed in with github{who}. your session is saved, so you stay logged in across restarts.</p>"
        '<p class="hint">you can close this tab and go back to your terminal.</p>'
        "</section>"
    )
    return page("login", body, title="sm · logged in")


# ---------------------------------------------------------------------------
# API docs: FastAPI's Swagger UI, recolored to match.
# ---------------------------------------------------------------------------

SWAGGER_CSS = """
body.docs { max-width: 960px; }
.swagger-ui { font-family: inherit; color: var(--text); }
.swagger-ui .topbar { display: none; }
.swagger-ui .wrapper { padding: 0; max-width: none; }
.swagger-ui .information-container { padding: 0; }
.swagger-ui .info { margin: 1.5rem 0 2rem; }
.swagger-ui .info .title { color: var(--text); font-family: inherit; font-weight: 400; font-size: clamp(1.6rem, 3vw, 2.1rem); }
.swagger-ui .info .title small { background: var(--surface-2); top: -4px; }
.swagger-ui .info .title small pre { color: var(--muted); font-family: inherit; }
.swagger-ui .info .title small.version-stamp { background: var(--accent); }
.swagger-ui .info .title small.version-stamp pre { color: var(--bg); }
.swagger-ui .info a, .swagger-ui .info .link { color: var(--accent); }
.swagger-ui .info p, .swagger-ui .info li, .swagger-ui .info table { color: var(--muted); font-family: inherit; font-weight: 300; font-size: 1rem; }
.swagger-ui .info h2, .swagger-ui .info h3 { color: var(--text); font-family: inherit; font-weight: 400; }
.swagger-ui .markdown code, .swagger-ui .renderedMarkdown code {
  background: var(--code-bg); color: #f2f2f2; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; padding: 2px 5px; border-radius: 0;
}
.swagger-ui .markdown pre, .swagger-ui .renderedMarkdown pre { background: var(--surface); padding: 1rem; color: var(--text); }
.swagger-ui .markdown pre code { background: none; padding: 0; }
.swagger-ui .scheme-container { background: transparent; box-shadow: none; padding: 0 0 1rem; border-bottom: 1px solid var(--divider); }
.swagger-ui .opblock-tag {
  color: var(--text); font-family: inherit; font-weight: 400; font-size: 1.3rem; border-bottom: 1px solid var(--divider);
}
.swagger-ui .opblock-tag:hover { background: transparent; }
.swagger-ui .opblock-tag small { color: var(--muted); font-family: inherit; font-weight: 300; }
.swagger-ui h1, .swagger-ui h2, .swagger-ui h3, .swagger-ui h4, .swagger-ui h5,
.swagger-ui label, .swagger-ui .tab li, .swagger-ui .tab li button.tablinks,
.swagger-ui .parameter__name, .swagger-ui .response-col_status, .swagger-ui table thead tr th,
.swagger-ui table thead tr td, .swagger-ui .responses-inner h4, .swagger-ui .responses-inner h5,
.swagger-ui .opblock .opblock-section-header h4, .swagger-ui .opblock-description-wrapper p,
.swagger-ui .opblock-external-docs-wrapper p, .swagger-ui .opblock-title_normal p,
.swagger-ui .response-col_links, .swagger-ui .model, .swagger-ui .model-title,
.swagger-ui section.models h4, .swagger-ui .prop-format, .swagger-ui .dialog-ux .modal-ux-header h3,
.swagger-ui .dialog-ux .modal-ux-content p, .swagger-ui .dialog-ux .modal-ux-content h4,
.swagger-ui .auth-container h4, .swagger-ui .auth-container h6, .swagger-ui .btn, .swagger-ui .servers-title,
.swagger-ui .parameters-col_description, .swagger-ui .response-col_description, .swagger-ui .renderedMarkdown p {
  color: var(--text); font-family: inherit;
}
.swagger-ui .parameter__type, .swagger-ui .parameter__in, .swagger-ui .prop-type, .swagger-ui .parameter__deprecated,
.swagger-ui .opblock .opblock-summary-description, .swagger-ui .model .property.primitive, .swagger-ui .response-control-media-type__accept-message {
  color: var(--muted); font-family: inherit;
}
.swagger-ui .parameter__name.required::after, .swagger-ui .parameter__name.required span { color: var(--red); }
.swagger-ui .prop-type { color: var(--purple); }

/* endpoint cards */
.swagger-ui .opblock { border-radius: 6px; box-shadow: none; background: var(--surface); border: 1px solid var(--border); margin: 0 0 0.6rem; }
.swagger-ui .opblock .opblock-summary { border: none; padding: 0.45rem 0.6rem; }
.swagger-ui .opblock .opblock-summary-method { border-radius: 4px; font-family: inherit; font-weight: 500; min-width: 72px; color: var(--bg); text-shadow: none; }
.swagger-ui .opblock .opblock-summary-path, .swagger-ui .opblock .opblock-summary-path__deprecated {
  color: var(--text); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.92rem; font-weight: 400;
}
.swagger-ui .opblock .opblock-section-header { background: var(--surface-2); box-shadow: none; }
.swagger-ui .opblock-body, .swagger-ui .opblock .opblock-section { background: transparent; }
.swagger-ui .opblock.opblock-get    { border-color: rgba(67,133,190,.45); background: rgba(67,133,190,.07); }
.swagger-ui .opblock.opblock-post   { border-color: rgba(135,154,57,.45); background: rgba(135,154,57,.07); }
.swagger-ui .opblock.opblock-put    { border-color: rgba(218,112,44,.45); background: rgba(218,112,44,.07); }
.swagger-ui .opblock.opblock-delete { border-color: rgba(209,77,65,.45);  background: rgba(209,77,65,.07); }
.swagger-ui .opblock.opblock-patch  { border-color: rgba(139,126,200,.45); background: rgba(139,126,200,.07); }
.swagger-ui .opblock.opblock-get .opblock-summary-method    { background: var(--blue); }
.swagger-ui .opblock.opblock-post .opblock-summary-method   { background: var(--green); }
.swagger-ui .opblock.opblock-put .opblock-summary-method    { background: var(--accent-strong); }
.swagger-ui .opblock.opblock-delete .opblock-summary-method { background: var(--red); }
.swagger-ui .opblock.opblock-patch .opblock-summary-method  { background: var(--purple); }
.swagger-ui .opblock.opblock-get .tab-header .tab-item.active h4 span::after { background: var(--blue); }
.swagger-ui .opblock.opblock-post .tab-header .tab-item.active h4 span::after { background: var(--green); }
.swagger-ui .opblock.opblock-put .tab-header .tab-item.active h4 span::after { background: var(--accent-strong); }
.swagger-ui .opblock.opblock-delete .tab-header .tab-item.active h4 span::after { background: var(--red); }

/* icons (chevrons, locks, copy) */
.swagger-ui svg:not(:root) { fill: var(--muted); }
.swagger-ui .authorization__btn svg, .swagger-ui .opblock-summary-control svg { fill: var(--muted); }
.swagger-ui .authorization__btn.unlocked svg { fill: var(--faint); }
.swagger-ui .copy-to-clipboard { background: var(--surface-2); }
.swagger-ui .copy-to-clipboard button { filter: invert(0.8); }

/* forms and buttons */
.swagger-ui input[type=text], .swagger-ui input[type=password], .swagger-ui input[type=search], .swagger-ui input[type=email],
.swagger-ui input[type=file], .swagger-ui textarea, .swagger-ui select {
  background: var(--bg); color: var(--text); border: 1px solid var(--surface-2); border-radius: 4px; box-shadow: none; font-family: inherit;
}
.swagger-ui textarea { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.swagger-ui input::placeholder, .swagger-ui textarea::placeholder { color: var(--faint); }
.swagger-ui select { background-image: none; }
.swagger-ui .btn { background: transparent; border: 1px solid var(--faint); border-radius: 4px; box-shadow: none; font-weight: 400; }
.swagger-ui .btn:hover { box-shadow: none; border-color: var(--muted); }
.swagger-ui .btn.authorize { color: var(--accent); border-color: var(--accent); }
.swagger-ui .btn.authorize svg { fill: var(--accent); }
.swagger-ui .btn.execute { background: var(--accent); border-color: var(--accent); color: var(--bg); }
.swagger-ui .btn.execute:hover { background: var(--accent-strong); }
.swagger-ui .btn.cancel { color: var(--red); border-color: var(--red); }
.swagger-ui .btn-group .btn.btn-clear { color: var(--text); }
.swagger-ui .try-out__btn { color: var(--text); }

/* code and responses */
.swagger-ui .highlight-code > .microlight, .swagger-ui .microlight, .swagger-ui pre.microlight {
  background: #1C1B1A !important; color: var(--text) !important; border-radius: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.swagger-ui .responses-inner h4, .swagger-ui .response-col_status .response-undocumented { color: var(--muted); }
.swagger-ui table tbody tr td { border-color: var(--divider); }
.swagger-ui .responses-table .response { border-color: var(--divider); }
.swagger-ui .loading-container .loading::after { color: var(--muted); }

/* schemas */
.swagger-ui section.models { border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }
.swagger-ui section.models.is-open h4 { border-bottom: 1px solid var(--divider); }
.swagger-ui section.models .model-container { background: var(--surface-2); border-radius: 4px; }
.swagger-ui section.models .model-container:hover { background: var(--surface-2); }
.swagger-ui .model-box { background: transparent; }
.swagger-ui .model .property { color: var(--muted); }
.swagger-ui .model-toggle::after { filter: invert(0.7); }
.swagger-ui .json-schema-2020-12, .swagger-ui .json-schema-2020-12-head, .swagger-ui .json-schema-2020-12__title,
.swagger-ui .json-schema-2020-12-keyword__name, .swagger-ui .json-schema-2020-12-keyword__value { color: var(--text) !important; }
.swagger-ui .json-schema-2020-12-body { border-color: var(--divider); }
.swagger-ui .json-schema-2020-12-accordion, .swagger-ui .json-schema-2020-12-expand-deep-button { background: transparent; color: var(--muted); }
.swagger-ui .json-schema-2020-12__attribute--primary { color: var(--purple) !important; }

/* small fixes over Swagger's defaults */
.swagger-ui pre code, .swagger-ui .microlight code, .swagger-ui .highlight-code code {
  background: none !important; padding: 0; color: inherit;
}
.swagger-ui .opblock-summary-control:focus, .swagger-ui .opblock .opblock-summary:focus,
.swagger-ui button:focus { outline: none; }
.swagger-ui .opblock-summary-control:focus-visible, .swagger-ui button:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
.swagger-ui .response-control-media-type--accept-controller select,
.swagger-ui .response-control-media-type__accept-message code { border-color: var(--surface-2) !important; }
.swagger-ui .btn.authorize svg, .swagger-ui .btn.authorize svg path,
.swagger-ui .authorization__btn svg, .swagger-ui .authorization__btn svg path { fill: var(--accent) !important; }
.swagger-ui .authorization__btn.unlocked svg, .swagger-ui .authorization__btn.unlocked svg path { fill: var(--faint) !important; }

/* authorize dialog */
.swagger-ui .dialog-ux .backdrop-ux { background: rgba(16,15,15,.8); }
.swagger-ui .dialog-ux .modal-ux { background: var(--surface); border: 1px solid var(--surface-2); box-shadow: none; }
.swagger-ui .dialog-ux .modal-ux-header { border-bottom: 1px solid var(--divider); }
.swagger-ui .dialog-ux .modal-ux-header .close-modal svg { fill: var(--muted); }
.swagger-ui .auth-container { border-color: var(--divider); }
.swagger-ui .scopes h2, .swagger-ui .scopes h2 a { color: var(--text); }
"""


def docs_page(openapi_url: str) -> str:
    """Swagger UI inside the site layout: our header, fonts and palette."""
    from fastapi.openapi.docs import get_swagger_ui_html

    swagger = get_swagger_ui_html(
        openapi_url=openapi_url,
        title="sm · api docs",
        swagger_favicon_url=FAVICON,
        swagger_ui_parameters={
            "syntaxHighlight": {"theme": "obsidian"},
            "defaultModelsExpandDepth": 0,  # schemas collapsed until clicked
            "docExpansion": "list",
            "persistAuthorization": True,  # keep a pasted token across reloads
            "tryItOutEnabled": False,
        },
    ).body.decode()
    head_extra = f"{FONT_LINK}<style>{THEME_CSS}{SWAGGER_CSS}</style>"
    header = _header("docs")
    swagger = swagger.replace("</head>", head_extra + "</head>", 1)
    swagger = swagger.replace("<body>", f'<body class="docs">{header}', 1)
    return swagger.replace("</body>", FOOTER.replace('· <a href="/docs">api docs</a>', "") + "</body>", 1)
