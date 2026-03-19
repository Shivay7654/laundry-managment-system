"""
Laundry Management System (LMS)
================================
Requirements:  pip install PyQt6
Run:           python laundry_management.py

Backend : SQLite  (laundry.db created automatically on first run)
Discount: DB-backed discount types · coupon codes · custom % · live breakdown
"""

import sys
import sqlite3
import os
import hashlib
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QGridLayout, QLineEdit, QCalendarWidget,
    QComboBox, QDialog, QDialogButtonBox, QMessageBox, QStackedWidget,
    QAbstractItemView, QSizePolicy, QFormLayout, QTabWidget,
    QSpinBox, QDoubleSpinBox, QCheckBox,
)
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QFont, QColor


# ═══════════════════════════════════════════════════════════
#  DATABASE LAYER
# ═══════════════════════════════════════════════════════════
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "laundry.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _get_columns(conn, table):
    """Return set of column names for a table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _add_column_if_missing(conn, table, column, definition):
    if column not in _get_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS customers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE,
                phone      TEXT,
                email      TEXT,
                notes      TEXT,
                created_at TEXT    DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS discount_types (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                kind        TEXT    NOT NULL DEFAULT 'percent',
                value       REAL    NOT NULL DEFAULT 0,
                applies_to  TEXT    NOT NULL DEFAULT 'order',
                active      INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS coupon_codes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT    NOT NULL UNIQUE,
                kind        TEXT    NOT NULL DEFAULT 'percent',
                value       REAL    NOT NULL DEFAULT 0,
                min_order   REAL    NOT NULL DEFAULT 0,
                max_uses    INTEGER NOT NULL DEFAULT 0,
                used_count  INTEGER NOT NULL DEFAULT 0,
                active      INTEGER NOT NULL DEFAULT 1,
                expires_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id     INTEGER NOT NULL REFERENCES customers(id),
                collection_date TEXT    NOT NULL,
                discount_type_id INTEGER,
                discount_pct    REAL    NOT NULL DEFAULT 0,
                coupon_id       INTEGER,
                coupon_value    REAL    NOT NULL DEFAULT 0,
                subtotal        REAL    NOT NULL DEFAULT 0,
                discount_amount REAL    NOT NULL DEFAULT 0,
                total_amount    REAL    NOT NULL DEFAULT 0,
                status          TEXT    NOT NULL DEFAULT 'Pending',
                created_at      TEXT    DEFAULT (datetime('now')),
                FOREIGN KEY (customer_id)      REFERENCES customers(id),
                FOREIGN KEY (discount_type_id) REFERENCES discount_types(id),
                FOREIGN KEY (coupon_id)        REFERENCES coupon_codes(id)
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id          INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                item_name         TEXT    NOT NULL,
                quantity          INTEGER NOT NULL,
                unit_price        REAL    NOT NULL,
                item_discount_pct REAL    NOT NULL DEFAULT 0,
                line_total        REAL    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                username     TEXT    NOT NULL UNIQUE,
                password_hash TEXT   NOT NULL,
                full_name    TEXT    NOT NULL DEFAULT '',
                email        TEXT    NOT NULL DEFAULT '',
                phone        TEXT    NOT NULL DEFAULT '',
                role         TEXT    NOT NULL DEFAULT 'staff',
                active       INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT    DEFAULT (datetime('now'))
            );
        """)

        # ── Migrate existing databases: add any missing columns ─────────
        _add_column_if_missing(conn, "orders", "discount_type_id", "INTEGER")
        _add_column_if_missing(conn, "orders", "coupon_id",        "INTEGER")
        _add_column_if_missing(conn, "orders", "coupon_value",     "REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "orders", "subtotal",         "REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "orders", "discount_amount",  "REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "orders", "discount_pct",     "REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "order_items", "item_discount_pct", "REAL NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "users", "full_name", "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "users", "email",     "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "users", "phone",     "TEXT NOT NULL DEFAULT ''")
        _add_column_if_missing(conn, "users", "role",      "TEXT NOT NULL DEFAULT 'staff'")
        _add_column_if_missing(conn, "users", "active",    "INTEGER NOT NULL DEFAULT 1")

        # ── Seed default admin user (username: admin / password: admin123) ─
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (username,password_hash,full_name,email,role) VALUES (?,?,?,?,?)",
                ("admin", _hash_password("admin123"), "Administrator", "admin@laundry.com", "admin"),
            )

        if conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO customers (name,phone,email,notes) VALUES (?,?,?,?)",
                [("om","","",""),("Sagar","","",""),("Ramesh","","",""),
                 ("Ram","","",""),("Sujita","","","")],
            )

        if conn.execute("SELECT COUNT(*) FROM discount_types").fetchone()[0] == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO discount_types (name,kind,value,applies_to) VALUES (?,?,?,?)",
                [("Student","percent",10,"order"),("Senior","percent",15,"order"),
                 ("VIP","percent",20,"order"),("Promo","percent",25,"order"),
                 ("Loyalty £5","fixed",5,"order")],
            )

        if conn.execute("SELECT COUNT(*) FROM coupon_codes").fetchone()[0] == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO coupon_codes (code,kind,value,min_order,max_uses) VALUES (?,?,?,?,?)",
                [("WELCOME10","percent",10,0,100),("SAVE5","fixed",5,20,50),
                 ("VIP30","percent",30,50,10)],
            )


# ── Discount types CRUD ─────────────────────────────────────
def db_get_discount_types(active_only=True):
    q = "SELECT * FROM discount_types"
    if active_only:
        q += " WHERE active=1"
    q += " ORDER BY name"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]


def db_add_discount_type(name, kind, value, applies_to):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO discount_types (name,kind,value,applies_to) VALUES (?,?,?,?)",
            (name, kind, value, applies_to),
        )


def db_update_discount_type(did, name, kind, value, applies_to, active):
    with get_connection() as conn:
        conn.execute(
            "UPDATE discount_types SET name=?,kind=?,value=?,applies_to=?,active=? WHERE id=?",
            (name, kind, value, applies_to, active, did),
        )


def db_delete_discount_type(did):
    with get_connection() as conn:
        conn.execute("DELETE FROM discount_types WHERE id=?", (did,))


# ── Coupon CRUD ─────────────────────────────────────────────
def db_get_coupons(active_only=False):
    q = "SELECT * FROM coupon_codes"
    if active_only:
        q += " WHERE active=1"
    q += " ORDER BY code"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(q).fetchall()]


def db_validate_coupon(code, order_subtotal):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM coupon_codes WHERE code=? AND active=1", (code,)
        ).fetchone()
    if not row:
        return "Coupon code not found or inactive."
    row = dict(row)
    if row["expires_at"]:
        try:
            exp = datetime.strptime(row["expires_at"], "%Y-%m-%d").date()
            if datetime.today().date() > exp:
                return "Coupon has expired."
        except ValueError:
            pass
    if row["max_uses"] > 0 and row["used_count"] >= row["max_uses"]:
        return "Coupon has reached its usage limit."
    if order_subtotal < row["min_order"]:
        return f"Minimum order £{row['min_order']:.2f} required."
    return row


def db_increment_coupon_usage(coupon_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE coupon_codes SET used_count = used_count + 1 WHERE id=?",
            (coupon_id,),
        )


def db_add_coupon(code, kind, value, min_order, max_uses, expires_at):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO coupon_codes (code,kind,value,min_order,max_uses,expires_at) VALUES (?,?,?,?,?,?)",
            (code, kind, value, min_order, max_uses, expires_at or None),
        )


def db_update_coupon(cid, code, kind, value, min_order, max_uses, expires_at, active):
    with get_connection() as conn:
        conn.execute(
            "UPDATE coupon_codes SET code=?,kind=?,value=?,min_order=?,max_uses=?,expires_at=?,active=? WHERE id=?",
            (code, kind, value, min_order, max_uses, expires_at or None, active, cid),
        )


def db_delete_coupon(cid):
    with get_connection() as conn:
        conn.execute("DELETE FROM coupon_codes WHERE id=?", (cid,))


# ── Customer CRUD ───────────────────────────────────────────
def db_get_customers():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,name,phone,email,notes FROM customers ORDER BY name").fetchall()]


def db_add_customer(name, phone="", email="", notes=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO customers (name,phone,email,notes) VALUES (?,?,?,?)",
            (name, phone, email, notes),
        )


def db_update_customer(cid, name, phone, email, notes):
    with get_connection() as conn:
        conn.execute(
            "UPDATE customers SET name=?,phone=?,email=?,notes=? WHERE id=?",
            (name, phone, email, notes, cid),
        )


def db_delete_customer(cid):
    with get_connection() as conn:
        conn.execute("DELETE FROM customers WHERE id=?", (cid,))


# ── Order CRUD ──────────────────────────────────────────────
def db_save_order(customer_id, collection_date_str, discount_type_id,
                  discount_pct, coupon_id, coupon_value, subtotal,
                  discount_amount, total_amount, items):
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO orders
               (customer_id,collection_date,discount_type_id,discount_pct,
                coupon_id,coupon_value,subtotal,discount_amount,total_amount)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (customer_id, collection_date_str, discount_type_id, discount_pct,
             coupon_id, coupon_value, subtotal, discount_amount, total_amount),
        )
        order_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO order_items (order_id,item_name,quantity,unit_price,item_discount_pct,line_total) VALUES (?,?,?,?,?,?)",
            [(order_id, name, qty, price, item_disc, qty * price * (1 - item_disc / 100))
             for name, qty, price, item_disc in items],
        )
    if coupon_id:
        db_increment_coupon_usage(coupon_id)
    return order_id


def db_get_orders(customer_id=None, status=None):
    q = """SELECT o.id, c.name as customer_name, o.collection_date,
                  o.discount_pct, o.coupon_value, o.subtotal,
                  o.discount_amount, o.total_amount, o.status, o.created_at
           FROM orders o JOIN customers c ON c.id=o.customer_id WHERE 1=1"""
    params = []
    if customer_id:
        q += " AND o.customer_id=?"; params.append(customer_id)
    if status:
        q += " AND o.status=?"; params.append(status)
    q += " ORDER BY o.created_at DESC"
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def db_get_order_items(order_id):
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT item_name,quantity,unit_price,item_discount_pct,line_total FROM order_items WHERE order_id=?",
            (order_id,)).fetchall()]


def db_update_order_status(order_id, status):
    with get_connection() as conn:
        conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))


def db_delete_order(order_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM orders WHERE id=?", (order_id,))


# ── Auth helpers ────────────────────────────────────────────
def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def db_authenticate(username: str, password: str):
    """Returns user dict on success, None on failure."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND active=1", (username,)
        ).fetchone()
    if row and row["password_hash"] == _hash_password(password):
        return dict(row)
    return None


def db_get_users():
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,username,full_name,email,phone,role,active,created_at FROM users ORDER BY username"
        ).fetchall()]


def db_add_user(username, password, full_name, email, phone, role):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (username,password_hash,full_name,email,phone,role) VALUES (?,?,?,?,?,?)",
            (username, _hash_password(password), full_name, email, phone, role),
        )


def db_update_user(uid, username, full_name, email, phone, role, active):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET username=?,full_name=?,email=?,phone=?,role=?,active=? WHERE id=?",
            (username, full_name, email, phone, role, active, uid),
        )


def db_change_password(uid, new_password):
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (_hash_password(new_password), uid),
        )


def db_delete_user(uid):
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (uid,))


# ═══════════════════════════════════════════════════════════
#  STATIC DATA
# ═══════════════════════════════════════════════════════════
CATEGORIES = [
    ("Jackets","🧥"),("Skirt","👗"),("Trousers","👖"),("Coats","🥼"),
    ("Shirts/Blouse","👔"),("2PC Suit","🕴"),("Jumpers","🧣"),("Dress","👘"),
    ("Alterations","✂️"),("Scarfs/Caps","🧤"),("Ironing","🫳"),("Laundry","🧺"),
    ("Duvet","🛏"),("Misc","📦"),("Asian Styles","🪭"),("Leather","🥋"),
]
ITEMS = {
    "Jackets":       [("Jacket Formal",5.25),("Jacket Casual",4.25),("Jacket Heavy",5.50)],
    "Skirt":         [("Plain Skirt",3.50),("Pleated Skirt",4.00),("Long Skirt",4.50)],
    "Trousers":      [("Plain Trousers",3.75),("Jeans",4.00),("Suit Trousers",4.25)],
    "Coats":         [("Short Coat",6.00),("Long Coat",7.50),("Winter Coat",8.00)],
    "Shirts/Blouse": [("Plain Shirt",2.50),("Blouse",3.00),("Dress Shirt",3.50)],
    "2PC Suit":      [("2PC Suit",8.50),("3PC Suit",10.00)],
    "Jumpers":       [("Plain Jumper",3.50),("Wool Jumper",4.50)],
    "Dress":         [("Dress General",5.00),("Plain Dress",4.50),("Full Evening Dress",9.50),
                      ("Delicate Dress",7.00),("VIP Dress",12.00),("3/4 Length Dress",6.50)],
    "Alterations":   [("Hem Trousers",8.00),("Zip Repair",6.00),("Take In/Out",10.00)],
    "Scarfs/Caps":   [("Scarf",3.00),("Cap/Hat",3.50)],
    "Ironing":       [("Iron Shirt",2.00),("Iron Trousers",2.00),("Iron Dress",3.00)],
    "Laundry":       [("Wash & Fold (kg)",3.50),("Wash & Press (kg)",5.00)],
    "Duvet":         [("Single Duvet",12.00),("Double Duvet",15.00),("King Duvet",18.00)],
    "Misc":          [("Tie",2.50),("Belt",3.00),("Other",4.00)],
    "Asian Styles":  [("Shalwar Kameez",8.00),("Sari",10.00),("Lengha",14.00)],
    "Leather":       [("Leather Jacket",12.00),("Leather Trousers",10.00)],
}
ORDER_STATUSES = ["Pending","Ready","Collected","Cancelled"]


# ═══════════════════════════════════════════════════════════
#  PRICING ENGINE
# ═══════════════════════════════════════════════════════════
def compute_totals(order_items, type_disc_pct, coupon, custom_pct):
    subtotal = sum(qty * price * (1 - item_disc / 100)
                   for _, qty, price, item_disc in order_items)
    eff_pct = max(type_disc_pct, custom_pct)
    type_disc_amt = round(subtotal * eff_pct / 100, 2)
    after_type = subtotal - type_disc_amt
    coupon_disc_amt = 0.0
    if coupon:
        if coupon["kind"] == "percent":
            coupon_disc_amt = round(after_type * coupon["value"] / 100, 2)
        else:
            coupon_disc_amt = min(coupon["value"], after_type)
    grand_total = max(0.0, after_type - coupon_disc_amt)
    total_discount = subtotal - grand_total
    return {
        "subtotal":        round(subtotal, 2),
        "type_disc_pct":   eff_pct,
        "type_disc_amt":   type_disc_amt,
        "coupon_disc_amt": coupon_disc_amt,
        "total_discount":  round(total_discount, 2),
        "grand_total":     round(grand_total, 2),
    }


# ═══════════════════════════════════════════════════════════
#  STYLES
# ═══════════════════════════════════════════════════════════
STYLE = """
QMainWindow, QWidget#central { background:#f0f2f5; }

QPushButton#tab_btn {
    background:#dde3ee; color:#445; border:none;
    border-radius:8px; padding:8px 18px; font-size:13px; font-weight:600;
}
QPushButton#tab_btn:checked {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #4a90d9,stop:1 #5ba8f5);
    color:white;
}
QPushButton#tab_btn:hover:!checked { background:#ccd4e8; }

QPushButton#cat_btn {
    background:white; border:1.5px solid #dde; border-radius:10px;
    padding:6px 4px; font-size:11px; color:#334;
}
QPushButton#cat_btn:checked {
    background:#e8f0fe; border:2px solid #4a90d9; color:#1a56b0; font-weight:700;
}
QPushButton#cat_btn:hover:!checked { background:#f5f7ff; }

QPushButton#item_btn {
    background:white; border:1.5px solid #dde; border-radius:8px;
    padding:8px 6px; font-size:12px; color:#334; text-align:left;
}
QPushButton#item_btn:hover { background:#e8f0fe; border-color:#4a90d9; color:#1a56b0; }

QPushButton#disc_type_btn {
    background:white; border:2px solid #dde; border-radius:10px;
    padding:10px 8px; font-size:12px; color:#334; font-weight:600;
}
QPushButton#disc_type_btn:checked {
    background:#e8f0fe; border:2px solid #4a90d9; color:#1a56b0;
}
QPushButton#disc_type_btn:hover:!checked { background:#f5f7ff; }

QTableWidget {
    background:white; border:none; border-radius:10px;
    gridline-color:#eee; font-size:13px;
}
QTableWidget::item { padding:6px 8px; }
QTableWidget::item:selected { background:#e8f0fe; color:#1a56b0; }
QHeaderView::section {
    background:#f7f9fc; color:#667; font-weight:700; font-size:12px;
    padding:8px; border:none; border-bottom:2px solid #dde;
}

QPushButton#btn_back {
    background:#9b59b6; color:white; border:none; border-radius:10px;
    font-size:15px; font-weight:700; padding:14px;
}
QPushButton#btn_back:hover { background:#8e44ad; }
QPushButton#btn_delete {
    background:#e74c3c; color:white; border:none; border-radius:10px;
    font-size:15px; font-weight:700; padding:14px;
}
QPushButton#btn_delete:hover { background:#c0392b; }
QPushButton#btn_next {
    background:#27ae60; color:white; border:none; border-radius:10px;
    font-size:15px; font-weight:700; padding:14px;
}
QPushButton#btn_next:hover { background:#219a52; }

QFrame#card { background:white; border-radius:12px; border:1px solid #e0e4ed; }
QFrame#disc_breakdown {
    background:#f7fbff; border-radius:10px; border:1.5px solid #c8dff8;
}

QLineEdit, QComboBox {
    background:white; border:1.5px solid #ccd; border-radius:8px;
    padding:7px 10px; font-size:13px; color:#334;
}
QLineEdit:focus, QComboBox:focus { border-color:#4a90d9; }
QComboBox::drop-down { border:none; width:24px; }

QPushButton#num_btn {
    background:#2c3e7a; color:white; border:none; border-radius:8px;
    font-size:16px; font-weight:700;
}
QPushButton#num_btn:hover { background:#3d52a0; }
QPushButton#num_btn:pressed { background:#1a2755; }

QCalendarWidget QWidget { background:white; }
QCalendarWidget QToolButton {
    background:#4a90d9; color:white; border-radius:6px;
    padding:4px 8px; font-weight:700;
}

QScrollArea { border:none; background:transparent; }
QScrollBar:vertical { width:6px; background:#f0f2f5; border-radius:3px; }
QScrollBar::handle:vertical { background:#bbc; border-radius:3px; min-height:30px; }

QPushButton#btn_sm_green {
    background:#27ae60; color:white; border:none;
    border-radius:6px; font-size:12px; font-weight:700; padding:6px 14px;
}
QPushButton#btn_sm_green:hover { background:#219a52; }
QPushButton#btn_sm_red {
    background:#e74c3c; color:white; border:none;
    border-radius:6px; font-size:12px; font-weight:700; padding:6px 14px;
}
QPushButton#btn_sm_red:hover { background:#c0392b; }
QPushButton#btn_sm_blue {
    background:#4a90d9; color:white; border:none;
    border-radius:6px; font-size:12px; font-weight:700; padding:6px 14px;
}
QPushButton#btn_sm_blue:hover { background:#357abd; }
QPushButton#btn_apply_coupon {
    background:#f39c12; color:white; border:none;
    border-radius:8px; font-size:13px; font-weight:700; padding:8px 18px;
}
QPushButton#btn_apply_coupon:hover { background:#d68910; }
QPushButton#btn_clear_disc {
    background:#95a5a6; color:white; border:none;
    border-radius:8px; font-size:12px; font-weight:700; padding:7px 14px;
}
QPushButton#btn_clear_disc:hover { background:#7f8c8d; }
"""


# ═══════════════════════════════════════════════════════════
#  DIALOGS
# ═══════════════════════════════════════════════════════════
class CustomerDialog(QDialog):
    def __init__(self, parent=None, customer=None):
        super().__init__(parent)
        self.setWindowTitle("Add Customer" if customer is None else "Edit Customer")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit  = QLineEdit(customer["name"]  if customer else "")
        self.phone_edit = QLineEdit(customer["phone"] if customer else "")
        self.email_edit = QLineEdit(customer["email"] if customer else "")
        self.notes_edit = QLineEdit(customer["notes"] if customer else "")
        form.addRow("Name *:", self.name_edit)
        form.addRow("Phone:",  self.phone_edit)
        form.addRow("Email:",  self.email_edit)
        form.addRow("Notes:",  self.notes_edit)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Customer name is required."); return
        self.accept()

    def get_data(self):
        return dict(name=self.name_edit.text().strip(), phone=self.phone_edit.text().strip(),
                    email=self.email_edit.text().strip(), notes=self.notes_edit.text().strip())


class DiscountTypeDialog(QDialog):
    def __init__(self, parent=None, dt=None):
        super().__init__(parent)
        self.setWindowTitle("Add Discount Type" if dt is None else "Edit Discount Type")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(dt["name"] if dt else "")
        self.kind_combo = QComboBox(); self.kind_combo.addItems(["percent", "fixed"])
        if dt: self.kind_combo.setCurrentText(dt["kind"])
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(0, 10000); self.value_spin.setDecimals(2)
        self.value_spin.setValue(dt["value"] if dt else 0)
        self.applies_combo = QComboBox(); self.applies_combo.addItems(["order", "item"])
        if dt: self.applies_combo.setCurrentText(dt["applies_to"])
        self.active_chk = QCheckBox("Active")
        self.active_chk.setChecked(bool(dt["active"]) if dt else True)
        form.addRow("Name *:",     self.name_edit)
        form.addRow("Kind:",       self.kind_combo)
        form.addRow("Value:",      self.value_spin)
        form.addRow("Applies to:", self.applies_combo)
        form.addRow("",            self.active_chk)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept(self):
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required."); return
        self.accept()

    def get_data(self):
        return dict(name=self.name_edit.text().strip(), kind=self.kind_combo.currentText(),
                    value=self.value_spin.value(), applies_to=self.applies_combo.currentText(),
                    active=int(self.active_chk.isChecked()))


class CouponDialog(QDialog):
    def __init__(self, parent=None, coupon=None):
        super().__init__(parent)
        self.setWindowTitle("Add Coupon" if coupon is None else "Edit Coupon")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.code_edit = QLineEdit(coupon["code"] if coupon else "")
        self.kind_combo = QComboBox(); self.kind_combo.addItems(["percent", "fixed"])
        if coupon: self.kind_combo.setCurrentText(coupon["kind"])
        self.value_spin = QDoubleSpinBox()
        self.value_spin.setRange(0, 10000); self.value_spin.setDecimals(2)
        self.value_spin.setValue(coupon["value"] if coupon else 0)
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(0, 10000); self.min_spin.setDecimals(2)
        self.min_spin.setValue(coupon["min_order"] if coupon else 0)
        self.maxuse_spin = QSpinBox()
        self.maxuse_spin.setRange(0, 99999)
        self.maxuse_spin.setValue(coupon["max_uses"] if coupon else 0)
        self.maxuse_spin.setSpecialValueText("Unlimited")
        self.expires_edit = QLineEdit(coupon["expires_at"] or "" if coupon else "")
        self.expires_edit.setPlaceholderText("YYYY-MM-DD  (leave blank = never)")
        self.active_chk = QCheckBox("Active")
        self.active_chk.setChecked(bool(coupon["active"]) if coupon else True)
        form.addRow("Code *:",      self.code_edit)
        form.addRow("Type:",        self.kind_combo)
        form.addRow("Value:",       self.value_spin)
        form.addRow("Min order £:", self.min_spin)
        form.addRow("Max uses:",    self.maxuse_spin)
        form.addRow("Expires:",     self.expires_edit)
        form.addRow("",             self.active_chk)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept(self):
        if not self.code_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Code is required."); return
        self.accept()

    def get_data(self):
        return dict(code=self.code_edit.text().strip().upper(),
                    kind=self.kind_combo.currentText(),
                    value=self.value_spin.value(), min_order=self.min_spin.value(),
                    max_uses=self.maxuse_spin.value(),
                    expires_at=self.expires_edit.text().strip() or "",
                    active=int(self.active_chk.isChecked()))


class OrderDetailDialog(QDialog):
    def __init__(self, parent, order):
        super().__init__(parent)
        self.setWindowTitle(f"Order #{order['id']} – {order['customer_name']}")
        self.setMinimumSize(560, 460)
        layout = QVBoxLayout(self)
        info = (f"<b>Customer:</b> {order['customer_name']}<br>"
                f"<b>Collection:</b> {order['collection_date']}<br>"
                f"<b>Subtotal:</b> £{order['subtotal']:.2f}<br>"
                f"<b>Discount saved:</b> £{order['discount_amount']:.2f}<br>"
                f"<b>Total:</b> £{order['total_amount']:.2f}<br>"
                f"<b>Status:</b> {order['status']}<br>"
                f"<b>Created:</b> {order['created_at']}")
        lbl = QLabel(info); lbl.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(lbl)
        items = db_get_order_items(order["id"])
        tbl = QTableWidget(len(items), 5)
        tbl.setHorizontalHeaderLabels(["Item","Qty","Unit Price","Item Disc%","Line Total"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        for r, it in enumerate(items):
            for c, val in enumerate([it["item_name"], str(it["quantity"]),
                                      f"£{it['unit_price']:.2f}",
                                      f"{it['item_discount_pct']:.0f}%",
                                      f"£{it['line_total']:.2f}"]):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tbl.setItem(r, c, cell)
        layout.addWidget(tbl)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)


# ═══════════════════════════════════════════════════════════
#  DISCOUNT PAGE  (fully functional)
# ═══════════════════════════════════════════════════════════
class DiscountPage(QWidget):
    discount_changed = pyqtSignal(float, object, float)

    def __init__(self, get_subtotal_fn):
        super().__init__()
        self._get_subtotal = get_subtotal_fn
        self._selected_type = None
        self._coupon        = None
        self._custom_pct    = 0.0

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(14)

        title = QLabel("🏷️  Discount Pricing")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color:#334;")
        layout.addWidget(title)

        cols = QHBoxLayout(); cols.setSpacing(16)

        left = QVBoxLayout(); left.setSpacing(12)
        left.addWidget(self._build_type_panel())
        left.addWidget(self._build_custom_panel())
        left.addWidget(self._build_coupon_panel())
        left_w = QWidget(); left_w.setLayout(left)
        cols.addWidget(left_w, 3)
        cols.addWidget(self._build_breakdown_panel(), 2)

        layout.addLayout(cols)

    # ── Discount Type panel ────────────────────────────────
    def _build_type_panel(self):
        frame = QFrame(); frame.setObjectName("card")
        fl = QVBoxLayout(frame); fl.setContentsMargins(14,12,14,12); fl.setSpacing(10)

        hdr = QHBoxLayout()
        hdr_lbl = QLabel("📂  Discount Type")
        hdr_lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet("color:#334;")
        clear = QPushButton("Clear"); clear.setObjectName("btn_clear_disc")
        clear.setFixedWidth(60); clear.clicked.connect(self._clear_type)
        hdr.addWidget(hdr_lbl); hdr.addStretch(); hdr.addWidget(clear)
        fl.addLayout(hdr)

        self._type_btn_group = []
        self._type_grid = QGridLayout(); self._type_grid.setSpacing(8)
        fl.addLayout(self._type_grid)
        self._reload_type_buttons()
        return frame

    def _reload_type_buttons(self):
        for i in reversed(range(self._type_grid.count())):
            w = self._type_grid.itemAt(i).widget()
            if w: w.deleteLater()
        self._type_btn_group = []

        types = db_get_discount_types(active_only=True)
        for i, dt in enumerate(types):
            badge = "%" if dt["kind"] == "percent" else "£"
            lbl = (f"{dt['name']}\n{dt['value']:.0f}{badge}"
                   if dt["kind"] == "percent"
                   else f"{dt['name']}\n-£{dt['value']:.2f}")
            btn = QPushButton(lbl); btn.setObjectName("disc_type_btn")
            btn.setCheckable(True); btn.setFixedSize(110, 56)
            btn.clicked.connect(lambda checked, d=dt, b=btn: self._type_selected(d, b))
            self._type_btn_group.append((dt, btn))
            self._type_grid.addWidget(btn, i // 3, i % 3)

    def _type_selected(self, dt, btn):
        # Toggle: clicking active one deselects
        if self._selected_type and self._selected_type["id"] == dt["id"]:
            btn.setChecked(False); self._selected_type = None
        else:
            self._selected_type = dt
            for d2, b2 in self._type_btn_group:
                b2.setChecked(d2["id"] == dt["id"])
        self._custom_pct = 0.0
        self.custom_spin.blockSignals(True)
        self.custom_spin.setValue(0)
        self.custom_spin.blockSignals(False)
        self._emit()

    def _clear_type(self):
        self._selected_type = None
        for _, b in self._type_btn_group:
            b.setChecked(False)
        self._emit()

    # ── Custom % panel ─────────────────────────────────────
    def _build_custom_panel(self):
        frame = QFrame(); frame.setObjectName("card")
        fl = QHBoxLayout(frame); fl.setContentsMargins(14,10,14,10); fl.setSpacing(10)
        lbl = QLabel("✏️  Custom %")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#334;")
        self.custom_spin = QDoubleSpinBox()
        self.custom_spin.setRange(0, 100); self.custom_spin.setDecimals(1)
        self.custom_spin.setSuffix(" %"); self.custom_spin.setFixedWidth(110)
        self.custom_spin.valueChanged.connect(self._custom_changed)
        fl.addWidget(lbl); fl.addStretch(); fl.addWidget(self.custom_spin)
        return frame

    def _custom_changed(self, val):
        self._custom_pct = val
        if val > 0:
            self._selected_type = None
            for _, b in self._type_btn_group:
                b.setChecked(False)
        self._emit()

    # ── Coupon panel ────────────────────────────────────────
    def _build_coupon_panel(self):
        frame = QFrame(); frame.setObjectName("card")
        fl = QVBoxLayout(frame); fl.setContentsMargins(14,12,14,12); fl.setSpacing(8)
        lbl = QLabel("🎟️  Coupon / Promo Code")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#334;")
        fl.addWidget(lbl)

        row = QHBoxLayout()
        self.coupon_edit = QLineEdit()
        self.coupon_edit.setPlaceholderText("Enter code  (e.g. WELCOME10)…")
        self.coupon_edit.setFixedHeight(36)
        apply_btn = QPushButton("Apply"); apply_btn.setObjectName("btn_apply_coupon")
        apply_btn.setFixedHeight(36); apply_btn.clicked.connect(self._apply_coupon)
        clear_btn = QPushButton("✕"); clear_btn.setObjectName("btn_clear_disc")
        clear_btn.setFixedSize(36, 36); clear_btn.clicked.connect(self._clear_coupon)
        row.addWidget(self.coupon_edit, 1); row.addWidget(apply_btn); row.addWidget(clear_btn)
        fl.addLayout(row)

        self.coupon_status = QLabel("")
        self.coupon_status.setWordWrap(True)
        self.coupon_status.setStyleSheet("font-size:12px; color:#667;")
        fl.addWidget(self.coupon_status)
        return frame

    def _apply_coupon(self):
        code = self.coupon_edit.text().strip().upper()
        if not code:
            return
        subtotal = self._get_subtotal()
        result = db_validate_coupon(code, subtotal)
        if isinstance(result, str):
            self.coupon_status.setText(f"❌  {result}")
            self.coupon_status.setStyleSheet("font-size:12px;color:#e74c3c;font-weight:700;")
            self._coupon = None
        else:
            self._coupon = result
            kind_label = (f"{result['value']:.0f}%" if result["kind"] == "percent"
                          else f"£{result['value']:.2f}")
            self.coupon_status.setText(f"✅  Code accepted: -{kind_label} applied!")
            self.coupon_status.setStyleSheet("font-size:12px;color:#27ae60;font-weight:700;")
        self._emit()

    def _clear_coupon(self):
        self._coupon = None
        self.coupon_edit.clear()
        self.coupon_status.setText("")
        self._emit()

    # ── Live breakdown ──────────────────────────────────────
    def _build_breakdown_panel(self):
        outer = QFrame(); outer.setObjectName("card")
        fl = QVBoxLayout(outer); fl.setContentsMargins(14,14,14,14); fl.setSpacing(10)
        lbl = QLabel("💷  Price Breakdown")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl.setStyleSheet("color:#334;")
        fl.addWidget(lbl)

        self.breakdown_frame = QFrame(); self.breakdown_frame.setObjectName("disc_breakdown")
        self.breakdown_layout = QVBoxLayout(self.breakdown_frame)
        self.breakdown_layout.setContentsMargins(12,10,12,10); self.breakdown_layout.setSpacing(6)
        fl.addWidget(self.breakdown_frame)

        self.savings_badge = QLabel("")
        self.savings_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.savings_badge.setStyleSheet(
            "background:#eafaf1;color:#27ae60;font-weight:700;font-size:13px;"
            "border-radius:8px;padding:8px;")
        fl.addWidget(self.savings_badge)
        fl.addStretch()
        self._update_breakdown(compute_totals([], 0, None, 0))
        return outer

    def _update_breakdown(self, t):
        while self.breakdown_layout.count():
            item = self.breakdown_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        def brow(label, value, color="#334", bold=False):
            w = QWidget(); h = QHBoxLayout(w); h.setContentsMargins(0,0,0,0)
            style = f"color:{color};font-size:13px;" + (" font-weight:700;" if bold else "")
            lbl2 = QLabel(label); lbl2.setStyleSheet(style)
            val2 = QLabel(value); val2.setStyleSheet(style)
            val2.setAlignment(Qt.AlignmentFlag.AlignRight)
            h.addWidget(lbl2); h.addStretch(); h.addWidget(val2)
            return w

        self.breakdown_layout.addWidget(brow("Subtotal", f"£{t['subtotal']:.2f}"))
        if t["type_disc_pct"] > 0:
            self.breakdown_layout.addWidget(
                brow(f"Discount ({t['type_disc_pct']:.1f}%)",
                     f"- £{t['type_disc_amt']:.2f}", "#e67e22"))
        if t["coupon_disc_amt"] > 0:
            self.breakdown_layout.addWidget(
                brow("Coupon saving", f"- £{t['coupon_disc_amt']:.2f}", "#8e44ad"))

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#c8dff8;")
        self.breakdown_layout.addWidget(line)
        self.breakdown_layout.addWidget(
            brow("TOTAL", f"£{t['grand_total']:.2f}", "#1a56b0", bold=True))

        if t["total_discount"] > 0:
            self.savings_badge.setText(f"🎉  You're saving  £{t['total_discount']:.2f}!")
            self.savings_badge.setVisible(True)
        else:
            self.savings_badge.setVisible(False)

    # ── Public API ──────────────────────────────────────────
    def refresh_breakdown(self, order_items):
        type_pct, _, coupon, custom_pct = self.get_discount_state()
        t = compute_totals(order_items, type_pct, coupon, custom_pct)
        self._update_breakdown(t)

    def get_discount_state(self):
        type_pct = 0.0; type_id = None
        if self._selected_type:
            if self._selected_type["kind"] == "percent":
                type_pct = self._selected_type["value"]
            type_id = self._selected_type["id"]
        return type_pct, type_id, self._coupon, self._custom_pct

    def reload_types(self):
        self._reload_type_buttons()

    def reset(self):
        self._clear_type(); self._clear_coupon()
        self.custom_spin.blockSignals(True)
        self.custom_spin.setValue(0)
        self.custom_spin.blockSignals(False)
        self._custom_pct = 0.0

    def _emit(self):
        type_pct = 0.0
        if self._selected_type and self._selected_type["kind"] == "percent":
            type_pct = self._selected_type["value"]
        self.discount_changed.emit(type_pct, self._coupon, self._custom_pct)


# ═══════════════════════════════════════════════════════════
#  DISCOUNT MANAGEMENT TAB
# ═══════════════════════════════════════════════════════════
class DiscountManagementTab(QWidget):
    types_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16,16,16,16); layout.setSpacing(10)

        title = QLabel("⚙️  Discount Management")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#334;")
        layout.addWidget(title)

        inner = QTabWidget()
        inner.setStyleSheet("""
            QTabWidget::pane { border:1px solid #dde; border-radius:8px; }
            QTabBar::tab { padding:8px 18px; font-size:12px; font-weight:600; color:#556; }
            QTabBar::tab:selected { color:#1a56b0; border-bottom:2px solid #4a90d9; }
        """)
        inner.addTab(self._build_types_tab(), "📂  Discount Types")
        inner.addTab(self._build_coupons_tab(), "🎟️  Coupon Codes")
        layout.addWidget(inner)

    def _build_types_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(10,10,10,10); lay.setSpacing(8)
        tb = QHBoxLayout()
        add_btn = QPushButton("+ Add Type"); add_btn.setObjectName("btn_sm_green")
        add_btn.clicked.connect(self._add_type)
        tb.addStretch(); tb.addWidget(add_btn)
        lay.addLayout(tb)
        self.types_table = QTableWidget(0, 6)
        self.types_table.setHorizontalHeaderLabels(["ID","Name","Kind","Value","Applies To","Active"])
        self.types_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.types_table.setColumnWidth(0, 36)
        self.types_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.types_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.types_table.verticalHeader().setVisible(False)
        self.types_table.setAlternatingRowColors(True)
        lay.addWidget(self.types_table)
        act = QHBoxLayout()
        edit_btn = QPushButton("✏️  Edit"); edit_btn.setObjectName("btn_sm_blue")
        edit_btn.clicked.connect(self._edit_type)
        del_btn = QPushButton("🗑  Delete"); del_btn.setObjectName("btn_sm_red")
        del_btn.clicked.connect(self._delete_type)
        act.addWidget(edit_btn); act.addWidget(del_btn); act.addStretch()
        lay.addLayout(act)
        self._load_types()
        return w

    def _load_types(self):
        self._types = db_get_discount_types(active_only=False)
        self.types_table.setRowCount(0)
        for dt in self._types:
            r = self.types_table.rowCount(); self.types_table.insertRow(r)
            badge = "%" if dt["kind"] == "percent" else "£"
            for c, v in enumerate([str(dt["id"]), dt["name"], dt["kind"],
                                    f"{badge}{dt['value']:.2f}", dt["applies_to"],
                                    "✅" if dt["active"] else "❌"]):
                cell = QTableWidgetItem(v); cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.types_table.setItem(r, c, cell)

    def _sel_type(self):
        row = self.types_table.currentRow()
        return self._types[row] if row >= 0 else None

    def _add_type(self):
        dlg = DiscountTypeDialog(self)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_add_discount_type(d["name"], d["kind"], d["value"], d["applies_to"])
                self._load_types(); self.types_changed.emit()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Duplicate", f"'{d['name']}' already exists.")

    def _edit_type(self):
        dt = self._sel_type()
        if not dt:
            QMessageBox.information(self, "No Selection", "Select a row to edit."); return
        dlg = DiscountTypeDialog(self, dt)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_update_discount_type(dt["id"], d["name"], d["kind"],
                                        d["value"], d["applies_to"], d["active"])
                self._load_types(); self.types_changed.emit()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Duplicate", f"'{d['name']}' already exists.")

    def _delete_type(self):
        dt = self._sel_type()
        if not dt:
            QMessageBox.information(self, "No Selection", "Select a row to delete."); return
        if QMessageBox.question(self, "Confirm", f"Delete '{dt['name']}'?",
                                QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            db_delete_discount_type(dt["id"]); self._load_types(); self.types_changed.emit()

    def _build_coupons_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        lay.setContentsMargins(10,10,10,10); lay.setSpacing(8)
        tb = QHBoxLayout()
        add_btn = QPushButton("+ Add Coupon"); add_btn.setObjectName("btn_sm_green")
        add_btn.clicked.connect(self._add_coupon)
        tb.addStretch(); tb.addWidget(add_btn)
        lay.addLayout(tb)
        self.coupons_table = QTableWidget(0, 8)
        self.coupons_table.setHorizontalHeaderLabels(
            ["ID","Code","Kind","Value","Min £","Max Uses","Used","Active"])
        self.coupons_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.coupons_table.setColumnWidth(0, 36)
        self.coupons_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.coupons_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.coupons_table.verticalHeader().setVisible(False)
        self.coupons_table.setAlternatingRowColors(True)
        lay.addWidget(self.coupons_table)
        act = QHBoxLayout()
        edit_btn = QPushButton("✏️  Edit"); edit_btn.setObjectName("btn_sm_blue")
        edit_btn.clicked.connect(self._edit_coupon)
        del_btn = QPushButton("🗑  Delete"); del_btn.setObjectName("btn_sm_red")
        del_btn.clicked.connect(self._delete_coupon)
        act.addWidget(edit_btn); act.addWidget(del_btn); act.addStretch()
        lay.addLayout(act)
        self._load_coupons()
        return w

    def _load_coupons(self):
        self._coupons = db_get_coupons()
        self.coupons_table.setRowCount(0)
        for cp in self._coupons:
            r = self.coupons_table.rowCount(); self.coupons_table.insertRow(r)
            badge = "%" if cp["kind"] == "percent" else "£"
            mu = str(cp["max_uses"]) if cp["max_uses"] > 0 else "∞"
            for c, v in enumerate([str(cp["id"]), cp["code"], cp["kind"],
                                    f"{badge}{cp['value']:.2f}", f"£{cp['min_order']:.2f}",
                                    mu, str(cp["used_count"]),
                                    "✅" if cp["active"] else "❌"]):
                cell = QTableWidgetItem(v); cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.coupons_table.setItem(r, c, cell)

    def _sel_coupon(self):
        row = self.coupons_table.currentRow()
        return self._coupons[row] if row >= 0 else None

    def _add_coupon(self):
        dlg = CouponDialog(self)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_add_coupon(d["code"], d["kind"], d["value"],
                              d["min_order"], d["max_uses"], d["expires_at"])
                self._load_coupons()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Duplicate", f"Code '{d['code']}' already exists.")

    def _edit_coupon(self):
        cp = self._sel_coupon()
        if not cp:
            QMessageBox.information(self, "No Selection", "Select a row to edit."); return
        dlg = CouponDialog(self, cp)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_update_coupon(cp["id"], d["code"], d["kind"], d["value"],
                                 d["min_order"], d["max_uses"], d["expires_at"], d["active"])
                self._load_coupons()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Duplicate", f"Code '{d['code']}' already exists.")

    def _delete_coupon(self):
        cp = self._sel_coupon()
        if not cp:
            QMessageBox.information(self, "No Selection", "Select a row to delete."); return
        if QMessageBox.question(self, "Confirm", f"Delete coupon '{cp['code']}'?",
                                QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            db_delete_coupon(cp["id"]); self._load_coupons()


# ═══════════════════════════════════════════════════════════
#  CUSTOMERS TAB
# ═══════════════════════════════════════════════════════════
class CustomersTab(QWidget):
    customers_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(16,16,16,16); layout.setSpacing(10)
        toolbar = QHBoxLayout()
        title = QLabel("👥  Customers")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold)); title.setStyleSheet("color:#334;")
        toolbar.addWidget(title); toolbar.addStretch()
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Search…")
        self.search_edit.setFixedWidth(220); self.search_edit.textChanged.connect(self._load_customers)
        toolbar.addWidget(self.search_edit)
        add_btn = QPushButton("+ Add Customer"); add_btn.setObjectName("btn_sm_green")
        add_btn.clicked.connect(self._add_customer); toolbar.addWidget(add_btn)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID","Name","Phone","Email","Notes"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False); self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        act = QHBoxLayout()
        edit_btn = QPushButton("✏️  Edit"); edit_btn.setObjectName("btn_sm_blue")
        edit_btn.clicked.connect(self._edit_customer)
        del_btn = QPushButton("🗑  Delete"); del_btn.setObjectName("btn_sm_red")
        del_btn.clicked.connect(self._delete_customer)
        act.addWidget(edit_btn); act.addWidget(del_btn); act.addStretch()
        layout.addLayout(act)
        self._load_customers()

    def _load_customers(self):
        q = self.search_edit.text().lower()
        customers = db_get_customers()
        if q:
            customers = [c for c in customers
                         if q in c["name"].lower() or q in (c["phone"] or "").lower()
                         or q in (c["email"] or "").lower()]
        self.table.setRowCount(0); self._customers = customers
        for c in customers:
            r = self.table.rowCount(); self.table.insertRow(r)
            for col, val in enumerate([str(c["id"]),c["name"],c["phone"] or "",
                                        c["email"] or "",c["notes"] or ""]):
                item = QTableWidgetItem(val); item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, col, item)

    def _sel(self):
        row = self.table.currentRow(); return self._customers[row] if row >= 0 else None

    def _add_customer(self):
        dlg = CustomerDialog(self)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_add_customer(d["name"],d["phone"],d["email"],d["notes"])
                self._load_customers(); self.customers_changed.emit()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self,"Duplicate",f"Customer '{d['name']}' already exists.")

    def _edit_customer(self):
        c = self._sel()
        if not c: QMessageBox.information(self,"No Selection","Select a customer."); return
        dlg = CustomerDialog(self, c)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_update_customer(c["id"],d["name"],d["phone"],d["email"],d["notes"])
                self._load_customers(); self.customers_changed.emit()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self,"Duplicate",f"Customer '{d['name']}' already exists.")

    def _delete_customer(self):
        c = self._sel()
        if not c: QMessageBox.information(self,"No Selection","Select a customer."); return
        if QMessageBox.question(self,"Confirm Delete",
                                f"Delete '{c['name']}'?\nAll their orders will be deleted too.",
                                QMessageBox.StandardButton.Yes|
                                QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            db_delete_customer(c["id"]); self._load_customers(); self.customers_changed.emit()


# ═══════════════════════════════════════════════════════════
#  ORDERS HISTORY TAB
# ═══════════════════════════════════════════════════════════
class OrdersTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self); layout.setContentsMargins(16,16,16,16); layout.setSpacing(10)
        toolbar = QHBoxLayout()
        title = QLabel("📋  Orders History")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold)); title.setStyleSheet("color:#334;")
        toolbar.addWidget(title); toolbar.addStretch()
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Statuses"] + ORDER_STATUSES)
        self.status_filter.currentTextChanged.connect(self.refresh)
        toolbar.addWidget(self.status_filter)
        refresh_btn = QPushButton("🔄 Refresh"); refresh_btn.setObjectName("btn_sm_blue")
        refresh_btn.clicked.connect(self.refresh); toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["ID","Customer","Collection","Items","Subtotal","Saved","Total","Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False); self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._view_order)
        layout.addWidget(self.table)
        act = QHBoxLayout()
        view_btn = QPushButton("👁  View Details"); view_btn.setObjectName("btn_sm_blue")
        view_btn.clicked.connect(self._view_order)
        self.status_combo = QComboBox(); self.status_combo.addItems(ORDER_STATUSES)
        self.status_combo.setFixedWidth(120)
        upd_btn = QPushButton("✔ Update Status"); upd_btn.setObjectName("btn_sm_green")
        upd_btn.clicked.connect(self._update_status)
        del_btn = QPushButton("🗑  Delete Order"); del_btn.setObjectName("btn_sm_red")
        del_btn.clicked.connect(self._delete_order)
        act.addWidget(view_btn); act.addWidget(QLabel("  Change status:"))
        act.addWidget(self.status_combo); act.addWidget(upd_btn)
        act.addWidget(del_btn); act.addStretch()
        layout.addLayout(act)
        self._orders = []; self.refresh()

    def refresh(self):
        sf = self.status_filter.currentText()
        status = None if sf == "All Statuses" else sf
        self._orders = db_get_orders(status=status)
        self.table.setRowCount(0)
        for o in self._orders:
            items = db_get_order_items(o["id"])
            total_qty = sum(i["quantity"] for i in items)
            r = self.table.rowCount(); self.table.insertRow(r)
            saved = o["discount_amount"]
            vals = [str(o["id"]),o["customer_name"],o["collection_date"],
                    str(total_qty),f"£{o['subtotal']:.2f}",
                    f"£{saved:.2f}",f"£{o['total_amount']:.2f}",o["status"]]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v); cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 7:
                    cm = {"Pending":"#fff3cd","Ready":"#d4edda","Collected":"#cce5ff","Cancelled":"#f8d7da"}
                    cell.setBackground(QColor(cm.get(v, "white")))
                if c == 5 and saved > 0:
                    cell.setForeground(QColor("#27ae60"))
                self.table.setItem(r, c, cell)

    def _sel(self):
        row = self.table.currentRow(); return self._orders[row] if row >= 0 else None

    def _view_order(self):
        o = self._sel()
        if not o: QMessageBox.information(self,"No Selection","Please select an order."); return
        OrderDetailDialog(self, o).exec()

    def _update_status(self):
        o = self._sel()
        if not o: QMessageBox.information(self,"No Selection","Please select an order."); return
        db_update_order_status(o["id"], self.status_combo.currentText()); self.refresh()

    def _delete_order(self):
        o = self._sel()
        if not o: QMessageBox.information(self,"No Selection","Please select an order."); return
        if QMessageBox.question(self,"Confirm Delete",f"Delete order #{o['id']}?",
                                QMessageBox.StandardButton.Yes|
                                QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes:
            db_delete_order(o["id"]); self.refresh()


# ═══════════════════════════════════════════════════════════
#  NEW ORDER WIDGET
# ═══════════════════════════════════════════════════════════
class NewOrderWidget(QWidget):
    order_saved = pyqtSignal()

    def __init__(self, current_user: dict = None):
        super().__init__()
        self._current_user = current_user or {}
        self.order_items = []           # [name, qty, unit_price, item_disc_pct]
        self.collection_date = QDate.currentDate().addDays(1)
        self.selected_customer = ""
        self.selected_customer_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(10)
        layout.addWidget(self._build_tab_bar())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_items_page())          # 0
        self.stack.addWidget(self._build_date_page())           # 1
        self.discount_page = DiscountPage(self._get_subtotal)
        self.discount_page.discount_changed.connect(self._on_discount_changed)
        self.stack.addWidget(self.discount_page)                # 2
        self.stack.addWidget(self._build_customer_page())       # 3
        layout.addWidget(self.stack, 1)
        layout.addWidget(self._build_bottom_bar())
        self._switch_tab(0)

    def _get_subtotal(self):
        return sum(q * p * (1 - d / 100) for _, q, p, d in self.order_items)

    def _on_discount_changed(self, *_):
        self._refresh_order_table()

    # ── Tab bar ───────────────────────────────────────────
    def _build_tab_bar(self):
        bar = QWidget(); row = QHBoxLayout(bar)
        row.setContentsMargins(0,0,0,0); row.setSpacing(6)
        self.tab_btns = []
        for i, label in enumerate(["Items Selection","Collection Date",
                                    "Discount Pricing","Customer Selection"]):
            btn = QPushButton(label); btn.setObjectName("tab_btn")
            btn.setCheckable(True); btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            row.addWidget(btn); self.tab_btns.append(btn)
        return bar

    def _switch_tab(self, idx):
        for i, b in enumerate(self.tab_btns): b.setChecked(i == idx)
        self.stack.setCurrentIndex(idx)
        if idx == 2: self.discount_page.refresh_breakdown(self.order_items)
        if idx == 3: self._reload_customers()

    # ── Bottom bar ────────────────────────────────────────
    def _build_bottom_bar(self):
        bar = QWidget(); row = QHBoxLayout(bar)
        row.setContentsMargins(0,0,0,0); row.setSpacing(8)
        for name, obj, slot in [("◀  Back","btn_back",self._go_back),
                                  ("🗑  Delete Selected Item","btn_delete",self._delete_item),
                                  ("Next  ▶","btn_next",self._go_next)]:
            btn = QPushButton(name); btn.setObjectName(obj)
            btn.setMinimumHeight(52); btn.clicked.connect(slot); row.addWidget(btn, 1)
        return bar

    def _go_back(self):
        idx = self.stack.currentIndex()
        if idx > 0: self._switch_tab(idx - 1)

    def _go_next(self):
        idx = self.stack.currentIndex()
        if idx < 3: self._switch_tab(idx + 1)
        else: self._confirm_order()

    def _delete_item(self):
        row = self.order_table.currentRow()
        if row < 0:
            QMessageBox.information(self,"No Selection","Select a row to delete."); return
        del self.order_items[row]; self._refresh_order_table()

    # ══════════════════════════════════════════
    #  PAGE 0 – ITEMS SELECTION
    # ══════════════════════════════════════════
    def _build_items_page(self):
        page = QWidget()
        main = QHBoxLayout(page); main.setContentsMargins(0,0,0,0); main.setSpacing(10)
        main.addWidget(self._build_category_sidebar(), 0)
        self.items_panel = self._build_items_panel(); main.addWidget(self.items_panel, 2)
        right = QVBoxLayout(); right.setSpacing(10)
        right.addWidget(self._build_numpad(), 0)
        right.addWidget(self._build_order_summary(), 1)
        right_w = QWidget(); right_w.setLayout(right); main.addWidget(right_w, 3)
        return page

    def _build_category_sidebar(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFixedWidth(102)
        inner = QWidget()
        grid = QGridLayout(inner); grid.setContentsMargins(4,4,4,4); grid.setSpacing(6)
        self.cat_buttons = []
        for i, (name, emoji) in enumerate(CATEGORIES):
            btn = QPushButton(f"{emoji}\n{name}"); btn.setObjectName("cat_btn")
            btn.setCheckable(True); btn.setFixedSize(88, 72)
            btn.clicked.connect(lambda _, n=name: self._select_category(n))
            grid.addWidget(btn, i, 0); self.cat_buttons.append((name, btn))
        scroll.setWidget(inner); return scroll

    def _select_category(self, name):
        for n, b in self.cat_buttons: b.setChecked(n == name)
        self._populate_items(name); self.current_cat_label.setText(name)

    def _build_items_panel(self):
        frame = QFrame(); frame.setObjectName("card")
        layout = QVBoxLayout(frame); layout.setContentsMargins(10,8,10,8)
        self.current_cat_label = QLabel("Dress")
        self.current_cat_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.current_cat_label.setStyleSheet("color:#334;"); layout.addWidget(self.current_cat_label)
        self.items_scroll = QScrollArea(); self.items_scroll.setWidgetResizable(True)
        self.items_inner = QWidget()
        self.items_layout = QVBoxLayout(self.items_inner)
        self.items_layout.setContentsMargins(0,0,0,0); self.items_layout.setSpacing(5)
        self.items_layout.addStretch()
        self.items_scroll.setWidget(self.items_inner); layout.addWidget(self.items_scroll)
        self._populate_items("Dress"); return frame

    def _populate_items(self, category):
        while self.items_layout.count() > 1:
            item = self.items_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for name, price in ITEMS.get(category, []):
            row = QHBoxLayout()
            btn = QPushButton(f"  {name}"); btn.setObjectName("item_btn"); btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _, n=name, p=price: self._add_item(n, p))
            price_lbl = QLabel(f"£{price:.2f}")
            price_lbl.setStyleSheet("color:#4a90d9;font-weight:700;font-size:12px;")
            price_lbl.setFixedWidth(52)
            row.addWidget(btn, 1); row.addWidget(price_lbl)
            self.items_layout.insertLayout(self.items_layout.count() - 1, row)

    def _add_item(self, name, price):
        for row in self.order_items:
            if row[0] == name: row[1] += 1; self._refresh_order_table(); return
        self.order_items.append([name, 1, price, 0])
        self._refresh_order_table()

    # ── Numpad ────────────────────────────────────────────
    def _build_numpad(self):
        frame = QFrame(); frame.setObjectName("card"); frame.setFixedWidth(240)
        layout = QVBoxLayout(frame); layout.setContentsMargins(10,8,10,8); layout.setSpacing(6)
        lbl = QLabel("Qty")
        lbl.setStyleSheet("color:#667;font-size:11px;font-weight:700;letter-spacing:1px;")
        layout.addWidget(lbl)
        self.qty_display = QLineEdit("1")
        self.qty_display.setAlignment(Qt.AlignmentFlag.AlignCenter); self.qty_display.setReadOnly(True)
        self.qty_display.setStyleSheet("font-size:20px;font-weight:700;color:#1a56b0;"
                                       "background:#f0f5ff;border:2px solid #4a90d9;border-radius:8px;padding:6px;")
        layout.addWidget(self.qty_display)
        grid = QGridLayout(); grid.setSpacing(5)
        keys = ["1","2","3","4","5","6","7","8","9","⌫","0","✓"]
        for i, k in enumerate(keys):
            btn = QPushButton(k); btn.setObjectName("num_btn"); btn.setFixedHeight(42)
            btn.clicked.connect(lambda _, key=k: self._numpad_press(key))
            grid.addWidget(btn, i // 3, i % 3)
        layout.addLayout(grid); return frame

    def _numpad_press(self, key):
        current = self.qty_display.text()
        if key == "⌫":   self.qty_display.setText(current[:-1] or "0")
        elif key == "✓": self._apply_qty()
        else:
            new = (current if current != "0" else "") + key
            self.qty_display.setText(new[:3])

    def _apply_qty(self):
        row = self.order_table.currentRow()
        if row < 0: return
        try:
            qty = max(1, int(self.qty_display.text()))
            self.order_items[row][1] = qty; self._refresh_order_table()
        except ValueError:
            pass

    # ── Order summary ─────────────────────────────────────
    def _build_order_summary(self):
        frame = QFrame(); frame.setObjectName("card")
        layout = QVBoxLayout(frame); layout.setContentsMargins(10,8,10,10); layout.setSpacing(8)
        self.order_table = QTableWidget(0, 4)
        self.order_table.setHorizontalHeaderLabels(["Item","Qty","Price","Total"])
        self.order_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col, w in zip([1,2,3],[50,60,70]):
            self.order_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.order_table.setColumnWidth(col, w)
        self.order_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.order_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.order_table.verticalHeader().setVisible(False)
        self.order_table.setAlternatingRowColors(True)
        layout.addWidget(self.order_table, 1)
        totals = QHBoxLayout()
        self.total_items_lbl = QLabel("Total Items: 0")
        self.total_items_lbl.setStyleSheet("color:#27ae60;font-weight:700;font-size:14px;")
        self.total_price_lbl = QLabel("Total: £0.00")
        self.total_price_lbl.setStyleSheet("color:#e74c3c;font-weight:700;font-size:16px;")
        self.savings_inline = QLabel("")
        self.savings_inline.setStyleSheet("color:#27ae60;font-size:11px;")
        totals.addWidget(self.total_items_lbl); totals.addStretch()
        v = QVBoxLayout(); v.addWidget(self.total_price_lbl); v.addWidget(self.savings_inline)
        totals.addLayout(v); layout.addLayout(totals)
        return frame

    def _refresh_order_table(self):
        self.order_table.setRowCount(0)
        total_qty = 0
        for name, qty, price, item_disc in self.order_items:
            r = self.order_table.rowCount(); self.order_table.insertRow(r)
            effective = price * (1 - item_disc / 100)
            line_total = qty * effective; total_qty += qty
            for col, val in enumerate([name, str(qty), f"£{price:.2f}", f"£{line_total:.2f}"]):
                cell = QTableWidgetItem(val); cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.order_table.setItem(r, col, cell)

        type_pct, _, coupon, custom_pct = self.discount_page.get_discount_state()
        t = compute_totals(self.order_items, type_pct, coupon, custom_pct)
        self.total_items_lbl.setText(f"Total Items: {total_qty}")
        self.total_price_lbl.setText(f"Total: £{t['grand_total']:.2f}")
        self.savings_inline.setText(
            f"Saving £{t['total_discount']:.2f}" if t["total_discount"] > 0 else "")

        if self.stack.currentIndex() == 2:
            self.discount_page.refresh_breakdown(self.order_items)

    # ══════════════════════════════════════════
    #  PAGE 1 – COLLECTION DATE
    # ══════════════════════════════════════════
    def _build_date_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(40,20,40,20); layout.setSpacing(16)
        title = QLabel("📅  Select Collection Date")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold)); title.setStyleSheet("color:#334;")
        layout.addWidget(title)
        frame = QFrame(); frame.setObjectName("card"); frame.setMaximumWidth(460)
        fl = QVBoxLayout(frame); fl.setContentsMargins(16,16,16,16)
        self.calendar = QCalendarWidget()
        self.calendar.setMinimumDate(QDate.currentDate())
        self.calendar.setSelectedDate(self.collection_date)
        self.calendar.selectionChanged.connect(self._date_changed)
        fl.addWidget(self.calendar)
        self.date_display = QLabel(f"Selected: {self.collection_date.toString('dd MMMM yyyy')}")
        self.date_display.setStyleSheet("color:#4a90d9;font-weight:700;font-size:14px;")
        self.date_display.setAlignment(Qt.AlignmentFlag.AlignCenter); fl.addWidget(self.date_display)
        layout.addWidget(frame); return page

    def _date_changed(self):
        self.collection_date = self.calendar.selectedDate()
        self.date_display.setText(f"Selected: {self.collection_date.toString('dd MMMM yyyy')}")

    # ══════════════════════════════════════════
    #  PAGE 3 – CUSTOMER SELECTION
    # ══════════════════════════════════════════
    def _build_customer_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        layout.setContentsMargins(40, 20, 40, 20); layout.setSpacing(16)

        title = QLabel("👤  Customer Selection")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold)); title.setStyleSheet("color:#334;")
        layout.addWidget(title)

        # ── Logged-in user info card ────────────────────────────────────
        u = self._current_user
        if u:
            user_card = QFrame(); user_card.setObjectName("card")
            user_card.setMaximumWidth(460)
            user_card.setStyleSheet(
                "QFrame#card { background:#eef6ff; border:1.5px solid #a8d4f5; border-radius:12px; }")
            ucl = QVBoxLayout(user_card); ucl.setContentsMargins(16, 12, 16, 12); ucl.setSpacing(4)

            badge_row = QHBoxLayout()
            badge_lbl = QLabel("🔐  Logged in as")
            badge_lbl.setStyleSheet("color:#667; font-size:11px; font-weight:600;")
            role_color = "#1a56b0" if u.get("role") == "admin" else "#27ae60"
            role_lbl = QLabel(u.get("role","").upper())
            role_lbl.setStyleSheet(
                f"color:white; background:{role_color}; border-radius:4px; "
                f"padding:2px 8px; font-size:11px; font-weight:700;")
            badge_row.addWidget(badge_lbl); badge_row.addStretch(); badge_row.addWidget(role_lbl)
            ucl.addLayout(badge_row)

            name_lbl = QLabel(u.get("full_name") or u.get("username",""))
            name_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
            name_lbl.setStyleSheet("color:#1a56b0;")
            ucl.addWidget(name_lbl)

            details = []
            if u.get("email"): details.append(f"✉️  {u['email']}")
            if u.get("phone"): details.append(f"📞  {u['phone']}")
            if details:
                det_lbl = QLabel("   ".join(details))
                det_lbl.setStyleSheet("color:#556; font-size:12px;")
                ucl.addWidget(det_lbl)

            self.use_self_btn = QPushButton("⬇  Use my info as customer")
            self.use_self_btn.setObjectName("btn_sm_blue")
            self.use_self_btn.clicked.connect(self._prefill_from_login)
            ucl.addWidget(self.use_self_btn)

            layout.addWidget(user_card)

        # ── Customer select card ────────────────────────────────────────
        frame = QFrame(); frame.setObjectName("card"); frame.setMaximumWidth(460)
        fl = QVBoxLayout(frame); fl.setContentsMargins(20, 20, 20, 20); fl.setSpacing(12)

        fl.addWidget(QLabel("Search Customer:"))
        self.customer_search = QLineEdit(); self.customer_search.setPlaceholderText("Type to search...")
        self.customer_search.textChanged.connect(self._filter_customers); fl.addWidget(self.customer_search)

        fl.addWidget(QLabel("Select Customer:"))
        self.customer_combo = QComboBox()
        self.customer_combo.currentIndexChanged.connect(self._customer_changed); fl.addWidget(self.customer_combo)

        self.customer_info = QLabel("")
        self.customer_info.setStyleSheet("color:#27ae60;font-weight:700;font-size:13px;")
        fl.addWidget(self.customer_info)

        fl.addWidget(QLabel("─" * 40))
        self.summary_lbl = QLabel(""); self.summary_lbl.setStyleSheet("color:#334;font-size:13px;")
        self.summary_lbl.setWordWrap(True); fl.addWidget(self.summary_lbl)
        layout.addWidget(frame)

        self._all_customers = []; self._reload_customers()
        return page

    def _prefill_from_login(self):
        """Auto-select the customer whose name matches the logged-in user's full_name or username."""
        u = self._current_user
        match_name = (u.get("full_name") or u.get("username", "")).strip()
        if not match_name:
            return

        # Try to find a matching customer
        matched = next(
            (c for c in self._all_customers
             if c["name"].lower() == match_name.lower()),
            None,
        )

        if matched:
            # Select in combo
            for i in range(self.customer_combo.count()):
                if self.customer_combo.itemData(i) == matched["id"]:
                    self.customer_combo.setCurrentIndex(i)
                    break
        else:
            # Ask to create one
            reply = QMessageBox.question(
                self, "No matching customer",
                f"No customer named '{match_name}' found.\n"
                f"Would you like to create one automatically?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    db_add_customer(
                        match_name,
                        u.get("phone", ""),
                        u.get("email", ""),
                        f"Auto-created from login: {u.get('username','')}",
                    )
                    self._reload_customers()
                    # Now select
                    for i in range(self.customer_combo.count()):
                        if self.customer_combo.itemText(i) == match_name:
                            self.customer_combo.setCurrentIndex(i)
                            break
                except sqlite3.IntegrityError:
                    QMessageBox.warning(self, "Error", "Could not create customer.")

    def _reload_customers(self):
        self._all_customers = db_get_customers()
        self._populate_customer_combo(self._all_customers)

    def _populate_customer_combo(self, customers):
        self.customer_combo.blockSignals(True); self.customer_combo.clear()
        self.customer_combo.addItem("— Select Customer —", userData=None)
        for c in customers: self.customer_combo.addItem(c["name"], userData=c["id"])
        self.customer_combo.blockSignals(False)

    def _filter_customers(self, text):
        filtered = ([c for c in self._all_customers if text.lower() in c["name"].lower()]
                    if text else self._all_customers)
        self._populate_customer_combo(filtered)

    def _customer_changed(self, idx):
        cid = self.customer_combo.itemData(idx)
        if cid is not None:
            self.selected_customer = self.customer_combo.currentText()
            self.selected_customer_id = cid
            self.customer_info.setText(f"✅  Customer: {self.selected_customer}")
            self._update_summary_preview()
        else:
            self.selected_customer = ""; self.selected_customer_id = None; self.customer_info.setText("")

    def _update_summary_preview(self):
        if not self.order_items:
            self.summary_lbl.setText("No items in order yet."); return
        type_pct, _, coupon, custom_pct = self.discount_page.get_discount_state()
        t = compute_totals(self.order_items, type_pct, coupon, custom_pct)
        lines = [f"• {name} × {qty}  =  £{qty*price:.2f}" for name, qty, price, _ in self.order_items]
        lines.append(f"\n📅 Collection: {self.collection_date.toString('dd MMM yyyy')}")
        if t["type_disc_pct"] > 0:
            lines.append(f"🏷️ Discount: {t['type_disc_pct']:.1f}%  (-£{t['type_disc_amt']:.2f})")
        if t["coupon_disc_amt"] > 0:
            lines.append(f"🎟️ Coupon: -£{t['coupon_disc_amt']:.2f}")
        if t["total_discount"] > 0:
            lines.append(f"💚 You save: £{t['total_discount']:.2f}")
        lines.append(f"\n💷 Total: £{t['grand_total']:.2f}")
        self.summary_lbl.setText("\n".join(lines))

    # ── Confirm & Save ────────────────────────────────────
    def _confirm_order(self):
        if not self.order_items:
            QMessageBox.warning(self,"Empty Order","Please add items before confirming."); return
        if not self.selected_customer_id:
            QMessageBox.warning(self,"No Customer","Please select a customer first.")
            self._switch_tab(3); return

        type_pct, type_id, coupon, custom_pct = self.discount_page.get_discount_state()
        t = compute_totals(self.order_items, type_pct, coupon, custom_pct)
        eff_pct = max(type_pct, custom_pct)

        msg = (f"Customer: {self.selected_customer}\n"
               f"Collection: {self.collection_date.toString('dd MMM yyyy')}\n"
               f"Items: {sum(q for _,q,_,_ in self.order_items)}\n"
               f"Subtotal: £{t['subtotal']:.2f}\n"
               + (f"Discount ({eff_pct:.1f}%): -£{t['type_disc_amt']:.2f}\n" if eff_pct > 0 else "")
               + (f"Coupon: -£{t['coupon_disc_amt']:.2f}\n" if t["coupon_disc_amt"] > 0 else "")
               + (f"You save: £{t['total_discount']:.2f}\n" if t["total_discount"] > 0 else "")
               + f"Total: £{t['grand_total']:.2f}\n\nConfirm this order?")

        if QMessageBox.question(self,"Confirm Order",msg,
                                QMessageBox.StandardButton.Yes|
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            order_id = db_save_order(
                customer_id=self.selected_customer_id,
                collection_date_str=self.collection_date.toString("yyyy-MM-dd"),
                discount_type_id=type_id, discount_pct=eff_pct,
                coupon_id=coupon["id"] if coupon else None,
                coupon_value=t["coupon_disc_amt"],
                subtotal=t["subtotal"], discount_amount=t["total_discount"],
                total_amount=t["grand_total"], items=self.order_items,
            )
            QMessageBox.information(self,"Order Saved",
                                    f"✅ Order #{order_id} saved!\n💚 Customer saved £{t['total_discount']:.2f}")
            self.order_items.clear(); self._refresh_order_table()
            self.discount_page.reset(); self._switch_tab(0); self.order_saved.emit()


# ═══════════════════════════════════════════════════════════
#  SHARED STYLES FOR LOGIN / REGISTER WINDOW
# ═══════════════════════════════════════════════════════════
AUTH_EXTRA_STYLE = """
    QWidget#auth_bg { background: #f0f2f5; }
    QLineEdit {
        padding: 10px 14px; font-size: 13px;
        border: 1.5px solid #ccd; border-radius: 10px;
        background: white; color: #334;
    }
    QLineEdit:focus { border-color: #4a90d9; }
    QLabel#field_lbl {
        color: #556; font-size: 12px; font-weight: 600;
        background: transparent;
    }
    QLabel#section_title {
        color: #1a56b0; background: transparent;
    }
    QPushButton#auth_tab_btn {
        background: transparent; border: none; border-bottom: 3px solid transparent;
        font-size: 14px; font-weight: 700; color: #889; padding: 10px 0px;
    }
    QPushButton#auth_tab_btn:checked {
        color: #1a56b0; border-bottom: 3px solid #4a90d9;
    }
    QPushButton#auth_tab_btn:hover:!checked { color: #556; }
    QPushButton#btn_primary {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #2c3e7a, stop:1 #4a90d9);
        color: white; border: none; border-radius: 10px;
        font-size: 14px; font-weight: 700; padding: 12px;
    }
    QPushButton#btn_primary:hover {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
            stop:0 #3d52a0, stop:1 #5ba8f5);
    }
    QPushButton#btn_primary:pressed { background: #1a2755; }
    QPushButton#btn_primary:disabled { background: #b0bec5; }
    QPushButton#btn_eye {
        background: #f0f2f5; border: 1.5px solid #ccd;
        border-radius: 10px; font-size: 15px;
    }
    QPushButton#btn_eye:checked { background: #e8f0fe; border-color: #4a90d9; }
    QComboBox {
        padding: 8px 12px; font-size: 13px;
        border: 1.5px solid #ccd; border-radius: 10px;
        background: white; color: #334;
    }
    QComboBox:focus { border-color: #4a90d9; }
    QComboBox::drop-down { border: none; width: 24px; }
"""


def _make_field_label(text):
    lbl = QLabel(text); lbl.setObjectName("field_lbl")
    return lbl


def _make_eye_btn():
    btn = QPushButton("👁"); btn.setObjectName("btn_eye")
    btn.setFixedSize(44, 44); btn.setCheckable(True)
    return btn


def _make_password_row(line_edit, eye_btn):
    row = QHBoxLayout(); row.setSpacing(6)
    row.addWidget(line_edit, 1); row.addWidget(eye_btn)
    return row


# ═══════════════════════════════════════════════════════════
#  LOGIN WINDOW  (with Register tab)
# ═══════════════════════════════════════════════════════════
class LoginWindow(QWidget):
    login_successful = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Laundry Management System")
        self.setFixedSize(480, 680)
        self.setStyleSheet(STYLE + AUTH_EXTRA_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Banner ─────────────────────────────────────────────────────
        banner = QFrame()
        banner.setFixedHeight(150)
        banner.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #1a2755, stop:1 #4a90d9);")
        bl = QVBoxLayout(banner); bl.setAlignment(Qt.AlignmentFlag.AlignCenter); bl.setSpacing(4)
        icon = QLabel("🧺"); icon.setFont(QFont("Segoe UI", 36))
        icon.setStyleSheet("color:white; background:transparent;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = QLabel("Laundry Management System")
        sub.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        sub.setStyleSheet("color:white; background:transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.addWidget(icon); bl.addWidget(sub)
        root.addWidget(banner)

        # ── Tab switcher ───────────────────────────────────────────────
        tab_bar = QWidget(); tab_bar.setStyleSheet("background:white;")
        tbr = QHBoxLayout(tab_bar); tbr.setContentsMargins(32, 0, 32, 0); tbr.setSpacing(0)

        self.login_tab_btn = QPushButton("Sign In"); self.login_tab_btn.setObjectName("auth_tab_btn")
        self.login_tab_btn.setCheckable(True); self.login_tab_btn.setChecked(True)
        self.reg_tab_btn   = QPushButton("Register"); self.reg_tab_btn.setObjectName("auth_tab_btn")
        self.reg_tab_btn.setCheckable(True)

        self.login_tab_btn.clicked.connect(lambda: self._switch_auth_tab(0))
        self.reg_tab_btn.clicked.connect(lambda: self._switch_auth_tab(1))

        tbr.addWidget(self.login_tab_btn, 1); tbr.addWidget(self.reg_tab_btn, 1)
        root.addWidget(tab_bar)

        # ── Stacked pages ──────────────────────────────────────────────
        self.auth_stack = QStackedWidget()
        self.auth_stack.setStyleSheet("background: #f0f2f5;")
        self.auth_stack.addWidget(self._build_login_page())    # 0
        self.auth_stack.addWidget(self._build_register_page()) # 1
        root.addWidget(self.auth_stack, 1)

    # ── Tab switching ──────────────────────────────────────────────────
    def _switch_auth_tab(self, idx):
        self.login_tab_btn.setChecked(idx == 0)
        self.reg_tab_btn.setChecked(idx == 1)
        self.auth_stack.setCurrentIndex(idx)
        # Clear messages when switching
        if idx == 0:
            self.login_error_lbl.setText("")
        else:
            self.reg_msg_lbl.setText("")

    # ══════════════════════════════════════════
    #  LOGIN PAGE
    # ══════════════════════════════════════════
    def _build_login_page(self):
        page = QWidget(); page.setObjectName("auth_bg")
        pv = QVBoxLayout(page)
        pv.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        pv.setContentsMargins(32, 24, 32, 24)
        pv.setSpacing(0)

        card = QFrame()
        card.setStyleSheet("background:white; border-radius:16px; border:1px solid #e0e4ed;")
        card.setMaximumWidth(400)
        cl = QVBoxLayout(card); cl.setContentsMargins(36, 28, 36, 28); cl.setSpacing(14)

        heading = QLabel("Welcome back 👋")
        heading.setObjectName("section_title")
        heading.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        cl.addWidget(heading)

        sub = QLabel("Sign in to your account to continue.")
        sub.setStyleSheet("color:#889; font-size:12px; background:transparent;")
        cl.addWidget(sub)

        # Username
        cl.addWidget(_make_field_label("Username"))
        self.login_user_edit = QLineEdit()
        self.login_user_edit.setPlaceholderText("Enter username")
        self.login_user_edit.setMinimumHeight(44)
        cl.addWidget(self.login_user_edit)

        # Password
        cl.addWidget(_make_field_label("Password"))
        self.login_pass_edit = QLineEdit()
        self.login_pass_edit.setPlaceholderText("Enter password")
        self.login_pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_pass_edit.setMinimumHeight(44)
        self.login_pass_edit.returnPressed.connect(self._do_login)
        login_eye = _make_eye_btn()
        login_eye.toggled.connect(lambda c: self.login_pass_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        cl.addLayout(_make_password_row(self.login_pass_edit, login_eye))

        # Error
        self.login_error_lbl = QLabel("")
        self.login_error_lbl.setStyleSheet(
            "color:#e74c3c; font-size:12px; font-weight:600; background:transparent;")
        self.login_error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_error_lbl.setWordWrap(True)
        cl.addWidget(self.login_error_lbl)

        # Sign in button
        self.login_btn = QPushButton("🔐  Sign In")
        self.login_btn.setObjectName("btn_primary")
        self.login_btn.setMinimumHeight(48)
        self.login_btn.clicked.connect(self._do_login)
        cl.addWidget(self.login_btn)

        # Hint + Register link
        hint_row = QHBoxLayout()
        hint = QLabel("Default: admin / admin123")
        hint.setStyleSheet("color:#aab; font-size:11px; background:transparent;")
        reg_link = QPushButton("Create an account →")
        reg_link.setStyleSheet(
            "QPushButton { background:transparent; border:none; color:#4a90d9; "
            "font-size:11px; font-weight:600; text-decoration:underline; padding:0; }"
            "QPushButton:hover { color:#1a56b0; }")
        reg_link.setCursor(Qt.CursorShape.PointingHandCursor)
        reg_link.clicked.connect(lambda: self._switch_auth_tab(1))
        hint_row.addWidget(hint); hint_row.addStretch(); hint_row.addWidget(reg_link)
        cl.addLayout(hint_row)

        # ── Add card directly to page layout ──────────────────────────
        pv.addWidget(card)
        return page

    # ══════════════════════════════════════════
    #  REGISTER PAGE
    # ══════════════════════════════════════════
    def _build_register_page(self):
        # Scrollable so it fits on small screens
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border:none; background:#f0f2f5; }")

        inner = QWidget(); inner.setObjectName("auth_bg")
        iv = QVBoxLayout(inner)
        iv.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        iv.setContentsMargins(32, 24, 32, 24)

        card = QFrame()
        card.setStyleSheet("background:white; border-radius:16px; border:1px solid #e0e4ed;")
        card.setMaximumWidth(400)
        cl = QVBoxLayout(card); cl.setContentsMargins(36, 28, 36, 28); cl.setSpacing(12)

        heading = QLabel("Create Account 🎉")
        heading.setObjectName("section_title")
        heading.setFont(QFont("Segoe UI", 17, QFont.Weight.Bold))
        cl.addWidget(heading)

        sub = QLabel("Fill in your details to get started.")
        sub.setStyleSheet("color:#889; font-size:12px; background:transparent;")
        cl.addWidget(sub)

        # Full Name
        cl.addWidget(_make_field_label("Full Name *"))
        self.reg_fullname = QLineEdit(); self.reg_fullname.setPlaceholderText("e.g. John Smith")
        self.reg_fullname.setMinimumHeight(42); cl.addWidget(self.reg_fullname)

        # Username
        cl.addWidget(_make_field_label("Username *"))
        self.reg_username = QLineEdit(); self.reg_username.setPlaceholderText("Choose a username")
        self.reg_username.setMinimumHeight(42); cl.addWidget(self.reg_username)

        # Email
        cl.addWidget(_make_field_label("Email"))
        self.reg_email = QLineEdit(); self.reg_email.setPlaceholderText("your@email.com")
        self.reg_email.setMinimumHeight(42); cl.addWidget(self.reg_email)

        # Phone
        cl.addWidget(_make_field_label("Phone"))
        self.reg_phone = QLineEdit(); self.reg_phone.setPlaceholderText("+44 7700 000000")
        self.reg_phone.setMinimumHeight(42); cl.addWidget(self.reg_phone)

        # Role
        cl.addWidget(_make_field_label("Role"))
        self.reg_role = QComboBox(); self.reg_role.addItems(["staff", "admin"])
        self.reg_role.setMinimumHeight(42); cl.addWidget(self.reg_role)

        # Password
        cl.addWidget(_make_field_label("Password *"))
        self.reg_pass = QLineEdit(); self.reg_pass.setPlaceholderText("Min 6 characters")
        self.reg_pass.setEchoMode(QLineEdit.EchoMode.Password); self.reg_pass.setMinimumHeight(42)
        reg_eye1 = _make_eye_btn()
        reg_eye1.toggled.connect(lambda c: self.reg_pass.setEchoMode(
            QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        cl.addLayout(_make_password_row(self.reg_pass, reg_eye1))

        # Confirm Password
        cl.addWidget(_make_field_label("Confirm Password *"))
        self.reg_confirm = QLineEdit(); self.reg_confirm.setPlaceholderText("Re-enter password")
        self.reg_confirm.setEchoMode(QLineEdit.EchoMode.Password); self.reg_confirm.setMinimumHeight(42)
        self.reg_confirm.returnPressed.connect(self._do_register)
        reg_eye2 = _make_eye_btn()
        reg_eye2.toggled.connect(lambda c: self.reg_confirm.setEchoMode(
            QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        cl.addLayout(_make_password_row(self.reg_confirm, reg_eye2))

        # Password strength bar
        self.strength_bar = QFrame()
        self.strength_bar.setFixedHeight(4)
        self.strength_bar.setStyleSheet("background:#eee; border-radius:2px;")
        self.strength_lbl = QLabel("")
        self.strength_lbl.setStyleSheet("font-size:11px; background:transparent;")
        self.reg_pass.textChanged.connect(self._update_strength)
        cl.addWidget(self.strength_bar)
        cl.addWidget(self.strength_lbl)

        # Message label (success / error)
        self.reg_msg_lbl = QLabel("")
        self.reg_msg_lbl.setStyleSheet("font-size:12px; font-weight:600; background:transparent;")
        self.reg_msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reg_msg_lbl.setWordWrap(True)
        cl.addWidget(self.reg_msg_lbl)

        # Register button
        self.reg_btn = QPushButton("✅  Create Account")
        self.reg_btn.setObjectName("btn_primary")
        self.reg_btn.setMinimumHeight(48)
        self.reg_btn.clicked.connect(self._do_register)
        cl.addWidget(self.reg_btn)

        # Back to login link
        back_row = QHBoxLayout()
        back_row.addStretch()
        back_lnk = QPushButton("← Already have an account? Sign in")
        back_lnk.setStyleSheet(
            "QPushButton { background:transparent; border:none; color:#4a90d9; "
            "font-size:11px; font-weight:600; text-decoration:underline; padding:0; }"
            "QPushButton:hover { color:#1a56b0; }")
        back_lnk.setCursor(Qt.CursorShape.PointingHandCursor)
        back_lnk.clicked.connect(lambda: self._switch_auth_tab(0))
        back_row.addWidget(back_lnk); back_row.addStretch()
        cl.addLayout(back_row)

        iv.addWidget(card)
        scroll.setWidget(inner)
        return scroll

    # ── Password strength ──────────────────────────────────────────────
    def _update_strength(self, text):
        score = 0
        if len(text) >= 6:  score += 1
        if len(text) >= 10: score += 1
        if any(c.isdigit() for c in text):          score += 1
        if any(c in "!@#$%^&*()_+-=[]{}|;':\",./<>?" for c in text): score += 1
        colours = ["#e74c3c", "#e67e22", "#f1c40f", "#2ecc71"]
        labels  = ["Weak", "Fair", "Good", "Strong"]
        widths  = [25, 50, 75, 100]
        if text:
            idx = min(score, 3)
            c = colours[idx]; w = widths[idx]; lbl = labels[idx]
            self.strength_bar.setStyleSheet(
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {c}, stop:{w/100:.2f} {c}, stop:{w/100+0.001:.3f} #eee, stop:1 #eee);"
                f"border-radius:2px;")
            self.strength_lbl.setStyleSheet(f"font-size:11px; color:{c}; background:transparent;")
            self.strength_lbl.setText(f"Password strength: {lbl}")
        else:
            self.strength_bar.setStyleSheet("background:#eee; border-radius:2px;")
            self.strength_lbl.setText("")

    # ── Actions ────────────────────────────────────────────────────────
    def _do_login(self):
        username = self.login_user_edit.text().strip()
        password = self.login_pass_edit.text()
        if not username or not password:
            self.login_error_lbl.setText("Please enter both username and password.")
            return
        self.login_btn.setEnabled(False); self.login_btn.setText("Signing in…")
        user = db_authenticate(username, password)
        self.login_btn.setEnabled(True); self.login_btn.setText("🔐  Sign In")
        if user:
            self.login_error_lbl.setText("")
            self.login_successful.emit(user)
        else:
            self.login_error_lbl.setText("❌  Invalid username or password.")
            self.login_pass_edit.clear(); self.login_pass_edit.setFocus()

    def _do_register(self):
        full_name = self.reg_fullname.text().strip()
        username  = self.reg_username.text().strip()
        email     = self.reg_email.text().strip()
        phone     = self.reg_phone.text().strip()
        role      = self.reg_role.currentText()
        password  = self.reg_pass.text()
        confirm   = self.reg_confirm.text()

        # Validation
        if not full_name:
            self._reg_error("Full name is required."); return
        if not username:
            self._reg_error("Username is required."); return
        if len(username) < 3:
            self._reg_error("Username must be at least 3 characters."); return
        if not password:
            self._reg_error("Password is required."); return
        if len(password) < 6:
            self._reg_error("Password must be at least 6 characters."); return
        if password != confirm:
            self._reg_error("Passwords do not match."); return

        self.reg_btn.setEnabled(False); self.reg_btn.setText("Creating account…")
        try:
            db_add_user(username, password, full_name, email, phone, role)
            self.reg_btn.setEnabled(True); self.reg_btn.setText("✅  Create Account")
            # Success – show message and switch to login with username pre-filled
            self.reg_msg_lbl.setStyleSheet(
                "font-size:12px; font-weight:600; color:#27ae60; background:transparent;")
            self.reg_msg_lbl.setText(
                f"🎉  Account '{username}' created successfully!\n"
                f"You can now sign in.")
            # Pre-fill login tab and switch
            self.login_user_edit.setText(username)
            self.login_pass_edit.clear()
            self._switch_auth_tab(0)
            self.login_pass_edit.setFocus()
            # Clear register form
            for w in [self.reg_fullname, self.reg_username, self.reg_email,
                      self.reg_phone, self.reg_pass, self.reg_confirm]:
                w.clear()
        except sqlite3.IntegrityError:
            self.reg_btn.setEnabled(True); self.reg_btn.setText("✅  Create Account")
            self._reg_error(f"Username '{username}' is already taken. Choose another.")

    def _reg_error(self, msg):
        self.reg_msg_lbl.setStyleSheet(
            "font-size:12px; font-weight:600; color:#e74c3c; background:transparent;")
        self.reg_msg_lbl.setText(f"❌  {msg}")


# ═══════════════════════════════════════════════════════════
#  USER MANAGEMENT TAB  (admin only)
# ═══════════════════════════════════════════════════════════
class UserManagementTab(QWidget):
    def __init__(self, current_user: dict):
        super().__init__()
        self._current_user = current_user
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16); layout.setSpacing(10)

        title = QLabel("👤  User Management")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet("color:#334;"); layout.addWidget(title)

        tb = QHBoxLayout()
        add_btn = QPushButton("+ Add User"); add_btn.setObjectName("btn_sm_green")
        add_btn.clicked.connect(self._add_user)
        tb.addStretch(); tb.addWidget(add_btn)
        layout.addLayout(tb)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Username", "Full Name", "Email", "Phone", "Role", "Active"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 36)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        act = QHBoxLayout()
        edit_btn = QPushButton("✏️  Edit"); edit_btn.setObjectName("btn_sm_blue")
        edit_btn.clicked.connect(self._edit_user)
        pwd_btn = QPushButton("🔑  Change Password"); pwd_btn.setObjectName("btn_sm_blue")
        pwd_btn.clicked.connect(self._change_password)
        del_btn = QPushButton("🗑  Delete"); del_btn.setObjectName("btn_sm_red")
        del_btn.clicked.connect(self._delete_user)
        act.addWidget(edit_btn); act.addWidget(pwd_btn)
        act.addWidget(del_btn); act.addStretch()
        layout.addLayout(act)

        self._load_users()

    def _load_users(self):
        self._users = db_get_users()
        self.table.setRowCount(0)
        for u in self._users:
            r = self.table.rowCount(); self.table.insertRow(r)
            for c, v in enumerate([str(u["id"]), u["username"], u["full_name"] or "",
                                    u["email"] or "", u["phone"] or "", u["role"],
                                    "✅" if u["active"] else "❌"]):
                cell = QTableWidgetItem(v)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 5:  # Role badge colour
                    if v == "admin":
                        cell.setForeground(QColor("#1a56b0"))
                self.table.setItem(r, c, cell)

    def _sel(self):
        row = self.table.currentRow()
        return self._users[row] if row >= 0 else None

    def _add_user(self):
        dlg = UserDialog(self)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_add_user(d["username"], d["password"], d["full_name"],
                            d["email"], d["phone"], d["role"])
                self._load_users()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Duplicate", f"Username '{d['username']}' already exists.")

    def _edit_user(self):
        u = self._sel()
        if not u:
            QMessageBox.information(self, "No Selection", "Select a user to edit."); return
        dlg = UserDialog(self, u)
        if dlg.exec():
            d = dlg.get_data()
            try:
                db_update_user(u["id"], d["username"], d["full_name"],
                               d["email"], d["phone"], d["role"], d["active"])
                self._load_users()
            except sqlite3.IntegrityError:
                QMessageBox.warning(self, "Duplicate", f"Username '{d['username']}' already exists.")

    def _change_password(self):
        u = self._sel()
        if not u:
            QMessageBox.information(self, "No Selection", "Select a user."); return
        dlg = ChangePasswordDialog(self, u)
        if dlg.exec():
            db_change_password(u["id"], dlg.get_password())
            QMessageBox.information(self, "Done", f"Password updated for '{u['username']}'.")

    def _delete_user(self):
        u = self._sel()
        if not u:
            QMessageBox.information(self, "No Selection", "Select a user to delete."); return
        if u["id"] == self._current_user["id"]:
            QMessageBox.warning(self, "Not Allowed", "You cannot delete your own account."); return
        if QMessageBox.question(self, "Confirm", f"Delete user '{u['username']}'?",
                                QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            db_delete_user(u["id"]); self._load_users()


# ── User dialog ─────────────────────────────────────────────
class UserDialog(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.setWindowTitle("Add User" if user is None else "Edit User")
        self.setMinimumWidth(380)
        self._is_edit = user is not None
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.username_edit  = QLineEdit(user["username"]  if user else "")
        self.fullname_edit  = QLineEdit(user["full_name"] if user else "")
        self.email_edit     = QLineEdit(user["email"]     if user else "")
        self.phone_edit     = QLineEdit(user["phone"]     if user else "")
        self.role_combo     = QComboBox()
        self.role_combo.addItems(["staff", "admin"])
        if user: self.role_combo.setCurrentText(user["role"])
        self.active_chk = QCheckBox("Active")
        self.active_chk.setChecked(bool(user["active"]) if user else True)

        form.addRow("Username *:", self.username_edit)
        form.addRow("Full Name:",  self.fullname_edit)
        form.addRow("Email:",      self.email_edit)
        form.addRow("Phone:",      self.phone_edit)
        form.addRow("Role:",       self.role_combo)
        form.addRow("",            self.active_chk)

        if not self._is_edit:
            self.password_edit = QLineEdit()
            self.password_edit.setPlaceholderText("Set initial password")
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.confirm_edit  = QLineEdit()
            self.confirm_edit.setPlaceholderText("Confirm password")
            self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Password *:", self.password_edit)
            form.addRow("Confirm *:",  self.confirm_edit)

        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept(self):
        if not self.username_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Username is required."); return
        if not self._is_edit:
            if not self.password_edit.text():
                QMessageBox.warning(self, "Validation", "Password is required."); return
            if self.password_edit.text() != self.confirm_edit.text():
                QMessageBox.warning(self, "Validation", "Passwords do not match."); return
        self.accept()

    def get_data(self):
        d = dict(username=self.username_edit.text().strip(),
                 full_name=self.fullname_edit.text().strip(),
                 email=self.email_edit.text().strip(),
                 phone=self.phone_edit.text().strip(),
                 role=self.role_combo.currentText(),
                 active=int(self.active_chk.isChecked()))
        if not self._is_edit:
            d["password"] = self.password_edit.text()
        return d


class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None, user=None):
        super().__init__(parent)
        self.setWindowTitle(f"Change Password – {user['username']}")
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.new_edit = QLineEdit()
        self.new_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_edit.setPlaceholderText("New password")
        self.confirm_edit = QLineEdit()
        self.confirm_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm_edit.setPlaceholderText("Confirm password")
        form.addRow("New password:", self.new_edit)
        form.addRow("Confirm:",      self.confirm_edit)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _accept(self):
        if not self.new_edit.text():
            QMessageBox.warning(self, "Validation", "Password cannot be empty."); return
        if self.new_edit.text() != self.confirm_edit.text():
            QMessageBox.warning(self, "Validation", "Passwords do not match."); return
        self.accept()

    def get_password(self): return self.new_edit.text()


# ═══════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════
class LMSWindow(QMainWindow):
    def __init__(self, current_user: dict):
        super().__init__()
        self._current_user = current_user
        self.setWindowTitle(
            f"Laundry Management System  —  {current_user['full_name'] or current_user['username']}  [{current_user['role'].upper()}]")
        self.setMinimumSize(1200, 800)
        self.setStyleSheet(STYLE)

        central = QWidget(); central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central); root.setContentsMargins(14, 10, 14, 10); root.setSpacing(10)

        # ── Top header bar ─────────────────────────────────────────────
        hdr_row = QHBoxLayout()
        hdr = QLabel("🧺  Laundry Management System")
        hdr.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        hdr.setStyleSheet("color:#1a56b0; padding:4px 0;")
        hdr_row.addWidget(hdr); hdr_row.addStretch()

        # User info badge
        role_color = "#1a56b0" if current_user["role"] == "admin" else "#27ae60"
        user_badge = QLabel(
            f"👤  {current_user['full_name'] or current_user['username']}  "
            f"<span style='color:{role_color};font-size:11px;'>[{current_user['role'].upper()}]</span>")
        user_badge.setTextFormat(Qt.TextFormat.RichText)
        user_badge.setStyleSheet("color:#334; font-size:13px; font-weight:600;")
        hdr_row.addWidget(user_badge)

        logout_btn = QPushButton("🚪 Logout")
        logout_btn.setObjectName("btn_sm_red")
        logout_btn.clicked.connect(self._logout)
        hdr_row.addWidget(logout_btn)
        root.addLayout(hdr_row)

        # ── Tabs ───────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border:1px solid #dde; border-radius:10px; background:white; }
            QTabBar::tab { padding:10px 22px; font-size:13px; font-weight:600; color:#556; }
            QTabBar::tab:selected { color:#1a56b0; border-bottom:3px solid #4a90d9; }
        """)

        self.new_order_widget = NewOrderWidget(current_user)
        tabs.addTab(self.new_order_widget, "🛒  New Order")
        self.orders_tab = OrdersTab()
        tabs.addTab(self.orders_tab, "📋  Orders")
        self.customers_tab = CustomersTab()
        tabs.addTab(self.customers_tab, "👥  Customers")
        self.disc_mgmt_tab = DiscountManagementTab()
        tabs.addTab(self.disc_mgmt_tab, "🏷️  Discounts")

        # User management – admin only
        if current_user["role"] == "admin":
            self.user_mgmt_tab = UserManagementTab(current_user)
            tabs.addTab(self.user_mgmt_tab, "🔐  Users")

        self.new_order_widget.order_saved.connect(self.orders_tab.refresh)
        self.disc_mgmt_tab.types_changed.connect(self.new_order_widget.discount_page.reload_types)

        root.addWidget(tabs, 1)

    def _logout(self):
        if QMessageBox.question(self, "Logout", "Log out and return to the login screen?",
                                QMessageBox.StandardButton.Yes |
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.close()
            _show_login()


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT HELPERS
# ═══════════════════════════════════════════════════════════
_login_win = None
_main_win  = None


def _show_login():
    global _login_win, _main_win
    _login_win = LoginWindow()
    _login_win.login_successful.connect(_on_login)
    _login_win.show()


def _on_login(user: dict):
    global _login_win, _main_win
    _login_win.close()
    _main_win = LMSWindow(user)
    _main_win.show()


# ═══════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    _show_login()
    sys.exit(app.exec())
