import sqlite3
import shlex
import random
import os
import json
import re


class SheetCommandError(ValueError):
    pass


class TrpgSheetStore:
    """
    COC 七版角色卡系统。
    - 保留原来的 @Dice card add / hp / san / check / sheet / cards 等命令
    - 扩展完整 COC 字段、技能表、AI 生成完整卡、网页编辑保存
    - 支持可细分技能：外语/生存/科学/艺术与手艺/驾驶/格斗/射击/学问，每类最多 3 个
    - 支持自定义技能，最多 3 个
    - 支持 @Dice sancheck 1 0/1d6 这样的自动理智检定和 SAN 扣除
    """

    DEFAULT_SKILLS = [
        ("会计", 5), ("人类学", 1), ("估价", 5), ("考古学", 1), ("魅惑", 15),
        ("攀爬", 20), ("计算机使用", 5), ("信用评级", 0), ("克苏鲁神话", 0),
        ("乔装", 5), ("闪避", 0), ("汽车驾驶", 20), ("电气维修", 10), ("电子学", 1),
        ("话术", 5), ("格斗", 25), ("射击", 20), ("急救", 30), ("历史", 5),
        ("恐吓", 15), ("跳跃", 20), ("母语", 0), ("法律", 5), ("图书馆使用", 20),
        ("聆听", 20), ("锁匠", 1), ("机械维修", 10), ("医学", 1), ("博物学", 10),
        ("导航", 10), ("神秘学", 5), ("操作重型机械", 1), ("说服", 10),
        ("精神分析", 1), ("心理学", 10), ("骑术", 5), ("妙手", 10), ("侦查", 25),
        ("潜行", 20), ("生存", 10), ("游泳", 20), ("投掷", 20), ("追踪", 10),
        ("艺术与手艺", 5), ("科学", 1), ("外语", 1), ("学问", 1),
    ]

    EXPANDABLE_SKILL_CATEGORIES = {
        "外语",
        "生存",
        "科学",
        "艺术与手艺",
        "技艺",
        "驾驶",
        "格斗",
        "射击",
        "学问",
    }

    CATEGORY_NORMALIZE = {
        "技艺": "艺术与手艺",
        "艺术": "艺术与手艺",
        "手艺": "艺术与手艺",
        "汽车驾驶": "驾驶",
        "驾驶汽车": "驾驶",
        "枪械": "射击",
        "火器": "射击",
        "知识": "学问",
    }

    MAX_SUB_SKILLS_PER_CATEGORY = 3
    MAX_CUSTOM_SKILLS = 3

    FIELD_ALIASES = {
        "力量": "STR", "STR": "STR",
        "敏捷": "DEX", "DEX": "DEX",
        "意志": "POW", "POW": "POW",
        "体质": "CON", "CON": "CON",
        "外貌": "APP", "APP": "APP",
        "教育": "EDU", "EDU": "EDU",
        "体型": "SIZ", "SIZ": "SIZ",
        "智力": "INS", "INT": "INS", "INS": "INS",
        "血量": "HP", "HP": "HP",
        "理智": "SAN", "SAN": "SAN",
        "魔法": "MP", "MP": "MP",
        "幸运": "LUCK", "LUCK": "LUCK",
        "移动力": "MOV", "MOV": "MOV",
        "体格": "BUILD", "BUILD": "BUILD",
        "伤害奖励": "DAMAGE_BONUS", "DB": "DAMAGE_BONUS", "DAMAGE_BONUS": "DAMAGE_BONUS",
        "信用评级": "CREDIT_RATING", "信誉": "CREDIT_RATING", "CREDIT": "CREDIT_RATING", "CREDIT_RATING": "CREDIT_RATING",
    }

    def __init__(self, db_path="TRPG_CharacterSheet.db"):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "TRPG_CharacterSheet.db")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cor = self.conn.cursor()
        self.ensure_schema()

    # ==================== schema ====================

    def ensure_schema(self):
        self.cor.execute("""
        CREATE TABLE IF NOT EXISTS trpg_character_sheet(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            local_id INTEGER NOT NULL,
            owner_id TEXT DEFAULT '',
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            occupation TEXT DEFAULT '',
            residence TEXT DEFAULT '',
            birthplace TEXT DEFAULT '',
            str_val INTEGER NOT NULL,
            dex INTEGER NOT NULL,
            pow INTEGER NOT NULL,
            con INTEGER NOT NULL,
            app INTEGER NOT NULL,
            edu INTEGER NOT NULL,
            siz INTEGER NOT NULL,
            ins INTEGER NOT NULL,
            luck INTEGER DEFAULT 0,
            max_hp INTEGER NOT NULL,
            hp INTEGER NOT NULL,
            max_san INTEGER NOT NULL,
            san INTEGER NOT NULL,
            max_mp INTEGER DEFAULT 0,
            mp INTEGER DEFAULT 0,
            mov INTEGER NOT NULL,
            damage_bonus TEXT DEFAULT '0',
            build TEXT DEFAULT '0',
            credit_rating INTEGER DEFAULT 0,
            background TEXT DEFAULT '',
            personal_description TEXT DEFAULT '',
            ideology TEXT DEFAULT '',
            important_people TEXT DEFAULT '',
            meaningful_locations TEXT DEFAULT '',
            treasured_possessions TEXT DEFAULT '',
            traits TEXT DEFAULT '',
            injuries TEXT DEFAULT '',
            phobias TEXT DEFAULT '',
            spells TEXT DEFAULT '',
            possessions TEXT DEFAULT '',
            cash_assets TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            UNIQUE(session_id, local_id)
        )
        """)
        self.cor.execute("PRAGMA table_info(trpg_character_sheet)")
        existing = {row["name"] for row in self.cor.fetchall()}
        desired = {
            "occupation": "TEXT DEFAULT ''",
            "residence": "TEXT DEFAULT ''",
            "birthplace": "TEXT DEFAULT ''",
            "luck": "INTEGER DEFAULT 0",
            "max_mp": "INTEGER DEFAULT 0",
            "mp": "INTEGER DEFAULT 0",
            "damage_bonus": "TEXT DEFAULT '0'",
            "build": "TEXT DEFAULT '0'",
            "credit_rating": "INTEGER DEFAULT 0",
            "background": "TEXT DEFAULT ''",
            "personal_description": "TEXT DEFAULT ''",
            "ideology": "TEXT DEFAULT ''",
            "important_people": "TEXT DEFAULT ''",
            "meaningful_locations": "TEXT DEFAULT ''",
            "treasured_possessions": "TEXT DEFAULT ''",
            "traits": "TEXT DEFAULT ''",
            "injuries": "TEXT DEFAULT ''",
            "phobias": "TEXT DEFAULT ''",
            "spells": "TEXT DEFAULT ''",
            "possessions": "TEXT DEFAULT ''",
            "cash_assets": "TEXT DEFAULT ''",
            "notes": "TEXT DEFAULT ''",
        }
        for column, ddl in desired.items():
            if column not in existing:
                self.cor.execute(f"ALTER TABLE trpg_character_sheet ADD COLUMN {column} {ddl}")

        self.cor.execute("""
        CREATE TABLE IF NOT EXISTS trpg_character_skill(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            local_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            base_value INTEGER DEFAULT 0,
            value INTEGER DEFAULT 0,
            checked INTEGER DEFAULT 0,
            note TEXT DEFAULT '',
            UNIQUE(session_id, local_id, skill_name)
        )
        """)
        self.conn.commit()

    # ==================== basic calculation ====================

    def calculate_hp(self, con, siz):
        return max(1, int((con + siz) / 10))

    def calculate_mp(self, pow_val):
        return max(0, int(pow_val / 5))

    def calculate_mov(self, age, str_val, dex, siz):
        if str_val < siz and dex < siz:
            mov = 7
        elif str_val > siz and dex > siz:
            mov = 9
        else:
            mov = 8
        if age >= 40:
            mov -= min((age - 30) // 10, 5)
        return max(mov, 1)

    def calculate_damage_bonus_and_build(self, str_val, siz):
        total = str_val + siz
        if total <= 64:
            return "-2", "-2"
        if total <= 84:
            return "-1", "-1"
        if total <= 124:
            return "0", "0"
        if total <= 164:
            return "+1D4", "1"
        if total <= 204:
            return "+1D6", "2"
        extra = max(0, (total - 205) // 80)
        return f"+{2 + extra}D6", str(3 + extra)

    def validate_stat(self, name, value):
        if not isinstance(value, int):
            raise SheetCommandError(f"{name} 必须是整数")
        if value < 1 or value > 100:
            raise SheetCommandError(f"{name} 必须在 1 到 100 之间")

    def clamp_int(self, value, low=0, high=100, default=0):
        try:
            value = int(value)
        except Exception:
            value = default
        return max(low, min(high, value))

    def next_local_id(self, session_id):
        self.cor.execute("SELECT MAX(local_id) FROM trpg_character_sheet WHERE session_id = ?", (session_id,))
        row = self.cor.fetchone()
        if row is None or row[0] is None:
            return 1
        return int(row[0]) + 1

    # ==================== sheet CRUD ====================

    def create_sheet(
        self,
        session_id,
        owner_id,
        name,
        age,
        gender,
        str_val,
        dex,
        pow_val,
        con,
        app,
        edu,
        siz,
        ins,
        occupation="",
        residence="",
        birthplace="",
        luck=None,
        credit_rating=0,
        background="",
        personal_description="",
        ideology="",
        important_people="",
        meaningful_locations="",
        treasured_possessions="",
        traits="",
        injuries="",
        phobias="",
        spells="",
        possessions="",
        cash_assets="",
        notes="",
        skills=None
    ):
        if not session_id:
            raise SheetCommandError("缺少 session_id，无法录入本局角色卡")
        if not name:
            raise SheetCommandError("角色名不能为空")
        if age < 1:
            raise SheetCommandError("年龄必须大于 0")
        stats = {"STR": str_val, "DEX": dex, "POW": pow_val, "CON": con, "APP": app, "EDU": edu, "SIZ": siz, "INS": ins}
        for stat_name, stat_value in stats.items():
            self.validate_stat(stat_name, stat_value)

        local_id = self.next_local_id(session_id)
        max_hp = self.calculate_hp(con, siz)
        max_san = pow_val
        max_mp = self.calculate_mp(pow_val)
        mov = self.calculate_mov(age, str_val, dex, siz)
        damage_bonus, build = self.calculate_damage_bonus_and_build(str_val, siz)
        if luck is None:
            luck = max(1, min(100, pow_val))

        self.cor.execute(
            """
            INSERT INTO trpg_character_sheet(
                session_id, local_id, owner_id,
                name, age, gender, occupation, residence, birthplace,
                str_val, dex, pow, con, app, edu, siz, ins, luck,
                max_hp, hp, max_san, san, max_mp, mp, mov,
                damage_bonus, build, credit_rating,
                background, personal_description, ideology, important_people,
                meaningful_locations, treasured_possessions, traits, injuries,
                phobias, spells, possessions, cash_assets, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, local_id, owner_id,
                name, age, gender, occupation, residence, birthplace,
                str_val, dex, pow_val, con, app, edu, siz, ins, int(luck),
                max_hp, max_hp, max_san, max_san, max_mp, max_mp, mov,
                damage_bonus, build, int(credit_rating or 0),
                background, personal_description, ideology, important_people,
                meaningful_locations, treasured_possessions, traits, injuries,
                phobias, spells, possessions, cash_assets, notes
            )
        )
        self.init_default_skills(session_id, local_id, edu, dex, skills or [], occupation)
        self.conn.commit()
        return self.get_sheet(session_id, local_id)

    def create_full_sheet(self, session_id, owner_id, data):
        stats = data.get("stats", data)
        return self.create_sheet(
            session_id=session_id,
            owner_id=owner_id,
            name=data.get("name", "未命名调查员"),
            age=int(data.get("age", 25)),
            gender=data.get("gender", "未知"),
            occupation=data.get("occupation", ""),
            residence=data.get("residence", ""),
            birthplace=data.get("birthplace", ""),
            str_val=int(stats.get("STR", 50)),
            dex=int(stats.get("DEX", 50)),
            pow_val=int(stats.get("POW", 50)),
            con=int(stats.get("CON", 50)),
            app=int(stats.get("APP", 50)),
            edu=int(stats.get("EDU", 50)),
            siz=int(stats.get("SIZ", 50)),
            ins=int(stats.get("INS", stats.get("INT", 50))),
            luck=int(data.get("luck", stats.get("LUCK", stats.get("POW", 50)))),
            credit_rating=int(data.get("credit_rating", 0)),
            background=data.get("background", ""),
            personal_description=data.get("personal_description", ""),
            ideology=data.get("ideology", ""),
            important_people=data.get("important_people", ""),
            meaningful_locations=data.get("meaningful_locations", ""),
            treasured_possessions=data.get("treasured_possessions", ""),
            traits=data.get("traits", ""),
            injuries=data.get("injuries", ""),
            phobias=data.get("phobias", ""),
            spells=data.get("spells", ""),
            possessions=data.get("possessions", ""),
            cash_assets=data.get("cash_assets", ""),
            notes=data.get("notes", ""),
            skills=data.get("skills", [])
        )

    def update_full_sheet(self, session_id, local_id, data):
        stats = data.get("stats", data)
        old = self.get_sheet(session_id, local_id)

        name = data.get("name", old["name"])
        age = int(data.get("age", old["age"]))
        gender = data.get("gender", old["gender"])
        occupation = data.get("occupation", old.get("occupation", ""))
        residence = data.get("residence", old.get("residence", ""))
        birthplace = data.get("birthplace", old.get("birthplace", ""))

        str_val = int(stats.get("STR", old["STR"]))
        dex = int(stats.get("DEX", old["DEX"]))
        pow_val = int(stats.get("POW", old["POW"]))
        con = int(stats.get("CON", old["CON"]))
        app = int(stats.get("APP", old["APP"]))
        edu = int(stats.get("EDU", old["EDU"]))
        siz = int(stats.get("SIZ", old["SIZ"]))
        ins = int(stats.get("INS", stats.get("INT", old["INS"])))

        for stat_name, stat_value in {
            "STR": str_val, "DEX": dex, "POW": pow_val, "CON": con,
            "APP": app, "EDU": edu, "SIZ": siz, "INS": ins
        }.items():
            self.validate_stat(stat_name, stat_value)

        max_hp = self.calculate_hp(con, siz)
        max_san = pow_val
        max_mp = self.calculate_mp(pow_val)
        mov = self.calculate_mov(age, str_val, dex, siz)
        damage_bonus, build = self.calculate_damage_bonus_and_build(str_val, siz)

        hp = self.clamp_int(data.get("hp", old["hp"]), 0, max_hp, old["hp"])
        san = self.clamp_int(data.get("san", old["san"]), 0, max_san, old["san"])
        mp = self.clamp_int(data.get("mp", old["mp"]), 0, max_mp, old["mp"])
        luck = self.clamp_int(data.get("luck", old.get("luck", pow_val)), 0, 100, old.get("luck", pow_val))
        credit_rating = self.clamp_int(data.get("credit_rating", old.get("credit_rating", 0)), 0, 100, old.get("credit_rating", 0))

        self.cor.execute(
            """
            UPDATE trpg_character_sheet
            SET name=?, age=?, gender=?, occupation=?, residence=?, birthplace=?,
                str_val=?, dex=?, pow=?, con=?, app=?, edu=?, siz=?, ins=?, luck=?,
                max_hp=?, hp=?, max_san=?, san=?, max_mp=?, mp=?, mov=?,
                damage_bonus=?, build=?, credit_rating=?,
                background=?, personal_description=?, ideology=?, important_people=?,
                meaningful_locations=?, treasured_possessions=?, traits=?, injuries=?,
                phobias=?, spells=?, possessions=?, cash_assets=?, notes=?
            WHERE session_id=? AND local_id=?
            """,
            (
                name, age, gender, occupation, residence, birthplace,
                str_val, dex, pow_val, con, app, edu, siz, ins, luck,
                max_hp, hp, max_san, san, max_mp, mp, mov,
                damage_bonus, build, credit_rating,
                data.get("background", old.get("background", "")),
                data.get("personal_description", old.get("personal_description", "")),
                data.get("ideology", old.get("ideology", "")),
                data.get("important_people", old.get("important_people", "")),
                data.get("meaningful_locations", old.get("meaningful_locations", "")),
                data.get("treasured_possessions", old.get("treasured_possessions", "")),
                data.get("traits", old.get("traits", "")),
                data.get("injuries", old.get("injuries", "")),
                data.get("phobias", old.get("phobias", "")),
                data.get("spells", old.get("spells", "")),
                data.get("possessions", old.get("possessions", "")),
                data.get("cash_assets", old.get("cash_assets", "")),
                data.get("notes", old.get("notes", "")),
                session_id, local_id
            )
        )

        if "skills" in data and isinstance(data["skills"], list):
            self.replace_skills(session_id, local_id, data["skills"], edu, dex, occupation)

        self.conn.commit()
        return self.get_sheet(session_id, local_id)

    def row_to_sheet(self, row):
        return {
            "id": row["local_id"], "owner_id": row["owner_id"],
            "name": row["name"], "age": row["age"], "gender": row["gender"],
            "occupation": row["occupation"] or "", "residence": row["residence"] or "", "birthplace": row["birthplace"] or "",
            "STR": row["str_val"], "DEX": row["dex"], "POW": row["pow"], "CON": row["con"],
            "APP": row["app"], "EDU": row["edu"], "SIZ": row["siz"], "INS": row["ins"],
            "luck": row["luck"], "max_hp": row["max_hp"], "hp": row["hp"],
            "max_san": row["max_san"], "san": row["san"], "max_mp": row["max_mp"], "mp": row["mp"],
            "MOV": row["mov"], "damage_bonus": row["damage_bonus"] or "0", "build": row["build"] or "0",
            "credit_rating": row["credit_rating"] or 0,
            "background": row["background"] or "", "personal_description": row["personal_description"] or "",
            "ideology": row["ideology"] or "", "important_people": row["important_people"] or "",
            "meaningful_locations": row["meaningful_locations"] or "", "treasured_possessions": row["treasured_possessions"] or "",
            "traits": row["traits"] or "", "injuries": row["injuries"] or "",
            "phobias": row["phobias"] or "", "spells": row["spells"] or "",
            "possessions": row["possessions"] or "", "cash_assets": row["cash_assets"] or "",
            "notes": row["notes"] or "", "skills": self.list_skills(row["session_id"], row["local_id"])
        }

    def get_sheet(self, session_id, local_id):
        self.cor.execute("SELECT * FROM trpg_character_sheet WHERE session_id = ? AND local_id = ?", (session_id, local_id))
        row = self.cor.fetchone()
        if row is None:
            raise SheetCommandError(f"没有找到角色ID：{local_id}")
        return self.row_to_sheet(row)

    def get_sheet_by_owner(self, session_id, owner_id):
        self.cor.execute(
            "SELECT local_id FROM trpg_character_sheet WHERE session_id = ? AND owner_id = ? ORDER BY local_id DESC LIMIT 1",
            (session_id, owner_id)
        )
        row = self.cor.fetchone()
        if row is None:
            raise SheetCommandError(f"当前身份尚未绑定角色卡：{owner_id}")
        return self.get_sheet(session_id, row["local_id"])

    def list_sheets(self, session_id):
        self.cor.execute("SELECT local_id FROM trpg_character_sheet WHERE session_id = ? ORDER BY local_id ASC", (session_id,))
        ids = [row["local_id"] for row in self.cor.fetchall()]
        return [self.get_sheet(session_id, local_id) for local_id in ids]

    def delete_sheet(self, session_id, local_id):
        self.cor.execute("DELETE FROM trpg_character_skill WHERE session_id = ? AND local_id = ?", (session_id, local_id))
        self.cor.execute("DELETE FROM trpg_character_sheet WHERE session_id = ? AND local_id = ?", (session_id, local_id))
        deleted = self.cor.rowcount
        self.conn.commit()
        return deleted

    def delete_session(self, session_id):
        self.cor.execute("DELETE FROM trpg_character_skill WHERE session_id = ?", (session_id,))
        self.cor.execute("DELETE FROM trpg_character_sheet WHERE session_id = ?", (session_id,))
        deleted_rows = self.cor.rowcount
        self.conn.commit()
        return deleted_rows

    # ==================== skills ====================

    def normalize_category(self, category):
        category = str(category or "").strip()
        return self.CATEGORY_NORMALIZE.get(category, category)

    def make_extended_skill_name(self, category, name):
        category = self.normalize_category(category)
        name = str(name or "").strip()
        if not category or not name:
            raise SheetCommandError("扩展技能类别和名称不能为空")
        if category not in self.EXPANDABLE_SKILL_CATEGORIES:
            raise SheetCommandError(f"不支持的扩展技能类别：{category}")
        if category == "技艺":
            category = "艺术与手艺"
        return f"{category}：{name}"

    def count_extended_skills(self, session_id, local_id, category):
        category = self.normalize_category(category)
        if category == "技艺":
            category = "艺术与手艺"
        prefix = f"{category}："
        self.cor.execute(
            """
            SELECT COUNT(*) AS count
            FROM trpg_character_skill
            WHERE session_id = ? AND local_id = ? AND skill_name LIKE ?
            """,
            (session_id, local_id, f"{prefix}%")
        )
        row = self.cor.fetchone()
        return int(row["count"] if row else 0)

    def count_custom_skills(self, session_id, local_id):
        self.cor.execute(
            """
            SELECT COUNT(*) AS count
            FROM trpg_character_skill
            WHERE session_id = ? AND local_id = ? AND skill_name LIKE '自定义：%'
            """,
            (session_id, local_id)
        )
        row = self.cor.fetchone()
        return int(row["count"] if row else 0)

    def add_extended_skill(self, session_id, local_id, category, name, value, base_value=1, note=""):
        skill_name = self.make_extended_skill_name(category, name)
        existing = self.get_skill_value(session_id, local_id, skill_name)
        if existing is None and self.count_extended_skills(session_id, local_id, category) >= self.MAX_SUB_SKILLS_PER_CATEGORY:
            raise SheetCommandError(f"{self.normalize_category(category)} 类扩展技能最多只能添加 {self.MAX_SUB_SKILLS_PER_CATEGORY} 个")
        self.upsert_skill(session_id, local_id, skill_name, base_value, value, note=note)
        return self.get_skill_value(session_id, local_id, skill_name)

    def add_custom_skill(self, session_id, local_id, name, value, base_value=1, note=""):
        name = str(name or "").strip()
        if not name:
            raise SheetCommandError("自定义技能名称不能为空")
        skill_name = f"自定义：{name}"
        existing = self.get_skill_value(session_id, local_id, skill_name)
        if existing is None and self.count_custom_skills(session_id, local_id) >= self.MAX_CUSTOM_SKILLS:
            raise SheetCommandError(f"自定义技能最多只能添加 {self.MAX_CUSTOM_SKILLS} 个")
        self.upsert_skill(session_id, local_id, skill_name, base_value, value, note=note)
        return self.get_skill_value(session_id, local_id, skill_name)

    def validate_skill_limits(self, session_id, local_id, skills):
        """
        网页保存整张表时检查限制：
        - 每类扩展技能最多 3 个
        - 自定义技能最多 3 个
        """
        category_counter = {}
        custom_count = 0
        for item in skills or []:
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            if name.startswith("自定义："):
                custom_count += 1
                continue
            if "：" in name:
                category = self.normalize_category(name.split("：", 1)[0])
                if category == "技艺":
                    category = "艺术与手艺"
                if category in self.EXPANDABLE_SKILL_CATEGORIES:
                    category_counter[category] = category_counter.get(category, 0) + 1
        if custom_count > self.MAX_CUSTOM_SKILLS:
            raise SheetCommandError(f"自定义技能最多只能添加 {self.MAX_CUSTOM_SKILLS} 个")
        for category, count in category_counter.items():
            if count > self.MAX_SUB_SKILLS_PER_CATEGORY:
                raise SheetCommandError(f"{category} 类扩展技能最多只能添加 {self.MAX_SUB_SKILLS_PER_CATEGORY} 个")

    def init_default_skills(self, session_id, local_id, edu, dex, custom_skills, occupation=""):
        skill_map = {name: base for name, base in self.DEFAULT_SKILLS}
        skill_map["母语"] = edu
        skill_map["闪避"] = max(1, dex // 2)
        default_skill_names = {name for name, _ in self.DEFAULT_SKILLS}

        for skill in custom_skills:
            if isinstance(skill, dict):
                name = str(skill.get("name", "")).strip()
                if not name:
                    continue
                # 如果 AI 创建了非标准技能，例如“植物学”“自然知识”，
                # 自动归入自定义技能槽，保证网页表格能够显示。
                if name not in default_skill_names and "：" not in name:
                    name = f"自定义：{name}"
                value = int(skill.get("value", skill.get("base_value", skill_map.get(name, 1))))
                base = int(skill.get("base_value", skill_map.get(name, 1)))
                skill_map[name] = max(base, value)

        if not custom_skills:
            self.autofill_common_skills(skill_map, occupation, edu)

        # 本项目的角色卡页面中，“初始”和“成功率”采用同一数值。
        # 因此无论是默认技能、职业自动技能，还是 AI 生成的技能，
        # 写入数据库时都令 base_value = value。
        normalized = [
            {
                "name": name,
                "base_value": int(value),
                "value": int(value)
            }
            for name, value in skill_map.items()
        ]
        self.replace_skills(session_id, local_id, normalized, edu, dex, occupation)

    def replace_skills(self, session_id, local_id, skills, edu=50, dex=50, occupation=""):
        self.validate_skill_limits(session_id, local_id, skills)
        self.cor.execute("DELETE FROM trpg_character_skill WHERE session_id = ? AND local_id = ?", (session_id, local_id))
        for item in skills:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            # 本项目的角色卡页面中，“初始”和“成功率”采用同一数值。
            # 如果 AI 只提供 value，则把 value 同时作为 base_value。
            raw_value = item.get("value", item.get("base_value", 1))
            raw_base = item.get("base_value", raw_value)
            base_value = self.clamp_int(raw_base, 0, 100, self.clamp_int(raw_value, 0, 100, 1))
            value = base_value
            note = str(item.get("note", "") or "")
            self.upsert_skill(session_id, local_id, name, base_value, value, note=note)

    def autofill_common_skills(self, skill_map, occupation, edu):
        occ = (occupation or "").lower()
        if any(k in occ for k in ["侦探", "调查", "警察", "记者"]):
            boosts = {"侦查": 60, "聆听": 50, "心理学": 50, "图书馆使用": 50, "话术": 45, "说服": 45, "法律": 35, "射击": 45}
        elif any(k in occ for k in ["医生", "医师", "护士"]):
            boosts = {"医学": 65, "急救": 60, "心理学": 45, "科学": 45, "图书馆使用": 40, "说服": 35, "聆听": 40}
        elif any(k in occ for k in ["教授", "学者", "学生", "研究"]):
            boosts = {"图书馆使用": 65, "历史": 55, "科学": 55, "外语": 45, "母语": max(skill_map.get("母语", edu), edu), "心理学": 35, "估价": 35}
        else:
            boosts = {"侦查": 50, "聆听": 45, "图书馆使用": 40, "心理学": 40, "话术": 35, "闪避": max(skill_map.get("闪避", 25), 35), "急救": 40}
        for name, value in boosts.items():
            skill_map[name] = max(skill_map.get(name, 1), value)

    def list_skills(self, session_id, local_id):
        self.cor.execute(
            """
            SELECT skill_name, base_value, value, checked, note
            FROM trpg_character_skill
            WHERE session_id = ? AND local_id = ?
            ORDER BY skill_name ASC
            """,
            (session_id, local_id)
        )
        return [
            {"name": row["skill_name"], "base_value": row["base_value"], "value": row["value"], "checked": bool(row["checked"]), "note": row["note"] or ""}
            for row in self.cor.fetchall()
        ]

    def upsert_skill(self, session_id, local_id, skill_name, base_value, value, note=""):
        base_value = self.clamp_int(base_value, 0, 100, 1)
        # 兜底保证：数据库中成功率 value 永远等于初始值 base_value。
        value = base_value
        self.cor.execute(
            """
            INSERT INTO trpg_character_skill(session_id, local_id, skill_name, base_value, value, note)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, local_id, skill_name)
            DO UPDATE SET value = excluded.value, base_value = excluded.base_value, note = excluded.note
            """,
            (session_id, local_id, skill_name, base_value, value, note)
        )
        self.conn.commit()

    def get_skill_value(self, session_id, local_id, skill_name):
        self.cor.execute(
            """
            SELECT skill_name, base_value, value
            FROM trpg_character_skill
            WHERE session_id = ? AND local_id = ? AND skill_name = ?
            """,
            (session_id, local_id, skill_name)
        )
        row = self.cor.fetchone()
        if row is None:
            return None
        return {"name": row["skill_name"], "base_value": row["base_value"], "value": row["value"]}

    # ==================== field/check/san ====================

    def normalize_field(self, field):
        raw = str(field or "").strip()
        field_upper = raw.upper()
        if raw in self.FIELD_ALIASES:
            return self.FIELD_ALIASES[raw]
        if field_upper in self.FIELD_ALIASES:
            return self.FIELD_ALIASES[field_upper]
        return raw

    def get_field_value(self, sheet, field):
        field = self.normalize_field(field)
        field_map = {
            "STR": "STR", "DEX": "DEX", "POW": "POW", "CON": "CON",
            "APP": "APP", "EDU": "EDU", "SIZ": "SIZ", "INS": "INS",
            "HP": "hp", "SAN": "san", "MP": "mp", "LUCK": "luck",
            "MOV": "MOV", "BUILD": "build", "DAMAGE_BONUS": "damage_bonus",
            "CREDIT_RATING": "credit_rating", "AGE": "age", "NAME": "name", "GENDER": "gender"
        }
        if field in field_map:
            key = field_map[field]
            value = sheet[key]
            if field == "HP":
                return value, f"{sheet['hp']}/{sheet['max_hp']}"
            if field == "SAN":
                return value, f"{sheet['san']}/{sheet['max_san']}"
            if field == "MP":
                return value, f"{sheet['mp']}/{sheet['max_mp']}"
            return value, str(value)

        for skill in sheet.get("skills", []):
            if skill["name"] == field:
                return skill["value"], str(skill["value"])
        raise SheetCommandError(f"不支持的属性或技能字段：{field}")

    def check_value(self, session_id, local_id, field):
        sheet = self.get_sheet(session_id, local_id)
        value, value_text = self.get_field_value(sheet, field)
        return {"sheet": sheet, "field": field, "value": value, "value_text": value_text}

    def update_resource(self, session_id, local_id, resource, delta):
        resource = resource.lower()
        if resource not in ["hp", "san", "mp"]:
            raise SheetCommandError("只能修改 hp、san 或 mp")
        sheet = self.get_sheet(session_id, local_id)
        old_value = sheet[resource]
        max_key = f"max_{resource}"
        max_value = sheet[max_key] if max_key in sheet else old_value
        new_value = max(0, min(old_value + delta, max_value))
        self.cor.execute(
            f"UPDATE trpg_character_sheet SET {resource} = ? WHERE session_id = ? AND local_id = ?",
            (new_value, session_id, local_id)
        )
        self.conn.commit()
        updated = self.get_sheet(session_id, local_id)
        return {"sheet": updated, "resource": resource.upper(), "old_value": old_value, "new_value": new_value, "delta": delta}

    def roll_loss_expr(self, expr):
        expr = str(expr or "0").strip().lower()
        if not expr:
            return 0, "0"
        if re.fullmatch(r"\d+", expr):
            value = int(expr)
            return value, str(value)
        match = re.fullmatch(r"(\d*)d(\d+)", expr)
        if not match:
            raise SheetCommandError(f"不支持的损失表达式：{expr}")
        count = int(match.group(1) or 1)
        sides = int(match.group(2))
        if count < 1 or count > 20 or sides < 1 or sides > 100:
            raise SheetCommandError(f"损失骰表达式超出范围：{expr}")
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        return total, f"{expr}={'+'.join(map(str, rolls))}={total}"

    def san_check(self, session_id, local_id, loss_expr):
        sheet = self.get_sheet(session_id, local_id)
        san_now = int(sheet["san"])
        if "/" in loss_expr:
            success_expr, fail_expr = loss_expr.split("/", 1)
        else:
            success_expr, fail_expr = "0", loss_expr
        roll = random.randint(1, 100)
        success = roll <= san_now
        chosen = success_expr if success else fail_expr
        loss, loss_text = self.roll_loss_expr(chosen)
        result = self.update_resource(session_id, local_id, "san", -loss)
        updated = result["sheet"]
        symbol = "<=" if success else ">"
        outcome = "成功" if success else "失败"
        text = (
            f"{sheet['name']} 进行理智检定。\n"
            f"当前 SAN：{san_now}\n"
            f"1d100={roll}{symbol}{san_now}，检定{outcome}。\n\n"
            f"理智损失：{loss_text}\n"
            f"SAN：{san_now} - {loss} → {updated['san']}"
        )
        return self.make_response(f"sancheck {local_id} {loss_expr}", text, total=updated["san"])

    def check_bound_value(self, session_id, owner_id, field):
        field = self.normalize_field(field)
        sheet = self.get_sheet_by_owner(session_id, owner_id)
        value, value_text = self.get_field_value(sheet, field)
        text = f"角色ID {sheet['id']}「{sheet['name']}」的 {field} = {value_text}"
        return {"sheet": sheet, "field": field, "value": value, "text": text}

    def ability_check_for_owner(self, session_id, owner_id, field, rule_config=None):
        if rule_config is None:
            rule_config = {}
        field = self.normalize_field(field)
        sheet = self.get_sheet_by_owner(session_id, owner_id)
        target, _ = self.get_field_value(sheet, field)
        if not isinstance(target, int):
            raise SheetCommandError(f"{field} 不是可检定数值")
        if field in ["HP", "SAN", "MP", "MOV", "BUILD", "DAMAGE_BONUS"]:
            raise SheetCommandError(f"{field} 是状态值，不适合作为 ra 检定目标。")
        roll = random.randint(1, 100)
        critical_enabled = bool(rule_config.get("critical_enabled", False))
        if critical_enabled and 1 <= roll <= 5:
            result_text = "大成功"
        elif critical_enabled and 96 <= roll <= 100:
            result_text = "大失败"
        elif roll <= target:
            result_text = "通过"
        else:
            result_text = "失败"
        symbol = "<=" if roll <= target else ">"
        text = (
            f"角色ID {sheet['id']}「{sheet['name']}」进行 {field} 检定。\n"
            f"1d100={roll}{symbol}{target}，检定{result_text}。"
        )
        return {
            "rule": "sheet_check",
            "command": f"@Dice ra{field}",
            "type": "ability_check",
            "expression": f"1d100 vs {target}",
            "terms": [],
            "rolls": [roll],
            "total": roll,
            "text": text
        }

    # ==================== formatting ====================

    def format_sheet(self, sheet):
        key_skills = ["侦查", "聆听", "图书馆使用", "心理学", "闪避", "格斗", "射击", "急救", "话术", "说服", "信用评级"]
        skill_map = {item["name"]: item["value"] for item in sheet.get("skills", [])}
        skill_text = "，".join(f"{name} {skill_map[name]}" for name in key_skills if name in skill_map)
        return (
            f"ID：{sheet['id']}\n"
            f"姓名：{sheet['name']}\n"
            f"职业：{sheet['occupation'] or '—'}\n"
            f"年龄：{sheet['age']}\n"
            f"性别：{sheet['gender']}\n"
            f"STR：{sheet['STR']} DEX：{sheet['DEX']} POW：{sheet['POW']} CON：{sheet['CON']}\n"
            f"APP：{sheet['APP']} EDU：{sheet['EDU']} SIZ：{sheet['SIZ']} INT：{sheet['INS']} LUCK：{sheet['luck']}\n"
            f"HP：{sheet['hp']}/{sheet['max_hp']} SAN：{sheet['san']}/{sheet['max_san']} MP：{sheet['mp']}/{sheet['max_mp']} MOV：{sheet['MOV']}\n"
            f"DB：{sheet['damage_bonus']} 体格：{sheet['build']} 信用评级：{sheet['credit_rating']}\n"
            f"关键技能：{skill_text or '暂无'}"
        )

    def format_all_for_prompt(self, session_id):
        sheets = self.list_sheets(session_id)
        if not sheets:
            return "暂无本局角色卡。"
        lines = []
        for sheet in sheets:
            skills = sorted(sheet.get("skills", []), key=lambda item: item["value"], reverse=True)[:18]
            skill_text = "，".join(f"{item['name']} {item['value']}" for item in skills)
            lines.append(
                f"角色ID {sheet['id']}：{sheet['name']}，职业 {sheet['occupation'] or '—'}，"
                f"年龄 {sheet['age']}，性别 {sheet['gender']}，"
                f"STR {sheet['STR']}，DEX {sheet['DEX']}，POW {sheet['POW']}，CON {sheet['CON']}，"
                f"APP {sheet['APP']}，EDU {sheet['EDU']}，SIZ {sheet['SIZ']}，INT {sheet['INS']}，LUCK {sheet['luck']}，"
                f"HP {sheet['hp']}/{sheet['max_hp']}，SAN {sheet['san']}/{sheet['max_san']}，MP {sheet['mp']}/{sheet['max_mp']}，MOV {sheet['MOV']}，"
                f"DB {sheet['damage_bonus']}，体格 {sheet['build']}，信用评级 {sheet['credit_rating']}，"
                f"关键技能：{skill_text or '暂无'}，"
                f"背景：{sheet['background'] or '暂无'}，"
                f"信念：{sheet['ideology'] or '暂无'}，"
                f"重要之人：{sheet['important_people'] or '暂无'}，"
                f"特质：{sheet['traits'] or '暂无'}"
            )
        return "\n".join(lines)

    def make_response(self, command, text, total=0):
        return {"rule": "sheet", "command": command, "type": "sheet", "expression": command, "terms": [], "rolls": [], "total": total, "text": text}

    # ==================== command parser ====================


    def _angle_object_to_json(self, text):
        """
        将 @Dice card create <...> 里的尖括号对象格式转为标准 JSON。
        只在字符串外部把 < > 转换为 { }，避免误伤字符串内容。

        示例：
        <"name":"约翰","stats":<"STR":60>,"skills":[<"name":"侦查","value":55>]>
        ->
        {"name":"约翰","stats":{"STR":60},"skills":[{"name":"侦查","value":55}]}
        """
        result = []
        in_string = False
        escaped = False

        for ch in text:
            if escaped:
                result.append(ch)
                escaped = False
                continue

            if ch == "\\" and in_string:
                result.append(ch)
                escaped = True
                continue

            if ch == '"':
                result.append(ch)
                in_string = not in_string
                continue

            if not in_string and ch == "<":
                result.append("{")
            elif not in_string and ch == ">":
                result.append("}")
            else:
                result.append(ch)

        return "".join(result)

    def parse_sheet_json_command(self, json_text):
        """
        解析 @Dice card create <JSON> 后面的角色卡内容。

        当前支持的固定格式是：
        @Dice card create <"name":"约翰","age":35,"gender":"男","stats":<"STR":60,...>>

        注意：
        - 外层必须用 < >
        - 嵌套对象也用 < >
        - 数组仍然用 [ ]
        - 字符串必须使用英文双引号
        - 不支持换行代码块
        """
        json_text = (json_text or "").strip()

        if not json_text:
            raise SheetCommandError("card create 后面缺少角色卡内容。")

        if "\n" in json_text or "\r" in json_text:
            raise SheetCommandError("@Dice card create 的角色卡内容必须写在同一行，不能换行。")

        if json_text.startswith("```"):
            raise SheetCommandError("不要使用 ```json 代码块，请把角色卡内容直接写在 @Dice card create 同一行。")

        if json_text == "<JSON>" or json_text.upper() == "JSON":
            raise SheetCommandError("请把 <JSON> 替换为真实角色卡内容，而不是字面量 <JSON>。")

        if not (json_text.startswith("<") and json_text.endswith(">")):
            raise SheetCommandError(
                'card create 必须使用尖括号对象格式，例如：@Dice card create <"name":"约翰","age":35,"gender":"男","stats":<"STR":60,"DEX":55,"POW":70,"CON":50,"APP":40,"EDU":65,"SIZ":60,"INT":70>>'
            )

        json_text = self._angle_object_to_json(json_text)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise SheetCommandError(f"角色卡内容不是合法 JSON。请检查英文双引号、逗号和尖括号。错误：{str(exc)}")

        if not isinstance(data, dict):
            raise SheetCommandError("角色卡内容必须是对象格式。")

        required_top = ["name", "age", "gender", "stats"]
        for key in required_top:
            if key not in data:
                raise SheetCommandError(f"角色卡缺少必要字段：{key}")

        stats = data.get("stats")
        if not isinstance(stats, dict):
            raise SheetCommandError("stats 必须是对象格式。")

        required_stats = ["STR", "DEX", "POW", "CON", "APP", "EDU", "SIZ"]
        for key in required_stats:
            if key not in stats:
                raise SheetCommandError(f"stats 缺少必要属性：{key}")

        if "INT" not in stats and "INS" not in stats:
            raise SheetCommandError("stats 缺少必要属性：INT。")

        # 兼容系统内部字段 INS。
        if "INS" not in stats and "INT" in stats:
            stats["INS"] = stats["INT"]

        stat_keys = ["STR", "DEX", "POW", "CON", "APP", "EDU", "SIZ", "INS"]
        if "LUCK" in stats and "luck" not in data:
            data["luck"] = stats["LUCK"]

        for key in stat_keys:
            try:
                value = int(stats[key])
            except Exception:
                raise SheetCommandError(f"stats.{key} 必须是整数。")
            if value < 1 or value > 100:
                raise SheetCommandError(f"stats.{key} 必须在 1 到 100 之间。")
            stats[key] = value

        if "luck" in data:
            try:
                data["luck"] = int(data["luck"])
            except Exception:
                raise SheetCommandError("LUCK/luck 必须是整数。")
            if data["luck"] < 1 or data["luck"] > 100:
                raise SheetCommandError("LUCK/luck 必须在 1 到 100 之间。")

        data["stats"] = stats
        return data

    def handle_command(self, session_id, full_command, owner_id="user", rule_config=None):
        if rule_config is None:
            rule_config = {}
        if not session_id:
            raise SheetCommandError("角色卡指令需要 session_id")
        command = full_command.strip()
        if command.startswith("@Dice"):
            command = command.replace("@Dice", "", 1).strip()
        if not command:
            raise SheetCommandError("角色卡指令不能为空")

        # @Dice card create <JSON>
        # 用于让 AI 或用户一次性创建完整 COC 七版角色卡。
        # 示例：
        # @Dice card create {"name":"约翰","age":35,"gender":"男","occupation":"记者","stats":{"STR":60,"DEX":55,"POW":70,"CON":50,"APP":40,"EDU":65,"SIZ":60,"INS":70},"skills":[{"name":"侦查","value":60}]}
        if command.lower().startswith("card create "):
            json_text = command[len("card create"):].strip()
            data = self.parse_sheet_json_command(json_text)
            sheet = self.create_full_sheet(
                session_id=session_id,
                owner_id=owner_id,
                data=data
            )
            text = (
                "完整 COC 角色卡创建成功。\n\n"
                f"绑定身份：{owner_id}\n"
                f"{self.format_sheet(sheet)}"
            )
            return self.make_response(full_command, text, total=sheet["id"])

        parts = shlex.split(command)
        if not parts:
            raise SheetCommandError("角色卡指令不能为空")

        if len(parts) == 13 and parts[0].lower() == "card" and parts[1].lower() == "add":
            sheet = self.create_sheet(
                session_id=session_id, owner_id=owner_id, name=parts[2], age=int(parts[3]), gender=parts[4],
                str_val=int(parts[5]), dex=int(parts[6]), pow_val=int(parts[7]), con=int(parts[8]),
                app=int(parts[9]), edu=int(parts[10]), siz=int(parts[11]), ins=int(parts[12])
            )
            return self.make_response(full_command, "角色卡录入成功。\n\n" f"绑定身份：{owner_id}\n" f"{self.format_sheet(sheet)}", total=sheet["id"])

        # @Dice skill add 1 外语 英语 50
        if len(parts) == 6 and parts[0].lower() == "skill" and parts[1].lower() == "add" and parts[2].isdigit():
            local_id = int(parts[2])
            result = self.add_extended_skill(session_id, local_id, parts[3], parts[4], int(parts[5]))
            return self.make_response(full_command, f"角色ID {local_id} 已添加扩展技能 {result['name']}：{result['value']}。", total=result["value"])

        # @Dice skill custom 1 灵视 40
        if len(parts) == 5 and parts[0].lower() == "skill" and parts[1].lower() == "custom" and parts[2].isdigit():
            local_id = int(parts[2])
            result = self.add_custom_skill(session_id, local_id, parts[3], int(parts[4]))
            return self.make_response(full_command, f"角色ID {local_id} 已添加自定义技能 {result['name']}：{result['value']}。", total=result["value"])

        # @Dice skill 1 侦查 60
        if len(parts) == 4 and parts[0].lower() == "skill" and parts[1].isdigit():
            local_id = int(parts[1])
            skill_name = parts[2]
            value = int(parts[3])
            sheet = self.get_sheet(session_id, local_id)
            # 本项目中技能“初始”和“成功率”采用同一数值。
            self.upsert_skill(session_id, local_id, skill_name, value, value)
            return self.make_response(full_command, f"角色ID {local_id}「{sheet['name']}」的技能 {skill_name} 已更新为 {value}。", total=value)

        # @Dice sancheck 1 0/1d6
        if len(parts) == 3 and parts[0].lower() in ["sancheck", "sc"] and parts[1].isdigit():
            return self.san_check(session_id, int(parts[1]), parts[2])

        if len(parts) == 3 and parts[0].isdigit() and parts[1].lower() in ["hp", "san", "mp"]:
            local_id = int(parts[0])
            resource = parts[1].lower()
            delta = int(parts[2])
            result = self.update_resource(session_id, local_id, resource, delta)
            sheet = result["sheet"]
            text = (
                f"{sheet['name']} 的 {result['resource']} 已更新。\n"
                f"变化：{result['old_value']} {delta:+d} → {result['new_value']}\n\n"
                f"当前状态：\n"
                f"HP：{sheet['hp']}/{sheet['max_hp']}\n"
                f"SAN：{sheet['san']}/{sheet['max_san']}\n"
                f"MP：{sheet['mp']}/{sheet['max_mp']}\n"
                f"MOV：{sheet['MOV']}"
            )
            return self.make_response(full_command, text, total=result["new_value"])

        if len(parts) == 3 and parts[0].lower() == "check" and parts[1].isdigit():
            local_id = int(parts[1])
            result = self.check_value(session_id, local_id, parts[2])
            sheet = result["sheet"]
            text = f"角色ID {sheet['id']}「{sheet['name']}」的 {result['field']} = {result.get('value_text', result['value'])}"
            return self.make_response(full_command, text, total=0)

        if len(parts) == 2 and parts[0].lower() == "check":
            result = self.check_bound_value(session_id, owner_id, parts[1])
            return self.make_response(full_command, result["text"], total=0)

        if len(parts) == 2 and parts[0].lower() == "sheet" and parts[1].isdigit():
            sheet = self.get_sheet(session_id, int(parts[1]))
            return self.make_response(full_command, "角色卡详情：\n\n" + self.format_sheet(sheet), total=sheet["id"])

        if len(parts) == 2 and parts[0].lower() == "skills" and parts[1].isdigit():
            sheet = self.get_sheet(session_id, int(parts[1]))
            skills = sheet.get("skills", [])
            if not skills:
                return self.make_response(full_command, "该角色暂无技能。", total=0)
            text = f"{sheet['name']} 的技能表：\n" + "\n".join(f"{item['name']}：{item['value']}（基础 {item['base_value']}）" for item in skills)
            return self.make_response(full_command, text, total=len(skills))

        if len(parts) == 1 and parts[0].lower() == "cards":
            sheets = self.list_sheets(session_id)
            if not sheets:
                return self.make_response(full_command, "本局暂无角色卡。", total=0)
            text = "本局角色卡列表：\n\n" + "\n\n".join(self.format_sheet(sheet) for sheet in sheets)
            return self.make_response(full_command, text, total=len(sheets))

        if len(parts) == 1 and parts[0].lower().startswith("ra"):
            raw_field = parts[0][2:].strip()
            if not raw_field:
                return None
            return self.ability_check_for_owner(session_id, owner_id, raw_field, rule_config=rule_config)

        return None