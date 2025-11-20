import os, io, csv, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from models import db, User, Account, Transaction, VirtualCard, ScheduledTransfer
from utils import send_otp_console, generate_virtual_card_number, detect_fraud

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'devkey')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///data.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['REQUIRE_OTP'] = os.getenv('REQUIRE_OTP', 'False') in ['True', 'true', '1']

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form['name']
        email = request.form['email'].lower()
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash("Email already registered", "danger")
            return redirect(url_for("register"))
        u = User(name=name, email=email, password_hash=generate_password_hash(password))
        acc = Account(balance=1000.0, currency="INR")
        u.accounts.append(acc)
        db.session.add(u); db.session.commit()
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email = request.form['email'].lower()
        passwd = request.form['password']
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, passwd):
            flash("Invalid credentials", "danger")
            return redirect(url_for("login"))
        if app.config['REQUIRE_OTP']:
            otp = send_otp_console(user.email)
            # store OTP in session or a short-term store — for demo we show input flow
            return render_template("login.html", ask_otp=True, email=email)
        login_user(user)
        flash("Welcome back", "success")
        return redirect(url_for("dashboard"))
    # OTP confirmation flow
    if request.args.get('otp_confirm'):
        email = request.args.get('email')
        # demo: accept any otp since OTP is printed to console
        user = User.query.filter_by(email=email).first()
        if user:
            login_user(user)
            flash("OTP accepted. Logged in.", "success")
            return redirect(url_for("dashboard"))
    return render_template("login.html", ask_otp=False)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    # process scheduled transfers due now (safe simple approach)
    due = ScheduledTransfer.query.filter(ScheduledTransfer.execute_at <= datetime.datetime.utcnow(), ScheduledTransfer.status=="PENDING").all()
    for s in due:
        try:
            sender = s.from_account
            receiver = s.to_account
            if sender.balance >= s.amount:
                sender.balance -= s.amount
                receiver.balance += s.amount
                t = Transaction(account=sender, amount=-s.amount, type="scheduled_transfer", note=f"Scheduled -> {receiver.number}")
                t2 = Transaction(account=receiver, amount=s.amount, type="scheduled_transfer", note=f"Scheduled from {sender.number}")
                db.session.add_all([t, t2])
                s.status = "COMPLETED"
            else:
                s.status = "FAILED"
        except Exception:
            s.status = "FAILED"
    db.session.commit()

    accounts = current_user.accounts
    txs = Transaction.query.filter(Transaction.account_id.in_([a.id for a in accounts])).order_by(Transaction.created_at.desc()).limit(10).all()
    categories = {}
    for t in txs:
        categories[t.category or "other"] = categories.get(t.category or "other", 0) + abs(t.amount)
    return render_template("dashboard.html", accounts=accounts, recent=txs, categories=categories)

@app.route("/transfer", methods=["GET","POST"])
@login_required
def transfer():
    if request.method=="POST":
        from_acc_id = int(request.form['from_account'])
        to_acc_number = request.form['to_account_number']
        amount = float(request.form['amount'])
        note = request.form.get('note')
        schedule_date = request.form.get('schedule_date')
        from_acc = Account.query.get(from_acc_id)
        to_acc = Account.query.filter_by(number=to_acc_number).first()
        if not to_acc:
            flash("Destination account not found", "danger"); return redirect(url_for("transfer"))
        if schedule_date:
            try:
                dt = datetime.datetime.fromisoformat(schedule_date)
            except Exception:
                flash("Invalid schedule date format", "danger"); return redirect(url_for("transfer"))
            s = ScheduledTransfer(from_account=from_acc, to_account=to_acc, amount=amount, execute_at=dt, status="PENDING")
            db.session.add(s); db.session.commit()
            flash("Transfer scheduled", "success"); return redirect(url_for("dashboard"))
        if from_acc.balance < amount:
            flash("Insufficient funds", "danger"); return redirect(url_for("transfer"))
        if detect_fraud(amount, from_acc):
            flash("Transfer flagged as suspicious and blocked. Contact support.", "danger"); return redirect(url_for("transfer"))
        from_acc.balance -= amount
        to_acc.balance += amount
        t1 = Transaction(account=from_acc, amount=-amount, type="transfer", note=note)
        t2 = Transaction(account=to_acc, amount=amount, type="transfer", note=f"From {from_acc.number}")
        db.session.add_all([t1,t2])
        db.session.commit()
        flash("Transfer complete", "success")
        return redirect(url_for("dashboard"))
    return render_template("transfer.html", accounts=current_user.accounts)

@app.route("/transactions")
@login_required
def transactions():
    accounts = current_user.accounts
    txs = Transaction.query.filter(Transaction.account_id.in_([a.id for a in accounts])).order_by(Transaction.created_at.desc()).all()
    return render_template("transactions.html", txs=txs)

@app.route("/virtual-card", methods=["GET","POST"])
@login_required
def virtual_card():
    if request.method=="POST":
        card_num = generate_virtual_card_number()
        vc = VirtualCard(owner_id=current_user.id, number=card_num, expiry="12/29", cvv="123")
        db.session.add(vc); db.session.commit()
        flash("Virtual card created", "success")
        return redirect(url_for("virtual_card"))
    cards = VirtualCard.query.filter_by(owner_id=current_user.id).all()
    return render_template("virtual_card.html", cards=cards)

@app.route("/export/transactions.csv")
@login_required
def export_csv():
    accounts = current_user.accounts
    txs = Transaction.query.filter(Transaction.account_id.in_([a.id for a in accounts])).order_by(Transaction.created_at.desc()).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Date","Account","Type","Amount","Category","Note"])
    for t in txs:
        cw.writerow([t.created_at.isoformat(), t.account.number, t.type, t.amount, t.category, t.note])
    output = io.BytesIO()
    output.write(si.getvalue().encode())
    output.seek(0)
    return send_file(output, mimetype="text/csv", download_name="transactions.csv", as_attachment=True)

# Admin dashboard
@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        flash("Not authorized", "danger"); return redirect(url_for("dashboard"))
    users = User.query.all()
    return render_template("admin.html", users=users)

# A small API endpoint you can call via Render scheduled job or curl to process scheduled transfers:
@app.route("/process-scheduled")
def process_scheduled():
    # Not protected for demo — lock in production
    due = ScheduledTransfer.query.filter(ScheduledTransfer.execute_at <= datetime.datetime.utcnow(), ScheduledTransfer.status=="PENDING").all()
    processed = 0
    for s in due:
        try:
            sender = s.from_account
            receiver = s.to_account
            if sender.balance >= s.amount:
                sender.balance -= s.amount
                receiver.balance += s.amount
                t = Transaction(account=sender, amount=-s.amount, type="scheduled_transfer", note=f"Scheduled -> {receiver.number}")
                t2 = Transaction(account=receiver, amount=s.amount, type="scheduled_transfer", note=f"Scheduled from {sender.number}")
                db.session.add_all([t, t2])
                s.status = "COMPLETED"
                processed += 1
            else:
                s.status = "FAILED"
        except Exception:
            s.status = "FAILED"
    db.session.commit()
    return {"processed": processed, "status": "ok"}

if __name__=="__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
