import os
import time
from functools import wraps
from urllib.parse import quote

import psycopg2
import psycopg2.extras
from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_file, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://shopapp:shopapp@localhost:5432/shopapp"
)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "novashop-dev-key")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    bio TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    price NUMERIC(10,2),
    category TEXT DEFAULT 'General',
    stock INT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES products(id),
    user_id INT NOT NULL REFERENCES users(id),
    rating INT DEFAULT 5,
    comment TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS favorites (
    user_id INT NOT NULL REFERENCES users(id),
    product_id INT NOT NULL REFERENCES products(id),
    note TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, product_id)
);
CREATE TABLE IF NOT EXISTS inquiries (
    id SERIAL PRIMARY KEY,
    name TEXT DEFAULT '',
    email TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    message TEXT DEFAULT '',
    status TEXT DEFAULT 'new',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS drafts (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id),
    title TEXT DEFAULT '',
    content TEXT DEFAULT '',
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

SEED_USERS = [
    ("alice", "password123", "Alice Nguyen", "alice.nguyen@mail.com",
     "Coffee, code and gadgets."),
    ("bob", "password123", "Bob Tran", "bob.tran@mail.com", "Weekend cyclist."),
    ("carol", "password123", "Carol Le", "carol.le@mail.com",
     "Interior design lover."),
    ("admin", "Adm1n2026!", "Store Administrator", "admin@novashop.local",
     "Keeping the shop running."),
]

SEED_PRODUCTS = [
    ("Wireless Earbuds Pro",
     "Active noise cancelling earbuds with 30h battery life and a wireless charging case.",
     "129.00", "Electronics", 25),
    ("Bluetooth Speaker Mini",
     "Pocket-size waterproof speaker with surprisingly big sound. 12h playtime.",
     "45.50", "Electronics", 40),
    ("Smart Watch X2",
     "Heart-rate, sleep tracking and 50+ sport modes. Water resistant 5 ATM.",
     "199.00", "Electronics", 12),
    ("USB-C Hub 7-in-1",
     "HDMI 4K, 2x USB 3.0, SD/microSD, Ethernet and 100W pass-through charging.",
     "39.00", "Electronics", 60),
    ("Mechanical Keyboard K68",
     "Hot-swappable red switches, PBT keycaps and per-key RGB lighting.",
     "89.00", "Electronics", 18),
    ("Ceramic Mug Set (4 pcs)",
     "Hand-glazed stoneware mugs, 350ml each. Dishwasher and microwave safe.",
     "25.00", "Home", 80),
    ("Scented Candle - Lavender",
     "Soy wax candle with cotton wick. Burns for approximately 45 hours.",
     "15.50", "Home", 120),
    ("Stainless Thermos 750ml",
     "Double-wall vacuum flask. Keeps drinks hot for 12h, cold for 24h.",
     "29.00", "Home", 55),
    ("Cotton T-Shirt Basic",
     "100% organic combed cotton, pre-shrunk. Unisex regular fit.",
     "19.00", "Fashion", 200),
    ("Denim Jacket Classic",
     "Rigid denim that fades beautifully. Two chest pockets, button front.",
     "79.00", "Fashion", 22),
    ("Yoga Mat Pro 6mm",
     "Non-slip TPE mat with alignment lines. Comes with carry strap.",
     "35.00", "Sports", 45),
    ("Dumbbell Set 2x5kg",
     "Neoprene-coated hex dumbbells with anti-roll design.",
     "55.00", "Sports", 30),
]

SEED_REVIEWS = [
    (1, 3, 5, "Best earbuds I have owned. ANC is superb on the metro."),
    (1, 1, 4, "Sound is great, though the case is a bit bulky for small pockets."),
    (2, 2, 5, "Took this on a hiking trip - battery lasted the whole weekend."),
    (3, 1, 4, "Accurate tracking, sleep insights are genuinely useful."),
    (6, 3, 5, "The glaze color is even nicer in person. Great gift set."),
    (8, 2, 5, "Coffee still hot after a full morning shift. Solid build."),
    (11, 3, 4, "Grippy and comfortable, the alignment lines help a lot."),
]

SEED_FAVORITES = [
    (1, 3, "Maybe get this for my birthday"),
    (1, 5, "Check Black Friday price"),
    (2, 12, ""),
    (3, 6, "Nice gift idea for mom"),
]

SEED_INQUIRIES = [
    ("Alice Nguyen", "alice.nguyen@mail.com", "Return request for order #10231",
     "Hi, I received the wrong color mug set in order #10231. "
     "How do I arrange a return? Thanks!",
     "new"),
    ("Bob Tran", "bob.tran@mail.com", "Warranty for Smart Watch X2",
     "The strap of my watch broke after three weeks. "
     "Serial number SWX2-88123. Is this covered by warranty?",
     "answered"),
    ("Carol Le", "carol.le@mail.com", "Bulk order discount",
     "I would like to order 30 ceramic mug sets for our office. "
     "Do you offer bulk pricing? You can reach me at 0903-221-884.",
     "new"),
    ("David Pham", "david.pham@mail.com", "Delivery to apartment",
     "Please call 0918-774-512 before delivering, the buzzer at "
     "12 Nguyen Hue, Apt 9B does not work.", "new"),
]

SEED_DRAFTS = [
    (1, "Review draft - Wireless Earbuds Pro",
     "Three weeks in: ANC still impresses, call quality is average on windy "
     "days. Will mention battery life in the final review."),
    (2, "Complaint draft - late delivery",
     "Order #10248 arrived nine days late. I want to ask support for a "
     "shipping refund, my phone number is 0913-445-209 in case they call."),
    (3, "Gift ideas",
     "Thermos for dad, scented candles for Linh, and maybe the denim jacket "
     "for myself if the price drops below $70."),
]


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------

def connect():
    return psycopg2.connect(DATABASE_URL,
                            cursor_factory=psycopg2.extras.RealDictCursor)


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, params=None, db=None):
    cur = (db or get_db()).cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def execute(sql, params=None, db=None):
    db = db or get_db()
    cur = db.cursor()
    cur.execute(sql, params)
    db.commit()
    return cur


def init_db(retries=30, delay=2):
    for i in range(retries):
        try:
            db = connect()
            break
        except psycopg2.OperationalError:
            if i == retries - 1:
                raise
            time.sleep(delay)
    with db:
        with db.cursor() as cur:
            cur.execute(SCHEMA)
        if query("SELECT COUNT(*) AS n FROM users", db=db)[0]["n"] == 0:
            for u in SEED_USERS:
                execute(
                    "INSERT INTO users (username, password_hash, full_name,"
                    " email, bio) VALUES (%s,%s,%s,%s,%s)",
                    (u[0], generate_password_hash(u[1]), u[2], u[3], u[4]),
                    db=db)
            for p in SEED_PRODUCTS:
                execute(
                    "INSERT INTO products (name, description, price,"
                    " category, stock) VALUES (%s,%s,%s,%s,%s)",
                    (p[0], p[1], p[2], p[3], p[4]), db=db)
            for r in SEED_REVIEWS:
                execute(
                    "INSERT INTO reviews (product_id, user_id, rating,"
                    " comment) VALUES (%s,%s,%s,%s)", r, db=db)
            for f in SEED_FAVORITES:
                execute(
                    "INSERT INTO favorites (user_id, product_id, note)"
                    " VALUES (%s,%s,%s)", f, db=db)
            for i in SEED_INQUIRIES:
                execute(
                    "INSERT INTO inquiries (name, email, subject, message,"
                    " status) VALUES (%s,%s,%s,%s,%s)", i, db=db)
            for d in SEED_DRAFTS:
                execute(
                    "INSERT INTO drafts (user_id, title, content)"
                    " VALUES (%s,%s,%s)", d, db=db)
    db.close()


# --------------------------------------------------------------------------
# Auth plumbing
# --------------------------------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def load_user():
    g.user = None
    uid = session.get("user_id")
    if uid is not None:
        rows = query("SELECT id, username, full_name, email, bio FROM users"
                     " WHERE id = %s", (uid,))
        g.user = rows[0] if rows else None


# --------------------------------------------------------------------------
# Public pages
# --------------------------------------------------------------------------

@app.route("/")
def index():
    featured = query("SELECT id, name, description, price, category FROM"
                     " products ORDER BY id LIMIT 4")
    return render_template("index.html", featured=featured)


@app.route("/shop")
def shop():
    q = (request.args.get("q") or "").strip()
    category = (request.args.get("category") or "").strip()

    sql = "SELECT id, name, description, price, category FROM products"
    conditions = []
    params = []
    if category:
        conditions.append("category = %s")
        params.append(category)
    if q:
        conditions.append(
            "id IN (SELECT id FROM products WHERE name ILIKE '%" + q + "%')")
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id"

    try:
        products = query(sql, params or None)
    except psycopg2.Error:
        get_db().rollback()
        products = []

    categories = [r["category"] for r in
                  query("SELECT DISTINCT category FROM products"
                        " ORDER BY category")]
    return render_template("shop.html", products=products, q=q,
                           category=category, categories=categories)


@app.route("/product/<int:pid>")
def product_page(pid):
    rows = query("SELECT id, name, description, price, category, stock FROM"
                 " products WHERE id = %s", (pid,))
    if not rows:
        abort(404)
    product = rows[0]
    reviews = query(
        "SELECT r.rating, r.comment, r.created_at, u.username FROM reviews r"
        " JOIN users u ON u.id = r.user_id WHERE r.product_id = %s"
        " ORDER BY r.id DESC", (pid,))
    fav = None
    if g.user:
        fav = query("SELECT product_id FROM favorites WHERE user_id = %s AND"
                    " product_id = %s", (g.user["id"], pid))
    return render_template("product.html", p=product, reviews=reviews,
                           is_favorite=bool(fav))


@app.route("/product/<int:pid>/review", methods=["POST"])
@login_required
def post_review(pid):
    rows = query("SELECT id FROM products WHERE id = %s", (pid,))
    if not rows:
        abort(404)
    rating = request.form.get("rating", "5")
    rating = int(rating) if rating.isdigit() else 5
    rating = min(max(rating, 1), 5)
    comment = (request.form.get("comment") or "").strip()[:2000]
    if comment:
        execute("INSERT INTO reviews (product_id, user_id, rating, comment)"
                " VALUES (%s,%s,%s,%s)", (pid, g.user["id"], rating, comment))
    return redirect(url_for("product_page", pid=pid))


# --------------------------------------------------------------------------
# Account
# --------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        full_name = (request.form.get("full_name") or "").strip()
        email = (request.form.get("email") or "").strip()
        error = None
        if not (3 <= len(username) <= 30) or not username.replace(
                "_", "").replace("-", "").replace(".", "").isalnum():
            error = "Username must be 3-30 letters, numbers, ., - or _"
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        if error:
            flash(error)
            return render_template("register.html"), 400
        try:
            execute("INSERT INTO users (username, password_hash, full_name,"
                    " email) VALUES (%s,%s,%s,%s)",
                    (username, generate_password_hash(password), full_name,
                     email))
        except psycopg2.IntegrityError:
            flash("That username is already taken.")
            return render_template("register.html"), 400
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.values.get("next") or "/"
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        rows = query("SELECT id, password_hash FROM users WHERE username = %s",
                     (username,))
        if rows and check_password_hash(rows[0]["password_hash"], password):
            session.clear()
            session["user_id"] = rows[0]["id"]
            return redirect(next_url)
        flash("Invalid username or password.")
        return render_template("login.html", next=next_url), 401
    return render_template("login.html", next=next_url)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------

@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", user=g.user)


@app.route("/profile/update", methods=["POST"])
@login_required
def profile_update():
    user_id = request.form.get("user_id") or str(g.user["id"])
    full_name = (request.form.get("full_name") or "").strip()[:120]
    email = (request.form.get("email") or "").strip()[:200]
    bio = (request.form.get("bio") or "").strip()[:1000]
    try:
        target = int(user_id)
    except ValueError:
        target = g.user["id"]
    execute("UPDATE users SET full_name = %s, email = %s, bio = %s"
            " WHERE id = %s", (full_name, email, bio, target))
    return redirect("/profile#updated=" + quote(full_name))


# --------------------------------------------------------------------------
# Favorites
# --------------------------------------------------------------------------

@app.route("/favorites")
@login_required
def favorites_page():
    added = request.args.get("added")
    rows = query(
        "SELECT f.product_id, f.note, p.name, p.price, p.category"
        " FROM favorites f JOIN products p ON p.id = f.product_id"
        " WHERE f.user_id = %s ORDER BY f.created_at DESC", (g.user["id"],))
    return render_template("favorites.html", favorites=rows, added=added)


@app.route("/favorites/toggle/<int:pid>")
@login_required
def favorites_toggle(pid):
    rows = query("SELECT id FROM products WHERE id = %s", (pid,))
    if not rows:
        abort(404)
    existing = query("SELECT product_id FROM favorites WHERE user_id = %s AND"
                     " product_id = %s", (g.user["id"], pid))
    if existing:
        execute("DELETE FROM favorites WHERE user_id = %s AND product_id = %s",
                (g.user["id"], pid))
        return redirect(url_for("favorites_page"))
    product = query("SELECT name FROM products WHERE id = %s", (pid,))[0]
    execute("INSERT INTO favorites (user_id, product_id) VALUES (%s,%s)",
            (g.user["id"], pid))
    return redirect(url_for("favorites_page", added=product["name"]))


@app.route("/favorites/note", methods=["POST"])
@login_required
def favorites_note():
    try:
        pid = int(request.form.get("product_id", ""))
    except ValueError:
        abort(404)
    note = (request.form.get("note") or "").strip()[:500]
    execute("UPDATE favorites SET note = %s WHERE user_id = %s AND"
            " product_id = %s", (note, g.user["id"], pid))
    return redirect(url_for("favorites_page"))


# --------------------------------------------------------------------------
# Contact / support
# --------------------------------------------------------------------------

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()[:120]
        email = (request.form.get("email") or "").strip()[:200]
        subject = (request.form.get("subject") or "").strip()[:200]
        message = (request.form.get("message") or "").strip()[:4000]
        if not (name and email and message):
            flash("Please fill in your name, email and message.")
            return render_template("contact.html"), 400
        cur = execute("INSERT INTO inquiries (name, email, subject, message)"
                      " VALUES (%s,%s,%s,%s) RETURNING id",
                      (name, email, subject, message))
        ticket_id = cur.fetchone()["id"]
        try:
            history = query(
                "SELECT id, subject, created_at FROM inquiries"
                " WHERE email = '" + email + "'"
                " ORDER BY id DESC LIMIT 5")
        except psycopg2.Error:
            get_db().rollback()
            history = []
        return render_template("contact_done.html", name=name,
                               ticket_id=ticket_id, history=history)
    return render_template("contact.html")


@app.route("/support/ticket/<int:tid>")
@login_required
def support_ticket(tid):
    rows = query("SELECT id, name, email, subject, message, status,"
                 " created_at FROM inquiries WHERE id = %s", (tid,))
    if not rows:
        abort(404)
    return render_template("ticket.html", t=rows[0])


# --------------------------------------------------------------------------
# Drafts
# --------------------------------------------------------------------------

@app.route("/drafts")
@login_required
def drafts_list():
    rows = query("SELECT id, title, content, updated_at FROM drafts"
                 " WHERE user_id = %s ORDER BY updated_at DESC", (g.user["id"],))
    return render_template("drafts.html", drafts=rows)


@app.route("/drafts/new", methods=["POST"])
@login_required
def drafts_new():
    title = (request.form.get("title") or "").strip()[:200]
    content = (request.form.get("content") or "").strip()[:4000]
    execute("INSERT INTO drafts (user_id, title, content) VALUES (%s,%s,%s)",
            (g.user["id"], title, content))
    return redirect(url_for("drafts_list"))


@app.route("/drafts/<int:did>/edit", methods=["GET", "POST"])
@login_required
def draft_edit(did):
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()[:200]
        content = (request.form.get("content") or "").strip()[:4000]
        execute("UPDATE drafts SET title = %s, content = %s, updated_at ="
                " NOW() WHERE id = %s", (title, content, did))
        return redirect(url_for("drafts_list"))
    rows = query("SELECT id, title, content, updated_at FROM drafts"
                 " WHERE id = %s", (did,))
    if not rows:
        abort(404)
    return render_template("draft_edit.html", d=rows[0])


# --------------------------------------------------------------------------
# Downloads
# --------------------------------------------------------------------------

@app.route("/downloads")
def downloads():
    files_dir = os.path.join(app.root_path, "files")
    names = sorted(f for f in os.listdir(files_dir)
                   if os.path.isfile(os.path.join(files_dir, f)))
    return render_template("downloads.html", names=names)


@app.route("/files/download")
def files_download():
    name = request.args.get("name") or ""
    files_dir = os.path.join(app.root_path, "files")
    path = os.path.abspath(os.path.join(files_dir, name))
    if not os.path.isfile(path):
        abort(404)
    return send_file(path, as_attachment=True,
                     download_name=os.path.basename(path))


# --------------------------------------------------------------------------
# Admin
# --------------------------------------------------------------------------

@app.route("/admin")
def admin_index():
    counts = {
        "users": query("SELECT COUNT(*) AS n FROM users")[0]["n"],
        "inquiries": query("SELECT COUNT(*) AS n FROM inquiries")[0]["n"],
    }
    return render_template("admin_index.html", counts=counts)


@app.route("/admin/users")
def admin_users():
    rows = query("SELECT id, username, full_name, email, created_at FROM"
                 " users ORDER BY id")
    return render_template("admin_users.html", users=rows)


@app.route("/admin/inquiries")
def admin_inquiries():
    rows = query("SELECT id, name, email, subject, status, created_at FROM"
                 " inquiries ORDER BY id DESC LIMIT 100")
    return render_template("admin_inquiries.html", inquiries=rows)


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="The page you are looking for does not"
                                   " exist."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500,
                           message="Something went wrong. Please try"
                                   " again."), 500


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=False)
