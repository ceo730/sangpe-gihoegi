from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Submission(db.Model):
    __tablename__ = "submissions"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    image_count = db.Column(db.Integer, default=0)
    analysis_result = db.Column(db.Text)  # Full JSON result
    product_name = db.Column(db.String(500))
    brand_name = db.Column(db.String(500))
    category = db.Column(db.String(500))

    def to_dict(self):
        import json

        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "image_count": self.image_count,
            "product_name": self.product_name,
            "brand_name": self.brand_name,
            "category": self.category,
            "analysis_result": json.loads(self.analysis_result)
            if self.analysis_result
            else None,
        }
