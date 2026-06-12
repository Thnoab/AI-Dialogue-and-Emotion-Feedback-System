import os
import json
import sqlite3
import uuid
import hashlib
import time
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# ================= 全局配置项 =================
INVITE_CODE = "Invited@123"           # VIP 邀请码
ADMIN_SECRET_SUFFIX = "@P2m;"         # 管理员动态秘钥后缀
# ==============================================

class TrpgGuideSettingRequest(BaseModel):
    hide_trpg_guide: bool

class UserAuthService:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.user_system_dir = os.getenv(
            "USER_SYSTEM_DIR",
            os.path.abspath(os.path.join(self.base_dir, "..", "user"))
        )
        self.user_db_path = os.path.join(self.user_system_dir, "tavern_users.db")
        self.user_profile_dir = os.path.join(self.user_system_dir, "player_cards")
        self.security = HTTPBearer()

    # ==================== 数据库与用户档案工具 ====================
    def get_user_db(self):
        conn = sqlite3.connect(self.user_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_user_profile_path(self, username: str):
        return os.path.join(self.user_profile_dir, f"{username}_profile.json")

    def load_user_profile_by_username(self, username: str):
        profile_path = self.get_user_profile_path(username)

        if not os.path.exists(profile_path):
            return {
                "username": username,
                "level": 1,
                "is_vip": 0,
                "role": "Adventurer",
                "status": "active",
                "settings": {
                    "hide_trpg_guide": False
                }
            }
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
        except json.JSONDecodeError:
            raise HTTPException(status_code=500, detail="用户档案 JSON 格式错误")
        if "role" not in profile:
            profile["role"] = "Adventurer"
        if "settings" not in profile or not isinstance(profile["settings"], dict):
            profile["settings"] = {}
        if "hide_trpg_guide" not in profile["settings"]:
            profile["settings"]["hide_trpg_guide"] = False
        return profile

    def save_user_profile(self, profile: dict):
        username = profile.get("username")
        if not username:
            raise HTTPException(status_code=400, detail="用户档案缺少 username")
        profile_path = self.get_user_profile_path(username)
        os.makedirs(os.path.dirname(profile_path), exist_ok=True)
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)

    def get_role_from_json(self, username: str) -> str:
        profile = self.load_user_profile_by_username(username)
        return profile.get("role", "Adventurer")

    def create_default_profile(self, username: str, email: str, personal_code: str):
        os.makedirs(self.user_profile_dir, exist_ok=True)
        profile = {
            "username": username,
            "email": email,
            "level": 1,
            "personal_code": personal_code,
            "is_vip": 0,
            "role": "Adventurer",
            "status": "active",
            "settings": {
                "hide_trpg_guide": False
            }
        }
        with open(self.get_user_profile_path(username), "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)
        return profile

    # ==================== 鉴权与权限判断 ====================

    def verificare(self, token: str):
        conn = self.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    u.id,
                    u.username,
                    u.email,
                    u.level,
                    u.personal_code,
                    u.is_vip,
                    u.avatar,
                    u.created_at
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_token = ?
                AND s.expires_at > datetime('now')
                """,
                (token,)
            )
            user = cursor.fetchone()
            if not user:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": 401,
                        "message": "会话已过期或无效"
                    }
                )
            user_dict = dict(user)
            user_dict["role"] = self.get_role_from_json(user_dict["username"])
            return user_dict
        finally:
            conn.close()

    def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
        token = credentials.credentials
        return self.verificare(token)

    def can_use_trpg(self, user: dict) -> bool:
        return user.get("is_vip") == 1 or user.get("role") == "Admin"

    def scoped_session_id(self, user: dict, session_id: str):
        """
        兼容保留：如果之后想用 session_id 前缀隔离可以调用。
        当前主逻辑建议保留原 session_id，另外向记忆层传 user_id。
        """
        prefix = f"u{user['id']}_"
        if session_id.startswith(prefix):
            return session_id
        return prefix + session_id


def create_user_router(auth_service: UserAuthService):
    router = APIRouter()

    # ==================== 当前用户与个人档案 ====================
    @router.get("/api/me")
    def get_current_user_endpoint(
        user: dict = Depends(auth_service.get_current_user)
    ):
        return {
            "code": 200,
            "data": user
        }
    @router.get("/user/profile")
    def get_user_profile(
        user: dict = Depends(auth_service.get_current_user)
    ):
        profile = auth_service.load_user_profile_by_username(user["username"])
        return {
            "profile": profile
        }

    @router.post("/user/profile/trpg-guide")
    def update_trpg_guide_setting(
        req: TrpgGuideSettingRequest,
        user: dict = Depends(auth_service.get_current_user)
    ):
        profile = auth_service.load_user_profile_by_username(user["username"])
        if "settings" not in profile or not isinstance(profile["settings"], dict):
            profile["settings"] = {}
        profile["settings"]["hide_trpg_guide"] = req.hide_trpg_guide
        auth_service.save_user_profile(profile)
        return {
            "status": "success",
            "hide_trpg_guide": profile["settings"]["hide_trpg_guide"]
        }

    # ==================== 登录 / 注册 / 退出 ====================

    @router.post("/api/login")
    def login(data: dict):
        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return {
                "code": 400,
                "message": "账号或密码不能为空"
            }
        conn = auth_service.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id,
                    username,
                    email,
                    level,
                    personal_code,
                    is_vip,
                    avatar,
                    created_at
                FROM users
                WHERE username = ?
                AND password = ?
                """,
                (username, password)
            )
            user = cursor.fetchone()
            if not user:
                return {
                    "code": 401,
                    "message": "用户名或密码错误"
                }
            session_token = uuid.uuid4().hex
            expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                INSERT INTO sessions (session_token, user_id, expires_at)
                VALUES (?, ?, ?)
                """,
                (session_token, user["id"], expires_at)
            )
            conn.commit()
            user_dict = dict(user)
            user_dict["token"] = session_token
            user_dict["role"] = auth_service.get_role_from_json(user_dict["username"])
            return {
                "code": 200,
                "message": "登录成功",
                "data": user_dict
            }
        finally:
            conn.close()

    @router.post("/api/register")
    def register(data: dict):
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")
        if not username or not email or not password:
            return {
                "code": 400,
                "message": "信息填写不完整"
            }
        conn = auth_service.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                return {
                    "code": 409,
                    "message": "用户已存在"
                }
            personal_code = hashlib.sha256(
                f"{username}_{time.time()}_secret".encode("utf-8")
            ).hexdigest()[:16].upper()
            cursor.execute(
                """
                INSERT INTO users
                (username, email, password, level, personal_code, is_vip, avatar)
                VALUES (?, ?, ?, ?, ?, 0, '')
                """,
                (username, email, password, 1, personal_code)
            )
            conn.commit()
            auth_service.create_default_profile(
                username=username,
                email=email,
                personal_code=personal_code
            )
            return {
                "code": 200,
                "message": "注册成功！请登录"
            }
        finally:
            conn.close()

    @router.post("/api/logout")
    def logout(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
        token = credentials.credentials
        conn = auth_service.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
            conn.commit()
            return {
                "code": 200,
                "message": "退出成功"
            }
        finally:
            conn.close()

    # ==================== 密码相关 ====================
    @router.post("/api/recover_password")
    def recover_password(data: dict):
        username = data.get("username")
        email = data.get("email")
        new_password = data.get("new_password")

        if not username or not email or not new_password:
            return {
                "code": 400,
                "message": "信息不完整"
            }
        conn = auth_service.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM users WHERE username = ? AND email = ?",
                (username, email)
            )
            user = cursor.fetchone()
            if not user:
                return {
                    "code": 404,
                    "message": "账号或邮箱错误"
                }
            cursor.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (new_password, user["id"])
            )
            conn.commit()
            return {
                "code": 200,
                "message": "密码重置成功！"
            }
        finally:
            conn.close()
    @router.post("/api/change_password")
    def change_password(
        data: dict,
        user: dict = Depends(auth_service.get_current_user)
    ):
        old_password = data.get("old_password")
        new_password = data.get("new_password")
        if not old_password or not new_password:
            return {
                "code": 400,
                "message": "密码不能为空"
            }
        conn = auth_service.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM users WHERE id = ? AND password = ?",
                (user["id"], old_password)
            )
            if not cursor.fetchone():
                return {
                    "code": 401,
                    "message": "原密码输入错误"
                }
            cursor.execute(
                "UPDATE users SET password = ? WHERE id = ?",
                (new_password, user["id"])
            )
            conn.commit()
            return {
                "code": 200,
                "message": "密码修改成功，请重新登录"
            }
        finally:
            conn.close()

    # ==================== VIP / Admin 权限相关 ====================
    @router.post("/api/redeem_code")
    def redeem_code(
        data: dict,
        user: dict = Depends(auth_service.get_current_user)
    ):
        code = data.get("code", "")
        if not code:
            return {
                "code": 400,
                "message": "兑换码不能为空"
            }
        today_str = datetime.now().strftime("%Y%m%d")
        dynamic_admin_key = f"{today_str}{ADMIN_SECRET_SUFFIX}"
        profile_path = auth_service.get_user_profile_path(user["username"])
        if code == dynamic_admin_key:
            if os.path.exists(profile_path):
                profile = auth_service.load_user_profile_by_username(user["username"])
                profile["role"] = "Admin"
                auth_service.save_user_profile(profile)

                return {
                    "code": 200,
                    "message": "秘钥验证成功！您已拥有管理员最高权限。",
                    "data": {
                        "type": "admin"
                    }
                }
            return {
                "code": 500,
                "message": "找不到档案文件"
            }
        if code == INVITE_CODE:
            if user["is_vip"] == 1:
                return {
                    "code": 400,
                    "message": "您已经是 VIP 了！"
                }
            conn = auth_service.get_user_db()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET is_vip = 1 WHERE id = ?",
                    (user["id"],)
                )
                conn.commit()
            finally:
                conn.close()
            if os.path.exists(profile_path):
                profile = auth_service.load_user_profile_by_username(user["username"])
                profile["is_vip"] = 1
                auth_service.save_user_profile(profile)
            return {
                "code": 200,
                "message": "兑换成功！已为您开通 VIP 权限。",
                "data": {
                    "type": "vip"
                }
            }
        return {
            "code": 400,
            "message": "无效的秘钥或邀请码"
        }
    @router.post("/api/upgrade_vip")
    def upgrade_vip(user: dict = Depends(auth_service.get_current_user)):
        conn = auth_service.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET is_vip = 1 WHERE id = ?",
                (user["id"],)
            )
            conn.commit()

            profile = auth_service.load_user_profile_by_username(user["username"])
            profile["is_vip"] = 1
            auth_service.save_user_profile(profile)

            return {
                "code": 200,
                "message": "支付成功！"
            }

        finally:
            conn.close()

    # ==================== 个人资料与账号操作 ====================

    @router.post("/api/update_profile")
    def update_profile(
        data: dict,
        user: dict = Depends(auth_service.get_current_user)
    ):
        new_username = data.get("username")
        new_avatar = data.get("avatar")

        conn = auth_service.get_user_db()

        try:
            cursor = conn.cursor()

            if new_username and new_username != user["username"]:
                cursor.execute("SELECT id FROM users WHERE username = ?", (new_username,))

                if cursor.fetchone():
                    return {
                        "code": 409,
                        "message": "被占用"
                    }
            final_username = new_username or user["username"]
            final_avatar = new_avatar or user["avatar"]
            cursor.execute(
                "UPDATE users SET username = ?, avatar = ? WHERE id = ?",
                (final_username, final_avatar, user["id"])
            )
            conn.commit()
            old_path = auth_service.get_user_profile_path(user["username"])
            new_path = auth_service.get_user_profile_path(final_username)
            if os.path.exists(old_path):
                with open(old_path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                profile["username"] = final_username
                if new_avatar:
                    profile["avatar"] = new_avatar
                with open(new_path, "w", encoding="utf-8") as f:
                    json.dump(profile, f, ensure_ascii=False, indent=4)
                if new_username and new_username != user["username"]:
                    os.remove(old_path)
            return {
                "code": 200,
                "message": "更新成功"
            }
        finally:
            conn.close()

    @router.post("/api/delete_account")
    def delete_account(user: dict = Depends(auth_service.get_current_user)):
        conn = auth_service.get_user_db()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = ?", (user["id"],))
            conn.commit()
            profile_path = auth_service.get_user_profile_path(user["username"])
            if os.path.exists(profile_path):
                os.remove(profile_path)
            return {
                "code": 200,
                "message": "注销成功"
            }
        finally:
            conn.close()
    return router