"""数据库模型：题库、试卷、作答、错题"""
import json
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aiplatform.db")

QUESTION_TYPES = ("single", "multiple", "judge", "blank", "short")
DIFFICULTIES = ("easy", "medium", "hard")
SUBJECTS = ("math", "english")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        knowledge_point TEXT NOT NULL,
        qtype TEXT NOT NULL,
        difficulty TEXT NOT NULL DEFAULT 'medium',
        stem TEXT NOT NULL,
        options TEXT DEFAULT '[]',
        answer TEXT NOT NULL,
        analysis TEXT DEFAULT '',
        source TEXT DEFAULT 'manual',
        create_time TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS papers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject TEXT NOT NULL,
        title TEXT NOT NULL,
        config TEXT DEFAULT '{}',
        create_time TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS paper_questions (
        paper_id INTEGER,
        question_id INTEGER,
        position INTEGER,
        PRIMARY KEY (paper_id, question_id)
    );

    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER,
        subject TEXT,
        student_name TEXT DEFAULT '学生',
        score REAL DEFAULT 0,
        total REAL DEFAULT 0,
        answers TEXT DEFAULT '{}',
        results TEXT DEFAULT '{}',
        create_time TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS wrong_book (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_name TEXT DEFAULT '学生',
        subject TEXT,
        question_id INTEGER,
        attempt_id INTEGER,
        wrong_time TEXT DEFAULT (datetime('now', 'localtime')),
        redo_count INTEGER DEFAULT 0,
        mastered INTEGER DEFAULT 0,
        UNIQUE(student_name, question_id)
    );
    """)
    conn.commit()
    conn.close()


def row_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    for key in ("options",):
        if key in d and isinstance(d.get(key), str):
            try:
                d[key] = json.loads(d[key])
            except Exception:
                pass
    return d
