import json
import os
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://postgres:54321@localhost:5432/predprof"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "5db3837044ea22f708eedf3e9ac802310f20dbbe48710aed798478d4532cf97e"
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model_mesto = os.path.join(BASE_DIR, "model.h5")
weights_mesto = os.path.join(BASE_DIR, "model.weights.h5")
config_mesto = os.path.join(BASE_DIR, "model_config.json")
label_mesto = os.path.join(BASE_DIR, "label_to_id.json")
history_js = os.path.join(BASE_DIR, "history.json")
class_js = os.path.join(BASE_DIR, "train_class_counts.json")
valid_js = os.path.join(BASE_DIR, "valid_top5.json")
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "uploads")
model = None
label_id = None
id_label = None

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class History(db.Model):
    __tablename__ = "history"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    input_info = db.Column(db.String(500), nullable=True)
    prediction = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def load_model():
    global model, label_id, id_label
    if not os.path.exists(label_mesto):
        print("Модель не загружена: файл не найден:", label_mesto)
        return
    try:
        from tensorflow import keras
        from tensorflow.keras import layers
        with open(label_mesto, "r", encoding="utf-8") as f:
            label_id = json.load(f)
        id_label = {str(v): k for k, v in label_id.items()}
        n_classes = len(label_id)
        if os.path.exists(weights_mesto) and os.path.exists(config_mesto):
            with open(config_mesto, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            max_len = int(cfg["max_len"])
            model = keras.Sequential([
                layers.Input(shape=(max_len, 1)),
                layers.Conv1D(64, 15, activation="relu", padding="same"),
                layers.MaxPooling1D(4),
                layers.Conv1D(128, 7, activation="relu", padding="same"),
                layers.MaxPooling1D(4),
                layers.Flatten(),
                layers.Dense(128, activation="relu"),
                layers.Dropout(0.4),
                layers.Dense(n_classes, activation="softmax")
            ])
            model.load_weights(weights_mesto)
            print("Модель загружена (веса):", weights_mesto)
        elif os.path.exists(model_mesto):
            model = keras.models.load_model(model_mesto)
            print("Модель загружена (полная):", model_mesto)
        else:
            print("Модель не загружена: не найден model.h5 или model.weights.h5 + model_config.json")
            model = None
    except Exception as e:
        print("Ошибка загрузки модели:", e)
        model = None

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class LoginForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=1, max=80)])
    password = PasswordField(validators=[InputRequired(), Length(min=1)])
    submit = SubmitField("Войти")

class CreateUserForm(FlaskForm):
    first_name = StringField(validators=[InputRequired(), Length(max=100)])
    last_name = StringField(validators=[InputRequired(), Length(max=100)])
    username = StringField(validators=[InputRequired(), Length(max=80)])
    password = PasswordField(validators=[InputRequired(), Length(min=1)])
    submit = SubmitField("Создать пользователя")

@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin_page"))
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            if user.role == "admin":
                return redirect(url_for("admin_page"))
            return redirect(url_for("dashboard"))
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route("/admin", methods=["GET", "POST"])
@login_required
def admin_page():
    if current_user.role != "admin":
        return redirect(url_for("dashboard"))
    form = CreateUserForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            return render_template("admin.html", form=form, error="Пользователь с таким логином уже существует")
        user = User(username=form.username.data, role="user", first_name=form.first_name.data, last_name=form.last_name.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("admin_page"))
    return render_template("admin.html", form=form)

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "admin":
        return redirect(url_for("admin_page"))
    return render_template("dashboard.html", user=current_user)

@app.route("/analytics")
@login_required
def analytics():
    if current_user.role == "admin":
        return redirect(url_for("admin_page"))
    return render_template("analytics.html")

@app.route("/api/analytics/epochs")
@login_required
def api_epochs():
    if current_user.role == "admin":
        return jsonify({}), 403
    if not os.path.exists(history_js):
        return jsonify({"epochs": [], "val_accuracy": []})
    with open(history_js, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route("/api/analytics/class_counts")
@login_required
def api_class_counts():
    if current_user.role == "admin":
        return jsonify({}), 403
    if not os.path.exists(class_js):
        return jsonify({})
    with open(class_js, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route("/api/analytics/valid_top5")
@login_required
def api_valid_top5():
    if current_user.role == "admin":
        return jsonify({}), 403
    if not os.path.exists(valid_js):
        return jsonify({})
    with open(valid_js, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))

@app.route("/api/predict", methods=["POST"])
@login_required
def api_predict():
    if model is None:
        return jsonify({"error": "Модель не загружена"}), 503
    data = request.get_json()
    if data is None or "signal" not in data:
        return jsonify({"error": "Нет данных signal"}), 400
    try:
        arr = np.array(data["signal"], dtype=np.float32)
        if arr.ndim == 1:
            arr = np.expand_dims(arr, 0)
        arr = arr / (np.max(np.abs(arr)) + 1e-8)
        pred = model.predict(arr, verbose=0)
        cls = int(np.argmax(pred[0]))
        rec = History(user_id=current_user.id, input_info="signal", prediction=cls)
        db.session.add(rec)
        db.session.commit()
        return jsonify({"class": cls, "label": id_label.get(str(cls), str(cls))})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/upload_test", methods=["POST"])
@login_required
def api_upload_test():
    if current_user.role == "admin":
        return jsonify({"error": "Доступ запрещён"}), 403
    if model is None:
        return jsonify({"error": "Модель не загружена"}), 503
    if "file" not in request.files:
        return jsonify({"error": "Нет файла"}), 400
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "Файл не выбран"}), 400
    if not (f.filename or "").lower().endswith(".npz"):
        return jsonify({"error": "Нужен файл .npz"}), 400
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    path = os.path.join(app.config["UPLOAD_FOLDER"], secure_filename(f.filename or "upload.npz"))
    f.save(path)
    try:
        data = np.load(path, allow_pickle=True)
        if "test_x" not in data or "test_y" not in data:
            raise ValueError("В файле .npz должны быть массивы test_x и test_y")
        test_x = data["test_x"]
        test_y = data["test_y"]
        test_y_fixed = np.array([label_id.get(str(v), 0) for v in np.ravel(test_y)], dtype=np.int32)
        max_len = int(model.input_shape[1])
        if test_x.ndim == 2:
            out = [np.array(test_x[i], dtype=np.float32).flatten() for i in range(len(test_x))]
        else:
            out = [np.array(test_x[i], dtype=np.float32).flatten() for i in range(len(test_x))]
        for i in range(len(out)):
            s = out[i]
            if len(s) == 0:
                s = np.zeros(1, dtype=np.float32)
            s = s / (np.max(np.abs(s)) + 1e-8)
            out[i] = s
        padded = np.zeros((len(out), max_len), dtype=np.float32)
        for i, s in enumerate(out):
            L = min(len(s), max_len)
            padded[i, :L] = s[:L]
        test_x = np.expand_dims(padded, -1)
        preds = model.predict(test_x, verbose=0)
        pred_classes = np.argmax(preds, axis=1)
        correct = (pred_classes == test_y_fixed).astype(int).tolist()
        accuracy = float(np.mean(correct))
        loss = float(np.mean(-np.log(np.max(preds, axis=1) + 1e-8)))
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        return jsonify({"accuracy": accuracy, "loss": loss, "per_record": correct, "total": len(correct)})
    except Exception as e:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Не удалось прочитать .npz. Проверьте, что в файле есть массивы test_x и test_y."}), 400

@app.route("/userinfo")
@login_required
def userinfo():
    if current_user.role == "admin":
        return redirect(url_for("admin_page"))
    return render_template("userinfo.html", user=current_user)

with app.app_context():
    db.create_all()
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(username="admin", role="admin", first_name="Администратор", last_name="Системы")
        admin.set_password("admin")
        db.session.add(admin)
        db.session.commit()
load_model()

if __name__ == "__main__":
    app.run(debug=True)
