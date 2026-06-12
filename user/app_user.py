from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sqlite3
import uuid
from datetime import datetime, timedelta
import hashlib
import time

app = FastAPI(title="AI酒馆 - 用户与鉴权模块")

# 跨域支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 使用 templates 文件夹挂载前端页面
app.mount("/static", StaticFiles(directory="templates"), name="static")

security = HTTPBearer()

def get_db():
    conn = sqlite3.connect("tavern_users.db")
    conn.row_factory = sqlite3.Row
    return conn

# ==================== 核心身份依赖 (提供给全组调用) ====================
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    解析请求头中的 Token，返回当前用户的完整信息（包含等级和识别码）。
    队友在他们的路由里注入这个依赖，就能实现数据隔离。
    """
    token = credentials.credentials
    print(f"\n[Auth-鉴权] 正在校验客户端 Token: {token[:8]}...")
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        # 新增查询 level 和 personal_code 字段
        cursor.execute("""
            SELECT u.id, u.username, u.level, u.personal_code, u.created_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ? 
              AND s.expires_at > datetime('now')
        """, (token,))
        user = cursor.fetchone()
        
        if not user:
            print(f"❌ [Auth-鉴权] 校验失败: Token 无效或已过期")
            raise HTTPException(status_code=401, detail={"code": 401, "message": "会话已过期或无效"})
            
        print(f"✅ [Auth-鉴权] 校验通过！当前用户: {user['username']} (等级: Lv.{user['level']})")
        return dict(user)
    finally:
        conn.close()

# ==================== 页面与接口路由 ====================
@app.get("/")
async def home():
    return FileResponse("templates/index.html")

@app.get("/api/me")
async def get_current_user_endpoint(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # 刷新页面时，前端调用此接口恢复用户的状态和个人信息
    return {"code": 200, "data": get_current_user(credentials)}

@app.post("/api/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    print(f"\n[Auth-退出] 收到退出注销请求，正在销毁 Token: {token[:8]}...")
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
        conn.commit()
        print("✅ [Auth-退出] 会话已从 sessions 表中安全清除。")
        return {"code": 200, "message": "退出成功"}
    finally:
        conn.close()

@app.post("/api/login")
async def login(data: dict):
    username = data.get("username")
    password = data.get("password")
    print(f"\n[Auth-登录] 收到用户登录请求: username={username}")

    if not username or not password:
        return {"code": 400, "message": "账号或密码不能为空"}

    conn = get_db()
    try:
        cursor = conn.cursor()
        # 新增查询 level 和 personal_code 字段
        cursor.execute(
            "SELECT id, username, level, personal_code, created_at FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cursor.fetchone()
        if not user:
            print(f"❌ [Auth-登录] 登录失败: 用户名或密码错误")
            return {"code": 401, "message": "用户名或密码错误"}

        session_token = uuid.uuid4().hex
        expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            INSERT INTO sessions (session_token, user_id, expires_at)
            VALUES (?, ?, ?)
        """, (session_token, user["id"], expires_at))
        conn.commit()

        print(f"✅ [Auth-登录] 登录成功！已为用户 '{username}' 生成会话 Token")

        user_dict = dict(user)
        user_dict["token"] = session_token
        return {"code": 200, "message": "登录成功", "data": user_dict}
    finally:
        conn.close()

@app.post("/api/register")
async def register(data: dict):
    username = data.get("username")
    password = data.get("password")
    print(f"\n[Auth-注册] 收到新用户注册请求: username={username}")

    if not username or not password:
        return {"code": 400, "message": "账号或密码不能为空"}

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            print(f"❌ [Auth-注册] 注册失败: 用户名 '{username}' 已存在")
            return {"code": 409, "message": "用户已存在"}

        # ========== 核心升级：生成哈希加密的专属识别码 ==========
        # 将 "用户名+当前时间戳+盐值" 拼接
        raw_string = f"{username}_{time.time()}_tavern_secret"
        # 使用 SHA-256 进行哈希加密
        hashed_code = hashlib.sha256(raw_string.encode('utf-8')).hexdigest()
        # 截取前 16 位作为大写识别码
        personal_code = hashed_code[:16].upper() 
        # ========================================================

        cursor.execute(
            "INSERT INTO users (username, password, level, personal_code) VALUES (?, ?, ?, ?)",
            (username, password, 1, personal_code)
        )
        conn.commit()
        print(f"✅ [Auth-注册] 注册成功！分配专属识别码: {personal_code}")
        return {"code": 200, "message": "注册成功！请登录"}
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    print("🍷 酒馆身份认证中心已启动: http://localhost:8000")
    uvicorn.run("app_user:app", host="0.0.0.0", port=8000, reload=True)