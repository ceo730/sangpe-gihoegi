import json
import os
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    render_template,
    request,
)

from analyzer import analyze_page
from models import Submission, db

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

# ── Database ──
database_url = os.getenv("DATABASE_URL", "sqlite:///local.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)
with app.app_context():
    db.create_all()


@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({"error": "파일이 너무 큽니다. 10MB 이하로 업로드해주세요."}), 413


# ── Admin auth ──
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        admin_pw = os.getenv("ADMIN_PASSWORD")
        if not admin_pw:
            abort(403, "ADMIN_PASSWORD 환경변수가 설정되지 않았습니다.")
        auth = request.authorization
        if not auth or auth.password != admin_pw:
            return Response(
                "관리자 인증이 필요합니다.",
                401,
                {"WWW-Authenticate": 'Basic realm="Admin"'},
            )
        return f(*args, **kwargs)

    return decorated


# ── Routes ──
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return jsonify({"error": "서버에 API 키가 설정되지 않았습니다."}), 500

    files = request.files.getlist("images")
    if not files:
        return jsonify({"error": "이미지를 업로드해주세요."}), 400

    MEDIA_MAP = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }

    image_list = []
    for f in files:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        media_type = MEDIA_MAP.get(ext, "image/jpeg")
        image_list.append((f.read(), media_type))

    try:
        result = analyze_page(image_list, api_key)
        del image_list  # free memory

        # Save to DB
        submission = Submission(
            image_count=len(files),
            analysis_result=json.dumps(result, ensure_ascii=False),
            product_name=result.get("product_name", ""),
            brand_name=result.get("brand_name", ""),
            category=result.get("category", ""),
        )
        db.session.add(submission)
        db.session.commit()

        return jsonify(result)
    except Exception as e:
        app.logger.error(f"분석 오류: {e}")
        return jsonify({"error": str(e)}), 500


# ── Admin routes ──
@app.route("/admin")
@require_admin
def admin_list():
    page = request.args.get("page", 1, type=int)
    per_page = 20
    pagination = Submission.query.order_by(Submission.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template("admin.html", pagination=pagination)


@app.route("/admin/submission/<int:sub_id>")
@require_admin
def admin_detail(sub_id):
    submission = Submission.query.get_or_404(sub_id)
    analysis = (
        json.loads(submission.analysis_result) if submission.analysis_result else {}
    )
    return render_template(
        "admin_detail.html", submission=submission, analysis=analysis
    )


@app.route("/admin/export")
@require_admin
def admin_export():
    submissions = Submission.query.order_by(Submission.created_at.desc()).all()
    data = [s.to_dict() for s in submissions]
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=sangpe_export.json"},
    )


@app.route("/admin/export-full")
@require_admin
def admin_export_full():
    submissions = Submission.query.order_by(Submission.created_at.desc()).all()
    data = [s.to_dict() for s in submissions]
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition": "attachment; filename=sangpe_export_full.json"
        },
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
