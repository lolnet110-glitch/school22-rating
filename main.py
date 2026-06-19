from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "school22.db"

app = FastAPI(title="School 22 Rating API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def column_exists(connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def init_db():
    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS school_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        min_grade INTEGER NOT NULL,
        max_grade INTEGER NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        grade INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        students_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)

    if not column_exists(connection, "classes", "students_count"):
        cursor.execute("ALTER TABLE classes ADD COLUMN students_count INTEGER NOT NULL DEFAULT 0")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        max_points INTEGER NOT NULL DEFAULT 100,
        sort_order INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_category_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        points REAL NOT NULL DEFAULT 0,
        comment TEXT,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(class_id, category_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS uniform_checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        check_date TEXT NOT NULL,
        without_uniform INTEGER NOT NULL DEFAULT 0,
        comment TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    connection.commit()

    cursor.execute("SELECT COUNT(*) AS count FROM school_groups")
    if cursor.fetchone()["count"] == 0:
        cursor.executemany(
            "INSERT INTO school_groups (name, min_grade, max_grade) VALUES (?, ?, ?)",
            [
                ("Начальная школа", 1, 4),
                ("Средняя школа", 5, 8),
                ("Старшая школа", 9, 11),
            ],
        )

    cursor.execute("SELECT COUNT(*) AS count FROM classes")
    if cursor.fetchone()["count"] == 0:
        for grade in range(1, 12):
            group_id = 1 if grade <= 4 else 2 if grade <= 8 else 3
            for letter in ["А", "Б"]:
                cursor.execute(
                    "INSERT INTO classes (name, grade, group_id, students_count) VALUES (?, ?, ?, ?)",
                    (f"{grade}{letter}", grade, group_id, 0),
                )

    cursor.execute("SELECT COUNT(*) AS count FROM categories")
    if cursor.fetchone()["count"] == 0:
        categories = [
            ("Учёба и наука", 100, 1),
            ("Спорт и здоровье", 100, 2),
            ("Творчество и медиа", 100, 3),
            ("Активность и волонтёрство", 100, 4),
            ("Школьная форма", 10, 5),
        ]
        cursor.executemany(
            "INSERT INTO categories (name, max_points, sort_order) VALUES (?, ?, ?)",
            categories,
        )
    else:
        uniform = cursor.execute(
            "SELECT id FROM categories WHERE LOWER(name) LIKE LOWER(?)",
            ("%форма%",)
        ).fetchone()

        if not uniform:
            cursor.execute(
                "INSERT INTO categories (name, max_points, sort_order) VALUES (?, ?, ?)",
                ("Школьная форма", 10, 5),
            )

    connection.commit()
    connection.close()


@app.on_event("startup")
def startup():
    init_db()


class ClassUpdate(BaseModel):
    name: Optional[str] = None
    grade: Optional[int] = None
    group_id: Optional[int] = None
    students_count: Optional[int] = None
    status: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str
    max_points: int = 100
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    max_points: Optional[int] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None


class ClassCategoryScoreUpdate(BaseModel):
    points: float
    comment: Optional[str] = None


class UniformCheckCreate(BaseModel):
    check_date: str
    without_uniform: int
    comment: Optional[str] = None


class UniformCheckUpdate(BaseModel):
    check_date: Optional[str] = None
    without_uniform: Optional[int] = None
    comment: Optional[str] = None


@app.get("/")
def home():
    return {"message": "API рейтинга Школы №22 работает", "docs": "/docs"}


@app.get("/api/groups")
def get_groups():
    connection = db()
    rows = connection.execute("SELECT * FROM school_groups").fetchall()
    connection.close()
    return [dict(row) for row in rows]


@app.get("/api/classes")
def get_classes():
    connection = db()
    rows = connection.execute("""
        SELECT classes.*, school_groups.name AS group_name
        FROM classes
        JOIN school_groups ON school_groups.id = classes.group_id
        WHERE classes.status = 'active'
        ORDER BY classes.grade, classes.name
    """).fetchall()
    connection.close()
    return [dict(row) for row in rows]


@app.put("/api/classes/{class_id}")
def update_class(class_id: int, item: ClassUpdate):
    fields = []
    values = []

    for key, value in item.dict(exclude_unset=True).items():
        fields.append(f"{key} = ?")
        values.append(value)

    if not fields:
        return {"message": "Нет изменений"}

    values.append(class_id)
    connection = db()
    connection.execute(f"UPDATE classes SET {', '.join(fields)} WHERE id = ?", values)
    connection.commit()
    connection.close()
    return {"message": "Класс обновлён"}


@app.get("/api/categories")
def get_categories():
    connection = db()
    rows = connection.execute("""
        SELECT * FROM categories
        WHERE status = 'active'
        ORDER BY sort_order, id
    """).fetchall()
    connection.close()
    return [dict(row) for row in rows]


@app.post("/api/categories")
def create_category(category: CategoryCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO categories (name, max_points, sort_order) VALUES (?, ?, ?)",
        (category.name, category.max_points, category.sort_order)
    )
    connection.commit()
    category_id = cursor.lastrowid
    connection.close()
    return {"id": category_id, "message": "Категория добавлена"}


@app.put("/api/categories/{category_id}")
def update_category(category_id: int, category: CategoryUpdate):
    fields = []
    values = []

    for key, value in category.dict(exclude_unset=True).items():
        fields.append(f"{key} = ?")
        values.append(value)

    if not fields:
        return {"message": "Нет изменений"}

    values.append(category_id)
    connection = db()
    connection.execute(f"UPDATE categories SET {', '.join(fields)} WHERE id = ?", values)
    connection.commit()
    connection.close()
    return {"message": "Категория обновлена"}


@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int):
    connection = db()
    connection.execute("UPDATE categories SET status = 'archive' WHERE id = ?", (category_id,))
    connection.commit()
    connection.close()
    return {"message": "Категория удалена в архив"}


@app.put("/api/classes/{class_id}/category-scores/{category_id}")
def set_class_category_score(class_id: int, category_id: int, score: ClassCategoryScoreUpdate):
    connection = db()
    category = connection.execute(
        "SELECT * FROM categories WHERE id = ? AND status = 'active'",
        (category_id,)
    ).fetchone()

    if not category:
        connection.close()
        raise HTTPException(status_code=404, detail="Категория не найдена")

    if score.points < 0 or score.points > category["max_points"]:
        connection.close()
        raise HTTPException(status_code=400, detail=f"Баллы должны быть от 0 до {category['max_points']}")

    connection.execute("""
        INSERT INTO class_category_scores (class_id, category_id, points, comment, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(class_id, category_id)
        DO UPDATE SET points = excluded.points, comment = excluded.comment, updated_at = CURRENT_TIMESTAMP
    """, (class_id, category_id, score.points, score.comment))

    connection.commit()
    connection.close()
    return {"message": "Баллы класса по категории сохранены"}


@app.get("/api/classes/{class_id}/category-scores")
def get_class_category_scores(class_id: int):
    connection = db()
    result = build_class_category_scores(connection, class_id)
    connection.close()
    return result


@app.post("/api/classes/{class_id}/uniform-checks")
def create_uniform_check(class_id: int, item: UniformCheckCreate):
    connection = db()
    class_row = connection.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()

    if not class_row:
        connection.close()
        raise HTTPException(status_code=404, detail="Класс не найден")

    if item.without_uniform < 0:
        connection.close()
        raise HTTPException(status_code=400, detail="Количество без формы не может быть меньше 0")

    if item.without_uniform > class_row["students_count"]:
        connection.close()
        raise HTTPException(status_code=400, detail="Количество без формы не может быть больше количества учеников в классе")

    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO uniform_checks (class_id, check_date, without_uniform, comment)
        VALUES (?, ?, ?, ?)
    """, (class_id, item.check_date, item.without_uniform, item.comment))

    connection.commit()
    check_id = cursor.lastrowid
    connection.close()
    return {"id": check_id, "message": "Проверка формы добавлена"}


@app.get("/api/classes/{class_id}/uniform-checks")
def get_uniform_checks(class_id: int):
    connection = db()
    class_row = connection.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()

    if not class_row:
        connection.close()
        raise HTTPException(status_code=404, detail="Класс не найден")

    checks = connection.execute("""
        SELECT * FROM uniform_checks
        WHERE class_id = ?
        ORDER BY check_date DESC, id DESC
    """, (class_id,)).fetchall()

    result = [format_uniform_check(class_row, check) for check in checks]
    summary = calculate_uniform_summary(connection, class_id)
    connection.close()

    return {
        "class_id": class_id,
        "class_name": class_row["name"],
        "students_count": class_row["students_count"],
        "average_points": summary["average_points"],
        "checks_count": summary["checks_count"],
        "checks": result
    }


@app.put("/api/uniform-checks/{check_id}")
def update_uniform_check(check_id: int, item: UniformCheckUpdate):
    connection = db()
    check = connection.execute("SELECT * FROM uniform_checks WHERE id = ?", (check_id,)).fetchone()

    if not check:
        connection.close()
        raise HTTPException(status_code=404, detail="Проверка не найдена")

    class_row = connection.execute("SELECT * FROM classes WHERE id = ?", (check["class_id"],)).fetchone()

    fields = []
    values = []

    for key, value in item.dict(exclude_unset=True).items():
        if key == "without_uniform" and value > class_row["students_count"]:
            connection.close()
            raise HTTPException(status_code=400, detail="Количество без формы не может быть больше количества учеников в классе")

        fields.append(f"{key} = ?")
        values.append(value)

    if not fields:
        connection.close()
        return {"message": "Нет изменений"}

    values.append(check_id)
    connection.execute(f"UPDATE uniform_checks SET {', '.join(fields)} WHERE id = ?", values)
    connection.commit()
    connection.close()
    return {"message": "Проверка формы обновлена"}


@app.delete("/api/uniform-checks/{check_id}")
def delete_uniform_check(check_id: int):
    connection = db()
    connection.execute("DELETE FROM uniform_checks WHERE id = ?", (check_id,))
    connection.commit()
    connection.close()
    return {"message": "Проверка формы удалена"}


@app.get("/api/ratings/groups/{group_id}")
def get_group_rating(group_id: int):
    connection = db()
    classes = connection.execute("""
        SELECT * FROM classes
        WHERE group_id = ? AND status = 'active'
        ORDER BY grade, name
    """, (group_id,)).fetchall()

    result = [calculate_class_rating(connection, class_row) for class_row in classes]
    connection.close()
    return sorted(result, key=lambda x: x["total"], reverse=True)


@app.get("/api/ratings/classes")
def get_all_classes_rating():
    connection = db()
    classes = connection.execute("""
        SELECT * FROM classes
        WHERE status = 'active'
        ORDER BY grade, name
    """).fetchall()

    result = [calculate_class_rating(connection, class_row) for class_row in classes]
    connection.close()
    return sorted(result, key=lambda x: x["total"], reverse=True)


@app.get("/api/classes/{class_id}/details")
def get_class_details(class_id: int):
    connection = db()
    class_row = connection.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()

    if not class_row:
        connection.close()
        raise HTTPException(status_code=404, detail="Класс не найден")

    result = {
        "class": calculate_class_rating(connection, class_row),
        "category_scores": build_class_category_scores(connection, class_id),
        "uniform": build_uniform_checks(connection, class_id)
    }

    connection.close()
    return result


def build_class_category_scores(connection, class_id: int):
    categories = connection.execute("""
        SELECT * FROM categories
        WHERE status = 'active'
        ORDER BY sort_order, id
    """).fetchall()

    result = []
    for category in categories:
        score = connection.execute("""
            SELECT points, comment, updated_at
            FROM class_category_scores
            WHERE class_id = ? AND category_id = ?
        """, (class_id, category["id"])).fetchone()

        item = dict(category)
        item["points"] = score["points"] if score else 0
        item["comment"] = score["comment"] if score else None
        item["updated_at"] = score["updated_at"] if score else None

        if "форма" in category["name"].lower():
            uniform_summary = calculate_uniform_summary(connection, class_id)
            item["points"] = uniform_summary["average_points"]
            item["uniform_summary"] = uniform_summary

        result.append(item)

    return result


def build_uniform_checks(connection, class_id: int):
    class_row = connection.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()

    if not class_row:
        return {"class_id": class_id, "students_count": 0, "average_points": 0, "checks_count": 0, "checks": []}

    checks = connection.execute("""
        SELECT * FROM uniform_checks
        WHERE class_id = ?
        ORDER BY check_date DESC, id DESC
    """, (class_id,)).fetchall()

    result = [format_uniform_check(class_row, check) for check in checks]
    summary = calculate_uniform_summary(connection, class_id)

    return {
        "class_id": class_id,
        "class_name": class_row["name"],
        "students_count": class_row["students_count"],
        "average_points": summary["average_points"],
        "checks_count": summary["checks_count"],
        "checks": result
    }


def calculate_class_rating(connection, class_row):
    category_scores = build_class_category_scores(connection, class_row["id"])
    total = sum(row["points"] for row in category_scores)

    return {
        "class_id": class_row["id"],
        "class_name": class_row["name"],
        "grade": class_row["grade"],
        "group_id": class_row["group_id"],
        "students_count": class_row["students_count"],
        "total": round(total, 2),
        "categories": category_scores
    }


def calculate_uniform_summary(connection, class_id: int):
    class_row = connection.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()

    if not class_row:
        return {"average_points": 0, "checks_count": 0, "checks": []}

    checks = connection.execute("""
        SELECT * FROM uniform_checks
        WHERE class_id = ?
        ORDER BY check_date DESC, id DESC
    """, (class_id,)).fetchall()

    if not checks:
        return {"average_points": 0, "checks_count": 0, "checks": []}

    formatted = [format_uniform_check(class_row, check) for check in checks]
    average = sum(item["points"] for item in formatted) / len(formatted)

    return {
        "average_points": round(average, 2),
        "checks_count": len(formatted),
        "checks": formatted
    }


def format_uniform_check(class_row, check):
    students_count = class_row["students_count"]
    without_uniform = check["without_uniform"]
    in_uniform = max(students_count - without_uniform, 0)

    if students_count <= 0:
        percent_in_uniform = 0
    else:
        percent_in_uniform = round((in_uniform / students_count) * 100, 2)

    points = uniform_points(percent_in_uniform)

    return {
        "id": check["id"],
        "class_id": check["class_id"],
        "check_date": check["check_date"],
        "students_count": students_count,
        "without_uniform": without_uniform,
        "in_uniform": in_uniform,
        "percent_in_uniform": percent_in_uniform,
        "points": points,
        "comment": check["comment"],
        "created_at": check["created_at"]
    }


def uniform_points(percent: float) -> int:
    if percent >= 100:
        return 10
    if percent >= 80:
        return 8
    if percent >= 60:
        return 5
    if percent >= 40:
        return 2
    if percent >= 20:
        return 0
    return 0
