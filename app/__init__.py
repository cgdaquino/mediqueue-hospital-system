from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(test_config=None):
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///mediqueue.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if test_config:
        app.config.update(test_config)

    db.init_app(app)

    @app.route("/")
    def home():
        return render_template("index.html")

    @app.route("/api/health")
    def health():
        return {"status": "ok", "application": "MediQueue"}, 200

    return app
