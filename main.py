from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sqlite3
import uuid
from datetime import datetime, timedelta
import logging

# ====================== 日志配置（重要！） ======================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI酒馆 - 用户模块")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="templates"), name="static")

security = HTTPBearer()

def get_db():
    conn = sqlite3.connect("tavern_users.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.created_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ? 
              AND s.expires_at > datetime('now')
        """, (token,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=401, detail={"code": 401, "message": "会话已过期或无效"})
        return dict(user)
    finally:
        conn.close()

@app.get("/")
async def home():
    return FileResponse("templates/index.html")

# ====================== 获取当前用户 ======================
@app.get("/api/me")
async def get_current_user_endpoint(credentials: HTTPAuthorizationCredentials = Depends(security)):
    user = get_current_user(credentials)
    logger.info(f"GET /api/me | 用户 {user['username']} (ID: {user['id']}) 成功获取当前会话信息")
    return {"code": 200, "data": user}

# ====================== 退出登录 ======================
@app.post("/api/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
        conn.commit()
        logger.info(f"POST /api/logout | Token 已成退出")
        return {"code": 200, "message": "退出成功"}
    finally:
        conn.close()

# ====================== 登录 ======================
@app.post("/api/login")
async def login(data: dict):
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        logger.warning(f"POST /api/login | 失败：用户名或密码为空")
        return {"code": 400, "message": "账号或密码不能为空"}

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, created_at FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cursor.fetchone()

        if not user:
            logger.warning(f"POST /api/login | 失败：用户名 '{username}' 密码错误")
            return {"code": 401, "message": "用户名或密码错误"}

        session_token = uuid.uuid4().hex
        expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO sessions (session_token, user_id, expires_at)
            VALUES (?, ?, ?)
        """, (session_token, user["id"], expires_at))
        conn.commit()

        user_dict = dict(user)
        user_dict["token"] = session_token

        logger.info(f"POST /api/login | 成功 | 用户: {username} | UserID: {user['id']} | Token生成成功")
        return {"code": 200, "message": "登录成功", "data": user_dict}
    finally:
        conn.close()

# ====================== 注册 ======================
@app.post("/api/register")
async def register(data: dict):
    username = data.get("username")
    password = data.get("password")
    
    if not username or not password:
        logger.warning(f"POST /api/register | 失败：用户名或密码为空")
        return {"code": 400, "message": "账号或密码不能为空"}

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            logger.warning(f"POST /api/register | 失败：用户名 '{username}' 已存在")
            return {"code": 409, "message": "用户已存在"}

        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, password)
        )
        conn.commit()

        logger.info(f"POST /api/register | 成功 | 新用户注册: {username}")
        return {"code": 200, "message": "注册成功！请登录"}
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    print("🍷 酒馆已开张: http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)