from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import date

app = Flask(__name__)
import os

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "teamorbit-demo-secret-key")

# Vercel functions do not provide persistent writable project storage.
# Use a temporary SQLite location on Vercel for demo/runtime writes,
# while keeping the normal Flask SQLite database locally.
if os.environ.get("VERCEL"):
    db_path = "/tmp/teamorbit.db"
else:
    db_path = os.path.join(app.instance_path, "teamorbit.db")

os.makedirs(os.path.dirname(db_path), exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


# -------------------- DATABASE MODELS --------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="member")


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)


class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"))


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey("user.id"))
    priority = db.Column(db.String(20), default="Medium")
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(30), default="Pending")


# -------------------- HELPERS --------------------

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def manager_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return redirect(url_for("login"))
        if user.role not in ("admin", "manager"):
            flash("Manager or Admin access required.", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    return {
        "current_user": current_user(),
        "today": date.today()
    }


# -------------------- HOME / AUTH --------------------

@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        role = request.form["role"]

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("register"))

        user = User(
            name=name,
            email=email,
            password=generate_password_hash(password),
            role=role
        )
        db.session.add(user)
        db.session.commit()

        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# -------------------- DASHBOARD --------------------

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()

    if user.role in ("admin", "manager"):
        tasks = Task.query.all()
    else:
        tasks = Task.query.filter_by(assigned_to=user.id).all()

    total = len(tasks)
    completed = sum(t.status == "Completed" for t in tasks)
    in_progress = sum(t.status == "In Progress" for t in tasks)
    pending = sum(t.status == "Pending" for t in tasks)

    overdue = sum(
        bool(t.end_date and t.end_date < date.today() and t.status != "Completed")
        for t in tasks
    )

    progress = round(completed / total * 100) if total else 0

    # Overall dashboard health
    if overdue >= 3:
        health = "AT RISK"
    elif overdue >= 1 or (total >= 3 and progress < 50):
        health = "NEEDS ATTENTION"
    else:
        health = "GOOD"

    return render_template(
        "dashboard.html",
        tasks=tasks,
        total=total,
        completed=completed,
        in_progress=in_progress,
        pending=pending,
        overdue=overdue,
        progress=progress,
        health=health
    )


# -------------------- USERS --------------------

@app.route("/users")
@login_required
def users():
    if current_user().role != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("dashboard"))

    return render_template(
        "users.html",
        users=User.query.order_by(User.id.desc()).all()
    )


# -------------------- TEAMS --------------------

@app.route("/teams", methods=["GET", "POST"])
@login_required
def teams():
    if request.method == "POST":
        if current_user().role not in ("admin", "manager"):
            flash("Only Admin or Manager can create teams.", "error")
            return redirect(url_for("teams"))

        name = request.form["name"].strip()

        if not name:
            flash("Team name is required.", "error")
            return redirect(url_for("teams"))

        db.session.add(Team(name=name))
        db.session.commit()

        flash("Team created.", "success")

    return render_template("teams.html", teams=Team.query.all())


# -------------------- PROJECTS --------------------

@app.route("/projects", methods=["GET", "POST"])
@login_required
def projects():
    if request.method == "POST":
        if current_user().role not in ("admin", "manager"):
            flash("Only Admin or Manager can create projects.", "error")
            return redirect(url_for("projects"))

        name = request.form["name"].strip()

        if not name:
            flash("Project name is required.", "error")
            return redirect(url_for("projects"))

        team_id = request.form.get("team_id") or None

        project = Project(
            name=name,
            description=request.form.get("description", "").strip(),
            team_id=int(team_id) if team_id else None
        )

        db.session.add(project)
        db.session.commit()

        flash("Project created.", "success")

    return render_template(
        "projects.html",
        projects=Project.query.all(),
        teams=Team.query.all()
    )


# -------------------- TASKS --------------------

@app.route("/tasks", methods=["GET", "POST"])
@login_required
def tasks():
    user = current_user()

    if request.method == "POST":
        if user.role not in ("admin", "manager"):
            flash("Only Admin or Manager can create tasks.", "error")
            return redirect(url_for("tasks"))

        if not Project.query.get(int(request.form["project_id"])):
            flash("Please select a valid project.", "error")
            return redirect(url_for("tasks"))

        start = request.form.get("start_date") or None
        end = request.form.get("end_date") or None

        task = Task(
            title=request.form["title"].strip(),
            description=request.form.get("description", "").strip(),
            project_id=int(request.form["project_id"]),
            assigned_to=(
                int(request.form["assigned_to"])
                if request.form.get("assigned_to")
                else None
            ),
            priority=request.form["priority"],
            start_date=date.fromisoformat(start) if start else None,
            end_date=date.fromisoformat(end) if end else None,
            status="Pending"
        )

        db.session.add(task)
        db.session.commit()

        flash("Task created.", "success")
        return redirect(url_for("tasks"))

    if user.role == "member":
        task_list = Task.query.filter_by(assigned_to=user.id).all()
    else:
        task_list = Task.query.all()

    return render_template(
        "tasks.html",
        tasks=task_list,
        projects=Project.query.all(),
        users=User.query.all()
    )


@app.post("/tasks/<int:task_id>/status")
@login_required
def update_status(task_id):
    task = db.session.get(Task, task_id)

    if not task:
        flash("Task not found.", "error")
        return redirect(url_for("tasks"))

    user = current_user()

    if user.role == "member" and task.assigned_to != user.id:
        flash("You can only update your own tasks.", "error")
        return redirect(url_for("tasks"))

    status = request.form["status"]

    if status not in ("Pending", "In Progress", "Completed"):
        flash("Invalid task status.", "error")
        return redirect(url_for("tasks"))

    task.status = status
    db.session.commit()

    flash("Task status updated.", "success")
    return redirect(url_for("tasks"))


# -------------------- SMART ASSIGNMENT --------------------

@app.route("/smart-assign")
@manager_required
def smart_assign():
    members = User.query.filter_by(role="member").all()

    recommendations = []

    for member in members:
        active = Task.query.filter(
            Task.assigned_to == member.id,
            Task.status.in_(["Pending", "In Progress"])
        ).count()

        overdue = Task.query.filter(
            Task.assigned_to == member.id,
            Task.end_date < date.today(),
            Task.status != "Completed"
        ).count()

        completed = Task.query.filter_by(
            assigned_to=member.id,
            status="Completed"
        ).count()

        # Lower score = better candidate.
        # Active tasks and overdue tasks increase workload score.
        # Completed tasks slightly improve the score.
        score = active * 3 + overdue * 5 - completed

        recommendations.append(
            (score, active, overdue, completed, member)
        )

    recommendations.sort(key=lambda item: item[0])

    return render_template(
        "smart_assign.html",
        recommendations=recommendations
    )


# -------------------- PROJECT HEALTH --------------------

@app.route("/health")
@login_required
def project_health():
    projects = Project.query.all()
    health_data = []

    for project in projects:
        project_tasks = Task.query.filter_by(
            project_id=project.id
        ).all()

        total = len(project_tasks)
        completed = sum(
            t.status == "Completed" for t in project_tasks
        )
        in_progress = sum(
            t.status == "In Progress" for t in project_tasks
        )
        pending = sum(
            t.status == "Pending" for t in project_tasks
        )

        overdue = sum(
            bool(
                t.end_date
                and t.end_date < date.today()
                and t.status != "Completed"
            )
            for t in project_tasks
        )

        progress = round(
            completed / total * 100
        ) if total else 0

        if overdue >= 3:
            health = "AT RISK"
        elif overdue >= 1 or (
            total >= 3 and progress < 50
        ):
            health = "NEEDS ATTENTION"
        else:
            health = "GOOD"

        health_data.append({
            "project": project,
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "pending": pending,
            "overdue": overdue,
            "progress": progress,
            "health": health
        })

    return render_template(
        "health.html",
        health_data=health_data
    )


# -------------------- DATABASE INITIALIZATION --------------------

with app.app_context():
    db.create_all()

    if not User.query.filter_by(
        email="admin@teamorbit.com"
    ).first():

        db.session.add(
            User(
                name="System Admin",
                email="admin@teamorbit.com",
                password=generate_password_hash("admin123"),
                role="admin"
            )
        )

        db.session.commit()


if __name__ == "__main__":
    app.run(debug=True)
