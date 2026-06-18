from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(file).parent / "school22.db"

app = FastAPI(title="School 22 Rating API")

app.add_middleware(
CORSMiddleware,
allow_origins=[
"https://school22-admin.vercel.app",
"https://school22-rating-site.vercel.app",
],
allow_credentials=True,
allow_methods=[""],
allow_headers=[""],
)


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


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
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        class_id INTEGER NOT NULL,
        photo_url TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        admin_comment TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

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
    CREATE TABLE IF NOT EXISTS subcategories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        max_points INTEGER NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS student_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subcategory_id INTEGER NOT NULL,
        points INTEGER NOT NULL DEFAULT 0,
        UNIQUE(student_id, subcategory_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        points INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    connection.commit()

    # Первичное заполнение, если база пустая
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
            if 1 <= grade <= 4:
                group_id = 1
            elif 5 <= grade <= 8:
                group_id = 2
            else:
                group_id = 3

            for letter in ["А", "Б"]:
                cursor.execute(
                    "INSERT INTO classes (name, grade, group_id) VALUES (?, ?, ?)",
                    (f"{grade}{letter}", grade, group_id),
                )

    cursor.execute("SELECT COUNT(*) AS count FROM categories")
    if cursor.fetchone()["count"] == 0:
        categories = [
            ("Учёба и наука", 100, 1),
            ("Спорт и здоровье", 100, 2),
            ("Творчество и медиа", 100, 3),
            ("Активность и волонтёрство", 100, 4),
        ]
        cursor.executemany(
            "INSERT INTO categories (name, max_points, sort_order) VALUES (?, ?, ?)",
            categories,
        )

        subcategories = [
            (1, "Олимпиады", 40, 1),
            (1, "Проекты", 35, 2),
            (1, "Успеваемость", 25, 3),

            (2, "Соревнования", 40, 1),
            (2, "Секции", 30, 2),
            (2, "Активность", 30, 3),

            (3, "Конкурсы", 40, 1),
            (3, "Выступления", 35, 2),
            (3, "Медиа", 25, 3),

            (4, "Помощь школе", 35, 1),
            (4, "Акции", 35, 2),
            (4, "Инициативы", 30, 3),
        ]
        cursor.executemany(
            "INSERT INTO subcategories (category_id, name, max_points, sort_order) VALUES (?, ?, ?, ?)",
            subcategories,
        )

    connection.commit()
    connection.close()


@app.on_event("startup")
def startup():
    init_db()


class StudentCreate(BaseModel):
    full_name: str
    class_id: int
    photo_url: Optional[str] = None
    admin_comment: Optional[str] = None


class StudentUpdate(BaseModel):
    full_name: Optional[str] = None
    class_id: Optional[int] = None
    photo_url: Optional[str] = None
    status: Optional[str] = None
    admin_comment: Optional[str] = None


class CategoryCreate(BaseModel):
    name: str
    max_points: int = 100
    sort_order: int = 0


class SubcategoryCreate(BaseModel):
    category_id: int
    name: str
    max_points: int
    sort_order: int = 0


class ScoreUpdate(BaseModel):
    points: int


class ClassScoreCreate(BaseModel):
    title: str
    points: int


@app.get("/")
def home():
    return {
        "message": "API рейтинга Школы №22 работает",
        "docs": "/docs"
    }


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


@app.get("/api/classes/{class_id}/students")
def get_class_students(class_id: int):
    connection = db()
    rows = connection.execute("""
        SELECT students.id, students.full_name, students.photo_url, students.status,
               classes.name AS class_name
        FROM students
        JOIN classes ON classes.id = students.class_id
        WHERE students.class_id = ? AND students.status = 'active'
        ORDER BY students.full_name
    """, (class_id,)).fetchall()
    connection.close()
    return [dict(row) for row in rows]


@app.post("/api/students")
def create_student(student: StudentCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO students (full_name, class_id, photo_url, admin_comment)
        VALUES (?, ?, ?, ?)
    """, (student.full_name, student.class_id, student.photo_url, student.admin_comment))
    connection.commit()
    student_id = cursor.lastrowid
    connection.close()
    return {"id": student_id, "message": "Ученик добавлен"}


@app.put("/api/students/{student_id}")
def update_student(student_id: int, student: StudentUpdate):
    fields = []
    values = []

    for key, value in student.dict(exclude_unset=True).items():
        fields.append(f"{key} = ?")
        values.append(value)

    if not fields:
        return {"message": "Нет изменений"}

    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(student_id)

    connection = db()
    cursor = connection.cursor()
    cursor.execute(f"UPDATE students SET {', '.join(fields)} WHERE id = ?", values)
    connection.commit()
    connection.close()

    return {"message": "Ученик обновлён"}


@app.get("/api/categories")
def get_categories():
    connection = db()
    categories = connection.execute("""
        SELECT * FROM categories
        WHERE status = 'active'
        ORDER BY sort_order, id
    """).fetchall()

    result = []
    for category in categories:
        subcategories = connection.execute("""
            SELECT * FROM subcategories
            WHERE category_id = ? AND status = 'active'
            ORDER BY sort_order, id
        """, (category["id"],)).fetchall()

        item = dict(category)
        item["subcategories"] = [dict(row) for row in subcategories]
        result.append(item)

    connection.close()
    return result


@app.post("/api/categories")
def create_category(category: CategoryCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO categories (name, max_points, sort_order)
        VALUES (?, ?, ?)
    """, (category.name, category.max_points, category.sort_order))
    connection.commit()
    category_id = cursor.lastrowid
    connection.close()
    return {"id": category_id, "message": "Категория добавлена"}


@app.post("/api/subcategories")
def create_subcategory(subcategory: SubcategoryCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO subcategories (category_id, name, max_points, sort_order)
        VALUES (?, ?, ?, ?)
    """, (
        subcategory.category_id,
        subcategory.name,
        subcategory.max_points,
        subcategory.sort_order,
    ))
    connection.commit()
    subcategory_id = cursor.lastrowid
    connection.close()
    return {"id": subcategory_id, "message": "Подкатегория добавлена"}


@app.put("/api/students/{student_id}/scores/{subcategory_id}")
def set_student_score(student_id: int, subcategory_id: int, score: ScoreUpdate):
    connection = db()

    subcategory = connection.execute(
        "SELECT max_points FROM subcategories WHERE id = ?",
        (subcategory_id,)
    ).fetchone()

    if not subcategory:
        connection.close()
        raise HTTPException(status_code=404, detail="Подкатегория не найдена")

    if score.points < 0 or score.points > subcategory["max_points"]:
        connection.close()
        raise HTTPException(
            status_code=400,
            detail=f"Баллы должны быть от 0 до {subcategory['max_points']}"
        )

    connection.execute("""
        INSERT INTO student_scores (student_id, subcategory_id, points)
        VALUES (?, ?, ?)
        ON CONFLICT(student_id, subcategory_id)
        DO UPDATE SET points = excluded.points
    """, (student_id, subcategory_id, score.points))

    connection.commit()
    connection.close()

    return {"message": "Баллы ученика сохранены"}


@app.post("/api/classes/{class_id}/scores")
def add_class_score(class_id: int, score: ClassScoreCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("""
        INSERT INTO class_scores (class_id, title, points)
        VALUES (?, ?, ?)
    """, (class_id, score.title, score.points))
    connection.commit()
    score_id = cursor.lastrowid
    connection.close()
    return {"id": score_id, "message": "Баллы класса добавлены"}


@app.get("/api/ratings/groups/{group_id}")
def get_group_rating(group_id: int):
    connection = db()

    classes = connection.execute("""
        SELECT * FROM classes
        WHERE group_id = ? AND status = 'active'
        ORDER BY grade, name
    """, (group_id,)).fetchall()

    result = []

    for class_row in classes:
        students = connection.execute("""
            SELECT id FROM students
            WHERE class_id = ? AND status = 'active'
        """, (class_row["id"],)).fetchall()

        student_ids = [s["id"] for s in students]

        if student_ids:
            placeholders = ",".join(["?"] * len(student_ids))
            scores = connection.execute(f"""
                SELECT SUM(points) AS total
                FROM student_scores
                WHERE student_id IN ({placeholders})
            """, student_ids).fetchone()["total"] or 0

            average_students_score = round(scores / len(student_ids), 2)
        else:
            average_students_score = 0

        class_bonus = connection.execute("""
            SELECT SUM(points) AS total
            FROM class_scores
            WHERE class_id = ?
        """, (class_row["id"],)).fetchone()["total"] or 0

        result.append({
            "class_id": class_row["id"],
            "class_name": class_row["name"],
            "students_count": len(student_ids),
            "average_students_score": average_students_score,
            "class_bonus": class_bonus,
            "total": average_students_score + class_bonus
        })

    connection.close()
    return sorted(result, key=lambda x: x["total"], reverse=True)
