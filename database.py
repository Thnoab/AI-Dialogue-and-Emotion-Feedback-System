import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'tavern.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            prompt TEXT NOT NULL,
            attributes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def create_character(name, description, prompt, attributes_dict):
    conn = get_db()
    attributes_json = json.dumps(attributes_dict, ensure_ascii=False)
    conn.execute(
        'INSERT INTO characters (name, description, prompt, attributes) VALUES (?, ?, ?, ?)',
        (name, description, prompt, attributes_json)
    )
    conn.commit()
    last_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    return last_id

def get_all_characters():
    conn = get_db()
    rows = conn.execute('SELECT * FROM characters ORDER BY created_at DESC').fetchall()
    conn.close()
    characters = []
    for row in rows:
        char = dict(row)
        char['attributes'] = json.loads(char['attributes']) if char['attributes'] else {}
        characters.append(char)
    return characters

def get_character_by_name(name):
    conn = get_db()
    row = conn.execute('SELECT * FROM characters WHERE name = ?', (name,)).fetchone()
    conn.close()
    if row:
        char = dict(row)
        char['attributes'] = json.loads(char['attributes']) if char['attributes'] else {}
        return char
    return None