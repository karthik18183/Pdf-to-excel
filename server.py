from flask import Flask, request, send_file, render_template_string
import os, sys, tempfile, uuid
from pathlib import Path
from subprocess import run, CalledProcessError

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload cap

PAGE = """
<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>PDF → Excel</title>
<style>
  :root { --fg:#111; --muted:#666; --border:#ddd; }
  * { box-sizing:border-box }
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,"Helvetica Neue",Arial,sans-serif;
       max-width:720px;margin:40px auto;padding:0 16px;color:var(--fg)}
  .card{border:1px solid var(--border);border-radius:14px;padding:22px;box-shadow:0 2px 10px rgba(0,0,0,.04)}
  .row{display:flex;gap:12px;align-items:center;margin-top:12px}
  input[type=file]{padding:8px}
  button{padding:10px 16px;border:0;border-radius:10px;cursor:pointer;background:#111;color:#fff}
  .muted{color:var(--muted)}
  pre{white-space:pre-wrap;font-size:13px}
  a.button{display:inline-block;margin-top:12px;text-decoration:none;background:#0a7;color:#fff;
           padding:10px 14px;border-radius:10px}
  footer{margin-top:20px;font-size:12px;color:var(--muted)}
</style>
<div class="card">
  <h1>PDF → Excel</h1>
  <p class="muted">Upload a PDF and get an <code>.xlsx</code> back.</p>

  <form method="post" enctype="multipart/form-data">
    <div class="row">
      <input type="file" name="pdf" accept="application/pdf" required>
      <button type="submit">Convert</button>
    </div>
  </form>

  {% if error %}<pre style="color:#b00;margin-top:16px;">{{error}}</pre>{% endif %}
  {% if download %}
    <a class="button" href="{{download}}">Download Excel</a>
  {% endif %}

  <footer>Max file size: 50 MB. Files are processed in a temp folder.</footer>
</div>
"""

def run_converter(pdf_path: str, out_path: str):
    """
    Calls your existing CLI script:
      python parse_pdf_to_excel.py --pdf <in> --out <out>
    If you later expose a function, you can import and call that here instead.
    """
    try:
        run(
            [sys.executable, "parse_pdf_to_excel.py", "--pdf", pdf_path, "--out", out_path],
            check=True, capture_output=True, text=True
        )
    except CalledProcessError as e:
        # bubble up a readable error including script stdout/stderr
        raise RuntimeError(f"Conversion failed.\n\nSTDOUT:\n{e.stdout}\n\nSTDERR:\n{e.stderr}")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        f = request.files.get("pdf")
        if not f or f.filename.strip() == "":
            return render_template_string(PAGE, error="No PDF provided.", download=None)

        tmpdir = tempfile.mkdtemp(prefix="pdf2xlsx_")
        in_path = os.path.join(tmpdir, f.filename)
        f.save(in_path)

        token = f"{Path(f.filename).stem}_{uuid.uuid4().hex[:6]}.xlsx"
        out_path = os.path.join(tmpdir, token)

        try:
            run_converter(in_path, out_path)
        except Exception as ex:
            return render_template_string(PAGE, error=str(ex), download=None)

        # stash for download
        app.config[token] = out_path
        return render_template_string(PAGE, error=None, download=f"/download/{token}")

    return render_template_string(PAGE, error=None, download=None)

@app.route("/download/<token>")
def download(token):
    path = app.config.get(token)
    if not path or not os.path.exists(path):
        return "Not found", 404
    return send_file(path, as_attachment=True, download_name=Path(path).name)

if __name__ == "__main__":
    # Local dev server
    app.run(host="127.0.0.1", port=5057, debug=True)
