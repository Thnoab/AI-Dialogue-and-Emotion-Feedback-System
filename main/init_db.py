import sqlite3
import os

def init_db():
    db_name = 'tavern_users.db'
    if os.path.exists(db_name):
        print(f"提示：发现已存在的数据库文件 '{db_name}'，请删除后重试以应用新字段。")
    
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # 新增了 email 字段
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,                  -- 💡 新增：预留邮箱
        password TEXT NOT NULL,
        level INTEGER DEFAULT 1,
        personal_code TEXT UNIQUE NOT NULL,
        is_vip INTEGER DEFAULT 0,
        avatar TEXT DEFAULT '',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_token TEXT UNIQUE NOT NULL,
        user_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    ''')

    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成！包含了邮箱字段。")

if __name__ == "__main__":
    init_db()