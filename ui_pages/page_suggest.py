import html
import os

import streamlit as st
import streamlit.components.v1 as components

WEB3FORMS_ENDPOINT = "https://api.web3forms.com/submit"


def _get_access_key() -> str:
    try:
        key = st.secrets.get("WEB3FORMS_ACCESS_KEY", "")
    except Exception:
        key = ""
    if not key:
        key = os.environ.get("WEB3FORMS_ACCESS_KEY", "")
    return (key or "").strip()


def render() -> None:
    st.title("✉️ Suggest an article")

    access_key = _get_access_key()
    if not access_key:
        st.error(
            "Email sending isn't configured yet. "
            "Ask the site owner to set WEB3FORMS_ACCESS_KEY in secrets."
        )
        return

    safe_key = html.escape(access_key, quote=True)
    safe_endpoint = html.escape(WEB3FORMS_ENDPOINT, quote=True)

    components.html(
        f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<style>
  body {{
    margin: 0;
    font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, sans-serif;
    color: inherit;
  }}
  form {{ display: flex; flex-direction: column; gap: 12px; }}
  label {{ font-size: 0.9rem; font-weight: 600; }}
  textarea, input[type="text"] {{
    width: 100%;
    box-sizing: border-box;
    padding: 8px 10px;
    border: 1px solid rgba(49, 51, 63, 0.2);
    border-radius: 8px;
    font-family: inherit;
    font-size: 0.95rem;
    background: transparent;
    color: inherit;
  }}
  textarea {{ min-height: 90px; resize: vertical; }}
  button {{
    align-self: flex-start;
    padding: 8px 18px;
    border-radius: 8px;
    border: 1px solid rgba(49, 51, 63, 0.2);
    background: #ff4b4b;
    color: white;
    font-weight: 600;
    cursor: pointer;
  }}
  button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
  #result {{ margin-top: 6px; font-size: 0.95rem; }}
  #result.ok {{ color: #137333; }}
  #result.err {{ color: #b3261e; }}
</style>
</head>
<body>
<form id="suggest-form">
  <label for="article">PMID (preferred) or article title</label>
  <textarea id="article" name="pmid_or_title" required></textarea>

  <label for="suggester">Your name (optional)</label>
  <input id="suggester" type="text" name="suggester" />

  <button type="submit" id="submit-btn">Send suggestion</button>
  <div id="result" aria-live="polite"></div>
</form>

<script>
(function() {{
  const form = document.getElementById('suggest-form');
  const btn = document.getElementById('submit-btn');
  const resultEl = document.getElementById('result');
  const ACCESS_KEY = "{safe_key}";
  const ENDPOINT = "{safe_endpoint}";

  form.addEventListener('submit', async function(e) {{
    e.preventDefault();
    resultEl.className = '';
    resultEl.textContent = 'Sending…';
    btn.disabled = true;

    const article = form.pmid_or_title.value.trim();
    const suggester = form.suggester.value.trim();

    if (!article) {{
      resultEl.className = 'err';
      resultEl.textContent = 'Please enter a PMID or article title.';
      btn.disabled = false;
      return;
    }}

    const short = article.length <= 80 ? article : article.slice(0, 77) + '...';
    const payload = {{
      access_key: ACCESS_KEY,
      subject: 'Article suggestion: ' + short,
      from_name: 'ABevidence — Suggest an article',
      pmid_or_title: article,
      suggester: suggester || '(anonymous)',
      message: 'PMID or title: ' + article + '\\nFrom: ' + (suggester || '(anonymous)')
    }};

    try {{
      const res = await fetch(ENDPOINT, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json', 'Accept': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      const data = await res.json().catch(function() {{ return {{}}; }});
      if (data && data.success) {{
        resultEl.className = 'ok';
        resultEl.textContent = 'Thanks! Your suggestion was sent.';
        form.reset();
      }} else {{
        resultEl.className = 'err';
        resultEl.textContent = 'Sorry, something went wrong: ' + (data.message || res.statusText || 'unknown error');
      }}
    }} catch (err) {{
      resultEl.className = 'err';
      resultEl.textContent = "Couldn't reach the email service: " + err.message;
    }} finally {{
      btn.disabled = false;
    }}
  }});
}})();
</script>
</body>
</html>
""",
        height=380,
        scrolling=False,
    )
