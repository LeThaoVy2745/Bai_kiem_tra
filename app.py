import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, g

app = Flask(__name__)
app.secret_key = "library-secret"
DATABASE = "library.db"


@app.template_filter("vnd")
def vnd(value):
    return "{:,.0f}".format(value or 0).replace(",", ".") + " đ"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            price REAL DEFAULT 0,
            quantity INTEGER DEFAULT 0,
            category_id INTEGER NOT NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
        );
    """)
    db.commit()
    db.close()


# ---------- DASHBOARD ----------
@app.route("/")
def dashboard():
    db = get_db()
    total_categories = db.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    total_books = db.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    total_quantity = db.execute("SELECT COALESCE(SUM(quantity),0) FROM books").fetchone()[0]
    total_value = db.execute("SELECT COALESCE(SUM(price*quantity),0) FROM books").fetchone()[0]
    stats = db.execute("""
        SELECT c.id, c.name, COUNT(b.id) AS book_count
        FROM categories c LEFT JOIN books b ON b.category_id = c.id
        GROUP BY c.id ORDER BY c.id
    """).fetchall()
    max_count = max([s["book_count"] for s in stats], default=0) or 1
    recent = db.execute("""
        SELECT b.*, c.name AS category_name FROM books b
        JOIN categories c ON c.id = b.category_id
        ORDER BY b.id DESC LIMIT 5
    """).fetchall()
    return render_template("dashboard.html", total_categories=total_categories,
                           total_books=total_books, total_quantity=total_quantity,
                           total_value=total_value, stats=stats,
                           max_count=max_count, recent=recent)


# ---------- CRUD DANH MỤC ----------
@app.route("/categories")
def categories():
    rows = get_db().execute("""
        SELECT c.*, COUNT(b.id) AS book_count
        FROM categories c LEFT JOIN books b ON b.category_id = c.id
        GROUP BY c.id ORDER BY c.id
    """).fetchall()
    return render_template("categories.html", categories=rows)


@app.route("/categories/add", methods=["GET", "POST"])
def add_category():
    if request.method == "POST":
        name = request.form["name"].strip()
        desc = request.form["description"].strip()
        if not name:
            flash("Tên danh mục không được để trống", "danger")
            return render_template("category_form.html", category=None)
        try:
            db = get_db()
            db.execute("INSERT INTO categories (name, description) VALUES (?, ?)", (name, desc))
            db.commit()
            flash("Thêm danh mục thành công", "success")
            return redirect(url_for("categories"))
        except sqlite3.IntegrityError:
            flash("Tên danh mục đã tồn tại", "danger")
    return render_template("category_form.html", category=None)


@app.route("/categories/edit/<int:id>", methods=["GET", "POST"])
def edit_category(id):
    db = get_db()
    category = db.execute("SELECT * FROM categories WHERE id = ?", (id,)).fetchone()
    if category is None:
        flash("Không tìm thấy danh mục", "danger")
        return redirect(url_for("categories"))
    if request.method == "POST":
        name = request.form["name"].strip()
        desc = request.form["description"].strip()
        try:
            db.execute("UPDATE categories SET name = ?, description = ? WHERE id = ?",
                       (name, desc, id))
            db.commit()
            flash("Cập nhật danh mục thành công", "success")
            return redirect(url_for("categories"))
        except sqlite3.IntegrityError:
            flash("Tên danh mục đã tồn tại", "danger")
    return render_template("category_form.html", category=category)


@app.route("/categories/delete/<int:id>", methods=["POST"])
def delete_category(id):
    db = get_db()
    db.execute("DELETE FROM categories WHERE id = ?", (id,))
    db.commit()
    flash("Đã xóa danh mục (và các sách thuộc danh mục)", "success")
    return redirect(url_for("categories"))


# ---------- CRUD SÁCH ----------
@app.route("/books")
def books():
    db = get_db()
    category_id = request.args.get("category_id", type=int)
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sql = """SELECT b.*, c.name AS category_name FROM books b
             JOIN categories c ON c.id = b.category_id"""
    params = ()
    if category_id:
        sql += " WHERE b.category_id = ?"
        params = (category_id,)
    sql += " ORDER BY b.id"
    rows = db.execute(sql, params).fetchall()
    return render_template("books.html", books=rows, categories=cats,
                           selected=category_id)


@app.route("/books/add", methods=["GET", "POST"])
def add_book():
    db = get_db()
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if request.method == "POST":
        db.execute(
            "INSERT INTO books (title, author, price, quantity, category_id) VALUES (?,?,?,?,?)",
            (request.form["title"].strip(), request.form["author"].strip(),
             request.form.get("price", 0) or 0, request.form.get("quantity", 0) or 0,
             request.form["category_id"]))
        db.commit()
        flash("Thêm sách thành công", "success")
        return redirect(url_for("books"))
    preselect = request.args.get("category_id", type=int)
    return render_template("book_form.html", book=None, categories=cats, preselect=preselect)


@app.route("/books/edit/<int:id>", methods=["GET", "POST"])
def edit_book(id):
    db = get_db()
    book = db.execute("SELECT * FROM books WHERE id = ?", (id,)).fetchone()
    if book is None:
        flash("Không tìm thấy sách", "danger")
        return redirect(url_for("books"))
    cats = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if request.method == "POST":
        db.execute(
            """UPDATE books SET title=?, author=?, price=?, quantity=?, category_id=?
               WHERE id=?""",
            (request.form["title"].strip(), request.form["author"].strip(),
             request.form.get("price", 0) or 0, request.form.get("quantity", 0) or 0,
             request.form["category_id"], id))
        db.commit()
        flash("Cập nhật sách thành công", "success")
        return redirect(url_for("books"))
    return render_template("book_form.html", book=book, categories=cats, preselect=None)


@app.route("/books/delete/<int:id>", methods=["POST"])
def delete_book(id):
    db = get_db()
    db.execute("DELETE FROM books WHERE id = ?", (id,))
    db.commit()
    flash("Đã xóa sách", "success")
    return redirect(url_for("books"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)