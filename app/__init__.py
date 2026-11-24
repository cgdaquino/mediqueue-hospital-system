import os
import secrets
from pathlib import Path
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(test_config=None):
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL', 'sqlite:///mediqueue.db')
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config.update(HOSPITAL_TIMEZONE='Asia/Manila', SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')

    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get('SECRET_KEY'):
        secret_path = Path(app.instance_path) / 'session-secret'
        try:
            with secret_path.open('x') as handle:
                handle.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secret_path.read_text().strip()
    db.init_app(app)
    from . import models
    from .routes import bp, seed_demo
    from .doctor_accounts import accounts_bp
    app.register_blueprint(bp)
    app.register_blueprint(accounts_bp)
    app.cli.add_command(seed_demo)

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.route("/api/health")
    def health():
        return {"status": "ok", "application": "MediQueue"}, 200

    with app.app_context():
        db.create_all()
        from .migrations import upgrade_sqlite_schema
        upgrade_sqlite_schema(db.engine)
        if not db.session.scalar(db.select(models.Doctor.id).limit(1)):
            db.session.add_all([
                models.Doctor(name='Dr. Maria Santos', department='General Medicine'),
                models.Doctor(name='Dr. Ana Cruz', department='Cardiology'),
                models.Doctor(name='Dr. Sofia Garcia', department='Pediatrics'),
            ])
            db.session.flush()
        from .scheduling import default_week
        for doctor in db.session.scalars(db.select(models.Doctor)):
            existing = set(db.session.scalars(db.select(models.WeeklyAvailability.weekday).filter_by(doctor_id=doctor.id)))
            for day in default_week():
                if day['weekday'] not in existing:
                    db.session.add(models.WeeklyAvailability(doctor_id=doctor.id,**day))
        db.session.commit()
    return app
