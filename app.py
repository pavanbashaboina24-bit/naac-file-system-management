
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from functools import wraps
from datetime import datetime
import base64
from supabase import create_client

app = Flask(__name__)
app.secret_key = "naac-secret-key-2024"

SUPABASE_URL = "https://vghhcjgcdaxyryztkdja.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZnaGhjamdjZGF4eXJ5enRrZGphIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjU4NjExOCwiZXhwIjoyMDc4MTYyMTE4fQ.K0kZV4ub_6wFBguGlkP7KSfwLm2bcLqw8aQpqCkgmbs"
db = create_client(SUPABASE_URL, SUPABASE_KEY)

CRITERIA = {
    "3.1": {"title": "Research Promotion", "desc": "Grants, research guides, funded departments.", "subs": [
        {"id": "3.1.1", "label": "Grants received from Government/Non-Govt agencies"},
        {"id": "3.1.2", "label": "Teachers recognized as research guides"},
        {"id": "3.1.3", "label": "Departments having research projects"},
    ]},
    "3.2": {"title": "Innovation Ecosystem", "desc": "IPR workshops, incubation, industry-academia.", "subs": [
        {"id": "3.2.1", "label": "Ecosystem for innovations including Incubation Centre"},
        {"id": "3.2.2", "label": "Workshops/seminars on IPR and Industry-Academia"},
    ]},
    "3.3": {"title": "Research Publications", "desc": "PhD registrations, UGC journals, code of ethics.", "subs": [
        {"id": "3.3.1", "label": "Implementation of Code of Ethics"},
        {"id": "3.3.2", "label": "Number of Ph.Ds registered per eligible teacher"},
        {"id": "3.3.3", "label": "Research papers in UGC-notified Journals"},
    ]},
    "3.4": {"title": "Extension Activities", "desc": "NSS/NCC, outreach, community programs.", "subs": [
        {"id": "3.4.1", "label": "Extension activities in neighborhood community"},
        {"id": "3.4.2", "label": "Awards for extension activities"},
        {"id": "3.4.3", "label": "Extension and outreach programs (NSS/NCC/Red Cross)"},
    ]},
    "3.5": {"title": "Collaboration", "desc": "MoUs, internships, faculty/student exchange.", "subs": [
        {"id": "3.5.1", "label": "Collaborative activities for research and faculty exchange"},
        {"id": "3.5.2", "label": "Linkages for internship and on-the-job training"},
    ]},
}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated

@app.route("/", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        login_id = request.form.get("login_id", "").strip()
        password = request.form.get("password", "").strip()
        result = db.table("users").select("*").eq("login_id", login_id).eq("password", password).execute()
        if result.data:
            user = result.data[0]
            session["user"] = user["login_id"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))
        else:
            error = "Invalid credentials. Please try again."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")
    name = session.get("name")
    if role == "admin":
        rows = db.table("submissions").select("status").execute().data or []
    else:
        rows = db.table("submissions").select("status").eq("user_name", name).execute().data or []
    stats = {"total": len(rows), "approved": 0, "pending": 0, "rejected": 0}
    for r in rows:
        stats[r["status"]] = stats.get(r["status"], 0) + 1
    return render_template("dashboard.html", criteria=CRITERIA, stats=stats)

@app.route("/criterion/<crit_key>")
@login_required
def criterion(crit_key):
    crit = CRITERIA.get(crit_key)
    if not crit:
        return redirect(url_for("dashboard"))
    return render_template("criterion.html", crit=crit, crit_key=crit_key)

@app.route("/upload/<crit_key>/<sub_id>", methods=["GET", "POST"])
@login_required
def upload(crit_key, sub_id):
    if session.get("role") == "operator":
        flash("Operators must use Bulk Upload.", "error")
        return redirect(url_for("bulk_upload"))

    crit = CRITERIA.get(crit_key)
    sub  = next((s for s in crit["subs"] if s["id"] == sub_id), None) if crit else None
    if not sub:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title  = request.form.get("title", "").strip()
        agency = request.form.get("agency", "").strip()
        year   = request.form.get("year", "2024-25")
        link   = request.form.get("link", "").strip() or None
        file   = request.files.get("file")
        file_name         = "Link only"
        file_url          = None
        file_data_b64     = None
        file_content_type = None

        if not title:
            flash("Title is required.", "error")
            return render_template("upload.html", crit=crit, sub=sub, crit_key=crit_key)

        is_admin = session.get("role") == "admin"

        if file and file.filename:
            allowed = {"pdf", "xls", "xlsx", "jpg", "jpeg", "png"}
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in allowed:
                flash("Invalid file type. Use PDF, XLS, or JPG.", "error")
                return render_template("upload.html", crit=crit, sub=sub, crit_key=crit_key)
            file_bytes = file.read()
            if len(file_bytes) > 5 * 1024 * 1024:
                flash("File exceeds 5MB limit.", "error")
                return render_template("upload.html", crit=crit, sub=sub, crit_key=crit_key)

            file_name         = file.filename
            file_content_type = file.content_type

            if is_admin:
                try:
                    safe_name = f"{sub_id}_{year}_{file.filename.replace(' ', '_')}"
                    db.storage.from_("evidence-files").upload(
                        safe_name, file_bytes,
                        {"content-type": file_content_type, "upsert": "true"}
                    )
                    file_url = db.storage.from_("evidence-files").get_public_url(safe_name)
                except Exception as e:
                    flash(f"File upload failed: {str(e)}", "error")
                    return render_template("upload.html", crit=crit, sub=sub, crit_key=crit_key)
            else:
                file_data_b64 = base64.b64encode(file_bytes).decode("utf-8")

        status = "approved" if is_admin else "pending"

        db.table("submissions").insert({
            "user_name":          session["name"],
            "submitted_by_role":  session["role"],
            "criterion":          crit_key,
            "sub_id":             sub_id,
            "sub_label":          sub["label"],
            "title":              title,
            "agency":             agency,
            "year":               year,
            "link":               link,
            "file_name":          file_name,
            "file_url":           file_url,
            "file_data":          file_data_b64,
            "file_content_type":  file_content_type,
            "status":             status,
            "timestamp":          datetime.utcnow().isoformat(),
        }).execute()

        if is_admin:
            flash("Evidence uploaded and automatically approved!", "success")
        else:
            flash("Evidence submitted! Awaiting admin approval before file goes live.", "success")

        return redirect(url_for("criterion", crit_key=crit_key))

    return render_template("upload.html", crit=crit, sub=sub, crit_key=crit_key)

@app.route("/bulk-upload", methods=["GET", "POST"])
@login_required
def bulk_upload():
    if session.get("role") not in ("operator", "admin"):
        flash("Access denied.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        files    = request.files.getlist("files")
        crit_key = request.form.get("criterion")
        sub_id   = request.form.get("sub_id")
        agency   = request.form.get("agency", "").strip()
        year     = request.form.get("year", "2024-25")
        titles   = request.form.getlist("titles")
        links    = request.form.getlist("links")

        if not crit_key or not sub_id:
            flash("Please select a Criterion and Metric.", "error")
            return render_template("bulk_upload.html", criteria=CRITERIA)

        crit = CRITERIA.get(crit_key)
        sub  = next((s for s in crit["subs"] if s["id"] == sub_id), None) if crit else None
        if not sub:
            flash("Invalid metric selected.", "error")
            return render_template("bulk_upload.html", criteria=CRITERIA)

        if not files or all(f.filename == "" for f in files):
            flash("Please select at least one file.", "error")
            return render_template("bulk_upload.html", criteria=CRITERIA)

        allowed       = {"pdf", "xls", "xlsx", "jpg", "jpeg", "png"}
        success_count = 0
        fail_count    = 0

        for i, file in enumerate(files):
            if not file.filename:
                continue
            ext = file.filename.rsplit(".", 1)[-1].lower()
            if ext not in allowed:
                fail_count += 1
                continue
            file_bytes = file.read()
            if len(file_bytes) > 5 * 1024 * 1024:
                fail_count += 1
                continue

            file_data_b64 = base64.b64encode(file_bytes).decode("utf-8")
            title = titles[i].strip() if i < len(titles) and titles[i].strip() else file.filename.rsplit(".", 1)[0].replace("_", " ")
            link  = links[i].strip() or None if i < len(links) else None

            try:
                db.table("submissions").insert({
                    "user_name":         session["name"],
                    "submitted_by_role": session["role"],
                    "criterion":         crit_key,
                    "sub_id":            sub_id,
                    "sub_label":         sub["label"],
                    "title":             title,
                    "agency":            agency,
                    "year":              year,
                    "link":              link,
                    "file_name":         file.filename,
                    "file_url":          None,
                    "file_data":         file_data_b64,
                    "file_content_type": file.content_type,
                    "status":            "pending",
                    "timestamp":         datetime.utcnow().isoformat(),
                }).execute()
                success_count += 1
            except Exception:
                fail_count += 1

        if success_count:
            flash(f"{success_count} file(s) submitted successfully! Awaiting admin approval.", "success")
        if fail_count:
            flash(f"{fail_count} file(s) skipped (invalid type or exceeds 5MB).", "error")

        return redirect(url_for("bulk_upload"))

    return render_template("bulk_upload.html", criteria=CRITERIA)

@app.route("/admin")
@login_required
@admin_required
def admin():
    submissions = db.table("submissions").select("*").order("timestamp", desc=True).execute().data or []
    return render_template("admin.html", submissions=submissions)

@app.route("/admin/update/<sub_id>", methods=["POST"])
@login_required
@admin_required
def update_status(sub_id):
    new_status = request.form.get("status")
    if new_status not in ("approved", "rejected", "pending"):
        return redirect(url_for("admin"))

    update_payload = {"status": new_status}

    if new_status == "approved":
        row = db.table("submissions").select(
            "file_data, file_name, file_content_type, sub_id, year, status"
        ).eq("id", sub_id).execute().data

        if row:
            r = row[0]
            if r.get("status") == "approved":
                return redirect(url_for("admin"))
            file_data_b64 = r.get("file_data")
            if file_data_b64:
                try:
                    file_bytes = base64.b64decode(file_data_b64)
                    safe_name  = f"{r['sub_id']}_{r['year']}_{r['file_name'].replace(' ', '_')}"
                    db.storage.from_("evidence-files").upload(
                        safe_name, file_bytes,
                        {"content-type": r.get("file_content_type", "application/octet-stream"), "upsert": "true"}
                    )
                    file_url = db.storage.from_("evidence-files").get_public_url(safe_name)
                    update_payload["file_url"]  = file_url
                    update_payload["file_data"] = None
                except Exception as e:
                    flash(f"File upload failed during approval: {str(e)}", "error")
                    return redirect(url_for("admin"))

    db.table("submissions").update(update_payload).eq("id", sub_id).execute()
    flash(f"Submission {new_status} successfully.", "success")
    return redirect(url_for("admin"))

# ✅ NEW — Admin file preview route
@app.route("/admin/preview/<sub_id>")
@login_required
@admin_required
def admin_preview(sub_id):
    try:
        result = db.table("submissions").select(
            "file_data, file_name, file_content_type"
        ).eq("id", sub_id).single().execute()
        row = result.data
        if not row or not row.get("file_data"):
            return jsonify({"error": "No file data found for this submission."})
        return jsonify({
            "file_data":    row["file_data"],
            "filename":     row["file_name"],
            "content_type": row.get("file_content_type") or "application/octet-stream"
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/my-submissions")
@login_required
def my_submissions():
    docs = db.table("submissions").select("*") \
             .eq("user_name", session["name"]) \
             .order("timestamp", desc=True).execute().data or []
    return render_template("my_submissions.html", docs=docs)

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
