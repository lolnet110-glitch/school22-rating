from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import date
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задан. Добавь DATABASE_URL в Render → Environment.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app = FastAPI(title="School 22 Rating API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS school_groups (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        min_grade INTEGER NOT NULL,
        max_grade INTEGER NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        grade INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        students_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        max_points INTEGER NOT NULL DEFAULT 100,
        sort_order INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS subcategories (
        id SERIAL PRIMARY KEY,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        max_points INTEGER NOT NULL DEFAULT 10,
        sort_order INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_subcategory_scores (
        id SERIAL PRIMARY KEY,
        class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        subcategory_id INTEGER NOT NULL REFERENCES subcategories(id) ON DELETE CASCADE,
        points REAL NOT NULL DEFAULT 0,
        comment TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(class_id, subcategory_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_subcategory_events (
        id SERIAL PRIMARY KEY,
        class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        subcategory_id INTEGER NOT NULL REFERENCES subcategories(id) ON DELETE CASCADE,
        event_date DATE NOT NULL,
        title TEXT NOT NULL,
        points REAL NOT NULL DEFAULT 0,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_category_scores (
        id SERIAL PRIMARY KEY,
        class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
        points REAL NOT NULL DEFAULT 0,
        comment TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(class_id, category_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS uniform_checks (
        id SERIAL PRIMARY KEY,
        class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        check_date DATE NOT NULL,
        without_uniform INTEGER NOT NULL DEFAULT 0,
        comment TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    connection.commit()

    cursor.execute("SELECT COUNT(*) AS count FROM school_groups")
    if cursor.fetchone()["count"] == 0:
        cursor.executemany(
            "INSERT INTO school_groups (name, min_grade, max_grade) VALUES (%s, %s, %s)",
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
                    """
                    INSERT INTO classes (name, grade, group_id, students_count)
                    VALUES (%s, %s, %s, %s)
                    """,
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

        category_ids = {}

        for name, max_points, sort_order in categories:
            cursor.execute(
                """
                INSERT INTO categories (name, max_points, sort_order)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (name, max_points, sort_order),
            )
            category_ids[name] = cursor.fetchone()["id"]

        default_subcategories = [
            ("Учёба и наука", "Олимпиады", 40, 1),
            ("Учёба и наука", "Проекты", 35, 2),
            ("Учёба и наука", "Успеваемость", 25, 3),
            ("Спорт и здоровье", "Соревнования", 40, 1),
            ("Спорт и здоровье", "Секции", 30, 2),
            ("Спорт и здоровье", "Активность", 30, 3),
            ("Творчество и медиа", "Конкурсы", 40, 1),
            ("Творчество и медиа", "Выступления", 35, 2),
            ("Творчество и медиа", "Медиа", 25, 3),
            ("Активность и волонтёрство", "Помощь школе", 35, 1),
            ("Активность и волонтёрство", "Акции", 35, 2),
            ("Активность и волонтёрство", "Инициативы", 30, 3),
        ]

        for category_name, name, max_points, sort_order in default_subcategories:
            cursor.execute(
                """
                INSERT INTO subcategories (category_id, name, max_points, sort_order)
                VALUES (%s, %s, %s, %s)
                """,
                (category_ids[category_name], name, max_points, sort_order),
            )

    connection.commit()
    cursor.close()
    connection.close()


@app.on_event("startup")
def startup():
    init_db()


class ClassCreate(BaseModel):
    name: str
    grade: int
    group_id: int
    students_count: int = 0


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


class SubcategoryCreate(BaseModel):
    category_id: int
    name: str
    max_points: int = 10
    sort_order: int = 0


class SubcategoryUpdate(BaseModel):
    category_id: Optional[int] = None
    name: Optional[str] = None
    max_points: Optional[int] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None


class ClassCategoryScoreUpdate(BaseModel):
    points: float
    comment: Optional[str] = None


class ClassSubcategoryScoreUpdate(BaseModel):
    points: float
    comment: Optional[str] = None


class SubcategoryEventCreate(BaseModel):
    subcategory_id: int
    event_date: str
    title: str
    points: float
    comment: Optional[str] = None


class SubcategoryEventUpdate(BaseModel):
    subcategory_id: Optional[int] = None
    event_date: Optional[str] = None
    title: Optional[str] = None
    points: Optional[float] = None
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
    return {
        "message": "API рейтинга Школы №22 работает на Supabase PostgreSQL",
        "docs": "/docs"
    }


@app.get("/api/groups")
def get_groups():
    connection = db()
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM school_groups ORDER BY id")
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return rows


@app.get("/api/classes")
def get_classes():
    connection = db()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT classes.*, school_groups.name AS group_name
        FROM classes
        JOIN school_groups ON school_groups.id = classes.group_id
        WHERE classes.status = 'active'
        ORDER BY classes.grade, classes.name
    """)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()
    return rows


@app.post("/api/classes")
def create_class(item: ClassCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO classes (name, grade, group_id, students_count)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (item.name, item.grade, item.group_id, item.students_count),
    )
    class_id = cursor.fetchone()["id"]
    connection.commit()
    cursor.close()
    connection.close()
    return {"id": class_id, "message": "Класс добавлен"}


@app.put("/api/classes/{class_id}")
def update_class(class_id: int, item: ClassUpdate):
    fields = []
    values = []

    for key, value in item.dict(exclude_unset=True).items():
        fields.append(f"{key} = %s")
        values.append(value)

    if not fields:
        return {"message": "Нет изменений"}

    values.append(class_id)
    connection = db()
    cursor = connection.cursor()
    cursor.execute(f"UPDATE classes SET {', '.join(fields)} WHERE id = %s", values)
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Класс обновлён"}


@app.delete("/api/classes/{class_id}")
def delete_class(class_id: int):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("UPDATE classes SET status = 'archive' WHERE id = %s", (class_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Класс удалён в архив"}


@app.get("/api/categories")
def get_categories():
    connection = db()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT *
        FROM categories
        WHERE status = 'active'
        ORDER BY sort_order, id
    """)
    categories = cursor.fetchall()

    result = []
    for category in categories:
        cursor.execute("""
            SELECT *
            FROM subcategories
            WHERE category_id = %s AND status = 'active'
            ORDER BY sort_order, id
        """, (category["id"],))
        item = dict(category)
        item["subcategories"] = cursor.fetchall()
        result.append(item)

    cursor.close()
    connection.close()
    return result


@app.post("/api/categories")
def create_category(category: CategoryCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO categories (name, max_points, sort_order)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (category.name, category.max_points, category.sort_order),
    )
    category_id = cursor.fetchone()["id"]
    connection.commit()
    cursor.close()
    connection.close()
    return {"id": category_id, "message": "Категория добавлена"}


@app.put("/api/categories/{category_id}")
def update_category(category_id: int, category: CategoryUpdate):
    fields = []
    values = []

    for key, value in category.dict(exclude_unset=True).items():
        fields.append(f"{key} = %s")
        values.append(value)

    if not fields:
        return {"message": "Нет изменений"}

    values.append(category_id)
    connection = db()
    cursor = connection.cursor()
    cursor.execute(f"UPDATE categories SET {', '.join(fields)} WHERE id = %s", values)
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Категория обновлена"}


@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("UPDATE categories SET status = 'archive' WHERE id = %s", (category_id,))
    cursor.execute("UPDATE subcategories SET status = 'archive' WHERE category_id = %s", (category_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Категория удалена в архив"}


@app.post("/api/subcategories")
def create_subcategory(subcategory: SubcategoryCreate):
    connection = db()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO subcategories (category_id, name, max_points, sort_order)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (
            subcategory.category_id,
            subcategory.name,
            subcategory.max_points,
            subcategory.sort_order,
        ),
    )
    subcategory_id = cursor.fetchone()["id"]
    connection.commit()
    cursor.close()
    connection.close()
    return {"id": subcategory_id, "message": "Подкатегория добавлена"}


@app.put("/api/subcategories/{subcategory_id}")
def update_subcategory(subcategory_id: int, subcategory: SubcategoryUpdate):
    fields = []
    values = []

    for key, value in subcategory.dict(exclude_unset=True).items():
        fields.append(f"{key} = %s")
        values.append(value)

    if not fields:
        return {"message": "Нет изменений"}

    values.append(subcategory_id)
    connection = db()
    cursor = connection.cursor()
    cursor.execute(f"UPDATE subcategories SET {', '.join(fields)} WHERE id = %s", values)
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Подкатегория обновлена"}


@app.delete("/api/subcategories/{subcategory_id}")
def delete_subcategory(subcategory_id: int):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("UPDATE subcategories SET status = 'archive' WHERE id = %s", (subcategory_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Подкатегория удалена в архив"}


@app.put("/api/classes/{class_id}/category-scores/{category_id}")
def set_class_category_score(class_id: int, category_id: int, score: ClassCategoryScoreUpdate):
    connection = db()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM categories WHERE id = %s AND status = 'active'",
        (category_id,)
    )
    category = cursor.fetchone()

    if not category:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=404, detail="Категория не найдена")

    if score.points < 0 or score.points > category["max_points"]:
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=400,
            detail=f"Баллы должны быть от 0 до {category['max_points']}"
        )

    cursor.execute("""
        INSERT INTO class_category_scores (class_id, category_id, points, comment, updated_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT(class_id, category_id)
        DO UPDATE SET
            points = EXCLUDED.points,
            comment = EXCLUDED.comment,
            updated_at = CURRENT_TIMESTAMP
    """, (class_id, category_id, score.points, score.comment))

    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Баллы класса по категории сохранены"}


@app.put("/api/classes/{class_id}/subcategory-scores/{subcategory_id}")
def set_class_subcategory_score(class_id: int, subcategory_id: int, score: ClassSubcategoryScoreUpdate):
    connection = db()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM subcategories WHERE id = %s AND status = 'active'",
        (subcategory_id,)
    )
    subcategory = cursor.fetchone()

    if not subcategory:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=404, detail="Подкатегория не найдена")

    if score.points < 0 or score.points > subcategory["max_points"]:
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=400,
            detail=f"Баллы должны быть от 0 до {subcategory['max_points']}"
        )

    cursor.execute("""
        INSERT INTO class_subcategory_scores (class_id, subcategory_id, points, comment, updated_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT(class_id, subcategory_id)
        DO UPDATE SET
            points = EXCLUDED.points,
            comment = EXCLUDED.comment,
            updated_at = CURRENT_TIMESTAMP
    """, (class_id, subcategory_id, score.points, score.comment))

    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Баллы класса по подкатегории сохранены"}


@app.post("/api/classes/{class_id}/subcategory-events")
def create_subcategory_event(class_id: int, item: SubcategoryEventCreate):
    connection = db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM classes WHERE id = %s AND status = 'active'", (class_id,))
    class_row = cursor.fetchone()

    if not class_row:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=404, detail="Класс не найден")

    cursor.execute("SELECT * FROM subcategories WHERE id = %s AND status = 'active'", (item.subcategory_id,))
    subcategory = cursor.fetchone()

    if not subcategory:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=404, detail="Подкатегория не найдена")

    if item.points < 0:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=400, detail="Баллы не могут быть меньше 0")

    cursor.execute("""
        INSERT INTO class_subcategory_events (class_id, subcategory_id, event_date, title, points, comment)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (class_id, item.subcategory_id, item.event_date, item.title, item.points, item.comment))

    event_id = cursor.fetchone()["id"]
    connection.commit()
    cursor.close()
    connection.close()
    return {"id": event_id, "message": "Событие добавлено"}


@app.get("/api/classes/{class_id}/subcategory-events")
def get_class_subcategory_events(class_id: int):
    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            class_subcategory_events.*,
            subcategories.name AS subcategory_name,
            categories.name AS category_name,
            subcategories.max_points AS subcategory_max_points
        FROM class_subcategory_events
        JOIN subcategories ON subcategories.id = class_subcategory_events.subcategory_id
        JOIN categories ON categories.id = subcategories.category_id
        WHERE class_subcategory_events.class_id = %s
        ORDER BY class_subcategory_events.event_date DESC, class_subcategory_events.id DESC
    """, (class_id,))

    rows = cursor.fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["event_date"] = str(item["event_date"])
        item["created_at"] = str(item["created_at"])
        result.append(item)

    cursor.close()
    connection.close()
    return result


@app.put("/api/subcategory-events/{event_id}")
def update_subcategory_event(event_id: int, item: SubcategoryEventUpdate):
    fields = []
    values = []

    for key, value in item.dict(exclude_unset=True).items():
        fields.append(f"{key} = %s")
        values.append(value)

    if not fields:
        return {"message": "Нет изменений"}

    values.append(event_id)
    connection = db()
    cursor = connection.cursor()
    cursor.execute(
        f"UPDATE class_subcategory_events SET {', '.join(fields)} WHERE id = %s",
        values
    )
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Событие обновлено"}


@app.delete("/api/subcategory-events/{event_id}")
def delete_subcategory_event(event_id: int):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM class_subcategory_events WHERE id = %s", (event_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Событие удалено"}


@app.get("/api/classes/{class_id}/category-scores")
def get_class_category_scores(class_id: int):
    connection = db()
    result = build_class_category_scores(connection, class_id)
    connection.close()
    return result


@app.post("/api/classes/{class_id}/uniform-checks")
def create_uniform_check(class_id: int, item: UniformCheckCreate):
    connection = db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
    class_row = cursor.fetchone()

    if not class_row:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=404, detail="Класс не найден")

    if item.without_uniform < 0:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=400, detail="Количество без формы не может быть меньше 0")

    if item.without_uniform > class_row["students_count"]:
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=400,
            detail="Количество без формы не может быть больше количества учеников в классе"
        )

    cursor.execute("""
        INSERT INTO uniform_checks (class_id, check_date, without_uniform, comment)
        VALUES (%s, %s, %s, %s)
        RETURNING id
    """, (class_id, item.check_date, item.without_uniform, item.comment))

    check_id = cursor.fetchone()["id"]
    connection.commit()
    cursor.close()
    connection.close()
    return {"id": check_id, "message": "Проверка формы добавлена"}


@app.get("/api/classes/{class_id}/uniform-checks")
def get_uniform_checks(class_id: int):
    connection = db()
    result = build_uniform_checks(connection, class_id)
    connection.close()
    return result


@app.put("/api/uniform-checks/{check_id}")
def update_uniform_check(check_id: int, item: UniformCheckUpdate):
    connection = db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM uniform_checks WHERE id = %s", (check_id,))
    check = cursor.fetchone()

    if not check:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=404, detail="Проверка не найдена")

    cursor.execute("SELECT * FROM classes WHERE id = %s", (check["class_id"],))
    class_row = cursor.fetchone()

    fields = []
    values = []

    for key, value in item.dict(exclude_unset=True).items():
        if key == "without_uniform" and value > class_row["students_count"]:
            cursor.close()
            connection.close()
            raise HTTPException(
                status_code=400,
                detail="Количество без формы не может быть больше количества учеников в классе"
            )

        fields.append(f"{key} = %s")
        values.append(value)

    if not fields:
        cursor.close()
        connection.close()
        return {"message": "Нет изменений"}

    values.append(check_id)
    cursor.execute(f"UPDATE uniform_checks SET {', '.join(fields)} WHERE id = %s", values)
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Проверка формы обновлена"}


@app.delete("/api/uniform-checks/{check_id}")
def delete_uniform_check(check_id: int):
    connection = db()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM uniform_checks WHERE id = %s", (check_id,))
    connection.commit()
    cursor.close()
    connection.close()
    return {"message": "Проверка формы удалена"}


@app.get("/api/ratings/groups/{group_id}")
def get_group_rating(group_id: int):
    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM classes
        WHERE group_id = %s AND status = 'active'
        ORDER BY grade, name
    """, (group_id,))

    classes = cursor.fetchall()
    result = [calculate_class_rating(connection, class_row) for class_row in classes]
    cursor.close()
    connection.close()
    return sorted(result, key=lambda x: x["total"], reverse=True)


@app.get("/api/ratings/classes")
def get_all_classes_rating():
    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM classes
        WHERE status = 'active'
        ORDER BY grade, name
    """)

    classes = cursor.fetchall()
    result = [calculate_class_rating(connection, class_row) for class_row in classes]
    cursor.close()
    connection.close()
    return sorted(result, key=lambda x: x["total"], reverse=True)


@app.get("/api/classes/{class_id}/details")
def get_class_details(class_id: int):
    connection = db()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
    class_row = cursor.fetchone()

    if not class_row:
        cursor.close()
        connection.close()
        raise HTTPException(status_code=404, detail="Класс не найден")

    result = {
        "class": calculate_class_rating(connection, class_row),
        "category_scores": build_class_category_scores(connection, class_id),
        "uniform": build_uniform_checks(connection, class_id),
        "events": get_class_events_internal(connection, class_id)
    }

    cursor.close()
    connection.close()
    return result


def get_class_events_internal(connection, class_id: int):
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            class_subcategory_events.*,
            subcategories.name AS subcategory_name,
            categories.name AS category_name,
            subcategories.max_points AS subcategory_max_points
        FROM class_subcategory_events
        JOIN subcategories ON subcategories.id = class_subcategory_events.subcategory_id
        JOIN categories ON categories.id = subcategories.category_id
        WHERE class_subcategory_events.class_id = %s
        ORDER BY class_subcategory_events.event_date DESC, class_subcategory_events.id DESC
    """, (class_id,))

    rows = cursor.fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["event_date"] = str(item["event_date"])
        item["created_at"] = str(item["created_at"])
        result.append(item)

    cursor.close()
    return result


def build_class_category_scores(connection, class_id: int):
    cursor = connection.cursor()

    cursor.execute("""
        SELECT *
        FROM categories
        WHERE status = 'active'
        ORDER BY sort_order, id
    """)

    categories = cursor.fetchall()
    result = []

    for category in categories:
        item = dict(category)

        cursor.execute("""
            SELECT *
            FROM subcategories
            WHERE category_id = %s AND status = 'active'
            ORDER BY sort_order, id
        """, (category["id"],))

        subcategories = cursor.fetchall()
        sub_result = []
        category_sum = 0

        for subcategory in subcategories:
            cursor.execute("""
                SELECT
                    id,
                    event_date,
                    title,
                    points,
                    comment,
                    created_at
                FROM class_subcategory_events
                WHERE class_id = %s AND subcategory_id = %s
                ORDER BY event_date DESC, id DESC
            """, (class_id, subcategory["id"]))

            events = cursor.fetchall()
            formatted_events = []
            events_sum = 0

            for event in events:
                event_item = dict(event)
                event_item["event_date"] = str(event_item["event_date"])
                event_item["created_at"] = str(event_item["created_at"])
                events_sum += event_item["points"]
                formatted_events.append(event_item)

            cursor.execute("""
                SELECT points, comment, updated_at
                FROM class_subcategory_scores
                WHERE class_id = %s AND subcategory_id = %s
            """, (class_id, subcategory["id"]))

            old_score = cursor.fetchone()

            if events:
                raw_points = events_sum
            else:
                raw_points = old_score["points"] if old_score else 0

            final_points = min(raw_points, subcategory["max_points"])

            sub_item = dict(subcategory)
            sub_item["points"] = round(final_points, 2)
            sub_item["raw_points"] = round(raw_points, 2)
            sub_item["maxed"] = raw_points > subcategory["max_points"]
            sub_item["events"] = formatted_events
            sub_item["comment"] = old_score["comment"] if old_score else None
            sub_item["updated_at"] = str(old_score["updated_at"]) if old_score and old_score["updated_at"] else None

            category_sum += final_points
            sub_result.append(sub_item)

        cursor.execute("""
            SELECT points, comment, updated_at
            FROM class_category_scores
            WHERE class_id = %s AND category_id = %s
        """, (class_id, category["id"]))

        category_score = cursor.fetchone()

        if "форма" in category["name"].lower():
            uniform_summary = calculate_uniform_summary(connection, class_id)
            item["points"] = uniform_summary["average_points"]
            item["uniform_summary"] = uniform_summary
        elif sub_result:
            item["points"] = round(min(category_sum, category["max_points"]), 2)
            item["raw_points"] = round(category_sum, 2)
            item["maxed"] = category_sum > category["max_points"]
        else:
            item["points"] = category_score["points"] if category_score else 0
            item["raw_points"] = item["points"]
            item["maxed"] = False

        item["comment"] = category_score["comment"] if category_score else None
        item["updated_at"] = str(category_score["updated_at"]) if category_score and category_score["updated_at"] else None
        item["subcategories"] = sub_result
        result.append(item)

    cursor.close()
    return result


def build_uniform_checks(connection, class_id: int):
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
    class_row = cursor.fetchone()

    if not class_row:
        cursor.close()
        return {
            "class_id": class_id,
            "students_count": 0,
            "average_points": 0,
            "checks_count": 0,
            "is_checked_current_month": False,
            "latest_check_date": None,
            "checks": []
        }

    cursor.execute("""
        SELECT *
        FROM uniform_checks
        WHERE class_id = %s
        ORDER BY check_date DESC, id DESC
    """, (class_id,))

    checks = cursor.fetchall()
    result = [format_uniform_check(class_row, check) for check in checks]
    summary = calculate_uniform_summary(connection, class_id)

    today = date.today()
    latest_check_date = result[0]["check_date"] if result else None
    is_checked_current_month = False

    if latest_check_date:
        year, month, *_ = latest_check_date.split("-")
        is_checked_current_month = int(year) == today.year and int(month) == today.month

    cursor.close()

    return {
        "class_id": class_id,
        "class_name": class_row["name"],
        "students_count": class_row["students_count"],
        "average_points": summary["average_points"],
        "checks_count": summary["checks_count"],
        "is_checked_current_month": is_checked_current_month,
        "latest_check_date": latest_check_date,
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
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM classes WHERE id = %s", (class_id,))
    class_row = cursor.fetchone()

    if not class_row:
        cursor.close()
        return {
            "average_points": 0,
            "checks_count": 0,
            "is_checked_current_month": False,
            "latest_check_date": None,
            "checks": []
        }

    cursor.execute("""
        SELECT *
        FROM uniform_checks
        WHERE class_id = %s
        ORDER BY check_date DESC, id DESC
    """, (class_id,))

    checks = cursor.fetchall()

    if not checks:
        cursor.close()
        return {
            "average_points": 0,
            "checks_count": 0,
            "is_checked_current_month": False,
            "latest_check_date": None,
            "checks": []
        }

    formatted = [format_uniform_check(class_row, check) for check in checks]
    average = sum(item["points"] for item in formatted) / len(formatted)

    today = date.today()
    latest_check_date = formatted[0]["check_date"]
    year, month, *_ = latest_check_date.split("-")
    is_checked_current_month = int(year) == today.year and int(month) == today.month

    cursor.close()

    return {
        "average_points": round(average, 2),
        "checks_count": len(formatted),
        "is_checked_current_month": is_checked_current_month,
        "latest_check_date": latest_check_date,
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
        "check_date": str(check["check_date"]),
        "students_count": students_count,
        "without_uniform": without_uniform,
        "in_uniform": in_uniform,
        "percent_in_uniform": percent_in_uniform,
        "points": points,
        "comment": check["comment"],
        "created_at": str(check["created_at"])
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
