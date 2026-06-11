import sqlite3
import shlex
import random

class SheetCommandError(ValueError):
    pass

class TrpgSheetStore:
    def __init__(self, db_path="TRPG_CharacterSheet.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cor = self.conn.cursor()
        self.cor.execute("""
        CREATE TABLE IF NOT EXISTS trpg_character_sheet(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            local_id INTEGER NOT NULL,
            owner_id TEXT DEFAULT '',
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            str_val INTEGER NOT NULL,
            dex INTEGER NOT NULL,
            pow INTEGER NOT NULL,
            con INTEGER NOT NULL,
            app INTEGER NOT NULL,
            edu INTEGER NOT NULL,
            siz INTEGER NOT NULL,
            ins INTEGER NOT NULL,
            max_hp INTEGER NOT NULL,
            hp INTEGER NOT NULL,
            max_san INTEGER NOT NULL,
            san INTEGER NOT NULL,
            mov INTEGER NOT NULL,
            UNIQUE(session_id, local_id)
        )
        """)
        self.conn.commit()

    def calculate_hp(self, con, siz):
        return int((con + siz) / 10)

    def calculate_mov(self, age, str_val, dex, siz):
        if str_val < siz and dex < siz:
            mov = 7
        elif str_val > siz and dex > siz:
            mov = 9
        else:
            mov = 8
        if age >= 40:
            penalty = min((age - 30) // 10, 5)
            mov -= penalty
        return max(mov, 1)

    def next_local_id(self, session_id):
        self.cor.execute(
            """
            SELECT MAX(local_id)
            FROM trpg_character_sheet
            WHERE session_id = ?
            """,
            (session_id,)
        )
        row = self.cor.fetchone()
        if row is None or row[0] is None:
            return 1
        return int(row[0]) + 1

    def validate_stat(self, name, value):
        if not isinstance(value, int):
            raise SheetCommandError(f"{name} 必须是整数")
        if value < 1 or value > 100:
            raise SheetCommandError(f"{name} 必须在 1 到 100 之间")

    def create_sheet(self, session_id, owner_id, name, age, gender, str_val, dex, pow_val, con, app, edu, siz, ins):
        if not session_id:
            raise SheetCommandError("缺少 session_id，无法录入本局角色卡")
        if not name:
            raise SheetCommandError("角色名不能为空")
        if age < 1:
            raise SheetCommandError("年龄必须大于 0")
        stats = {
            "STR": str_val,
            "DEX": dex,
            "POW": pow_val,
            "CON": con,
            "APP": app,
            "EDU": edu,
            "SIZ": siz,
            "INS": ins
        }
        for stat_name, stat_value in stats.items():
            self.validate_stat(stat_name, stat_value)
        local_id = self.next_local_id(session_id)
        max_hp = self.calculate_hp(con, siz)
        max_san = pow_val
        mov = self.calculate_mov(age, str_val, dex, siz)
        self.cor.execute(
            """
            INSERT INTO trpg_character_sheet(
                session_id, local_id, owner_id,
                name, age, gender,
                str_val, dex, pow, con, app, edu, siz, ins,
                max_hp, hp, max_san, san, mov
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id, local_id, owner_id,
                name, age, gender,
                str_val, dex, pow_val, con, app, edu, siz, ins,
                max_hp, max_hp, max_san, max_san, mov
            )
        )
        self.conn.commit()
        return self.get_sheet(session_id, local_id)

    def get_sheet(self, session_id, local_id):
        self.cor.execute(
            """
            SELECT
                local_id, owner_id, name, age, gender,
                str_val, dex, pow, con, app, edu, siz, ins,
                max_hp, hp, max_san, san, mov
            FROM trpg_character_sheet
            WHERE session_id = ?
            AND local_id = ?
            """,
            (session_id, local_id)
        )
        row = self.cor.fetchone()
        if row is None:
            raise SheetCommandError(f"没有找到角色ID：{local_id}")
        return {
            "id": row[0],
            "owner_id": row[1],
            "name": row[2],
            "age": row[3],
            "gender": row[4],
            "STR": row[5],
            "DEX": row[6],
            "POW": row[7],
            "CON": row[8],
            "APP": row[9],
            "EDU": row[10],
            "SIZ": row[11],
            "INS": row[12],
            "max_hp": row[13],
            "hp": row[14],
            "max_san": row[15],
            "san": row[16],
            "MOV": row[17]
        }
    
    def get_sheet_by_owner(self, session_id, owner_id):
        """
        根据 session_id + owner_id 找到当前 PL/AI 绑定的角色卡。
        一个 owner 在一局里默认绑定一张角色卡。
        如果同一 owner 多次创建角色卡，默认取最新的一张。
        """
        self.cor.execute(
            """
            SELECT local_id
            FROM trpg_character_sheet
            WHERE session_id = ?
            AND owner_id = ?
            ORDER BY local_id DESC
            LIMIT 1
            """,
            (session_id, owner_id)
        )
        row = self.cor.fetchone()
        if row is None:
            raise SheetCommandError(f"当前身份尚未绑定角色卡：{owner_id}")
        return self.get_sheet(session_id, row[0])
    
    def list_sheets(self, session_id):
        self.cor.execute(
            """
            SELECT local_id
            FROM trpg_character_sheet
            WHERE session_id = ?
            ORDER BY local_id ASC
            """,
            (session_id,)
        )
        ids = [row[0] for row in self.cor.fetchall()]
        return [self.get_sheet(session_id, local_id) for local_id in ids]

    def update_resource(self, session_id, local_id, resource, delta):
        resource = resource.lower()
        if resource not in ["hp", "san"]:
            raise SheetCommandError("只能修改 hp 或 san")
        sheet = self.get_sheet(session_id, local_id)
        if resource == "hp":
            old_value = sheet["hp"]
            max_value = sheet["max_hp"]
        else:
            old_value = sheet["san"]
            max_value = sheet["max_san"]
        new_value = old_value + delta
        new_value = max(0, min(new_value, max_value))
        self.cor.execute(
            f"""
            UPDATE trpg_character_sheet
            SET {resource} = ?
            WHERE session_id = ?
            AND local_id = ?
            """,
            (new_value, session_id, local_id)
        )
        self.conn.commit()
        updated = self.get_sheet(session_id, local_id)
        return {
            "sheet": updated,
            "resource": resource.upper(),
            "old_value": old_value,
            "new_value": new_value,
            "delta": delta
        }

    def check_value(self, session_id, local_id, field):
        field = self.normalize_field(field)
        sheet = self.get_sheet(session_id, local_id)
        field_map = {
            "STR": "STR",
            "DEX": "DEX",
            "POW": "POW",
            "CON": "CON",
            "APP": "APP",
            "EDU": "EDU",
            "SIZ": "SIZ",
            "INS": "INS",
            "HP": "hp",
            "SAN": "san",
            "MOV": "MOV",
            "AGE": "age",
            "NAME": "name",
            "GENDER": "gender"
        }
        if field not in field_map:
            raise SheetCommandError(f"不支持查询字段：{field}")
        key = field_map[field]
        value = sheet[key]
        if field == "HP":
            value_text = f"{sheet['hp']}/{sheet['max_hp']}"
        elif field == "SAN":
            value_text = f"{sheet['san']}/{sheet['max_san']}"
        else:
            value_text = str(value)
        return {
            "sheet": sheet,
            "field": field,
            "value": value,
            "value_text": value_text
        }
    
    def normalize_field(self, field):
        """
        把中文属性名 / 英文简称统一成内部字段。
        """
        field = field.strip().upper()
        field_map = {
            "力量": "STR",
            "STR": "STR",
            "敏捷": "DEX",
            "DEX": "DEX",
            "意志": "POW",
            "POW": "POW",
            "体质": "CON",
            "CON": "CON",
            "外貌": "APP",
            "APP": "APP",
            "教育": "EDU",
            "EDU": "EDU",
            "体型": "SIZ",
            "SIZ": "SIZ",
            "智力": "INS",
            "INS": "INS",
            "INT": "INS",
            "血量": "HP",
            "HP": "HP",
            "理智": "SAN",
            "SAN": "SAN",
            "移动力": "MOV",
            "MOV": "MOV"
        }
        if field not in field_map:
            raise SheetCommandError(f"不支持的属性或检定字段：{field}")
        return field_map[field]
    
    def ability_check_for_owner(self, session_id, owner_id, field, rule_config=None):
        """
        根据当前 owner_id 绑定的角色卡，直接进行 d100 检定。
        支持：
        @Dice ra力量
        @Dice raSTR
        @Dice ra敏捷
        @Dice raDEX
        """
        if rule_config is None:
            rule_config = {}
        field = self.normalize_field(field)
        # HP / SAN / MOV 是状态查询，不建议作为检定目标
        if field in ["HP", "SAN", "MOV"]:
            result = self.check_bound_value(session_id, owner_id, field)
            return self.make_response(
                command=f"@Dice ra{field}",
                text=result["text"],
                total=0
            )
        sheet = self.get_sheet_by_owner(session_id, owner_id)
        target = sheet[field]
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
    
    def check_bound_value(self, session_id, owner_id, field):
        """
        查询当前 owner_id 绑定角色卡的属性或状态。
        """
        field = self.normalize_field(field)
        sheet = self.get_sheet_by_owner(session_id, owner_id)
        field_map = {
            "STR": "STR",
            "DEX": "DEX",
            "POW": "POW",
            "CON": "CON",
            "APP": "APP",
            "EDU": "EDU",
            "SIZ": "SIZ",
            "INS": "INS",
            "HP": "hp",
            "SAN": "san",
            "MOV": "MOV"
        }
        key = field_map[field]
        value = sheet[key]
        if field == "HP":
            value_text = f"{sheet['hp']}/{sheet['max_hp']}"
        elif field == "SAN":
            value_text = f"{sheet['san']}/{sheet['max_san']}"
        else:
            value_text = str(value)
        text = f"角色ID {sheet['id']}「{sheet['name']}」的 {field} = {value_text}"
        return {
            "sheet": sheet,
            "field": field,
            "value": value,
            "text": text
        }

    def delete_session(self, session_id):
        self.cor.execute(
            """
            DELETE FROM trpg_character_sheet
            WHERE session_id = ?
            """,
            (session_id,)
        )
        deleted_rows = self.cor.rowcount
        self.conn.commit()
        return deleted_rows

    def format_sheet(self, sheet):
        return (
            f"ID：{sheet['id']}\n"
            f"姓名：{sheet['name']}\n"
            f"年龄：{sheet['age']}\n"
            f"性别：{sheet['gender']}\n"
            f"STR：{sheet['STR']}\n"
            f"DEX：{sheet['DEX']}\n"
            f"POW：{sheet['POW']}\n"
            f"CON：{sheet['CON']}\n"
            f"APP：{sheet['APP']}\n"
            f"EDU：{sheet['EDU']}\n"
            f"SIZ：{sheet['SIZ']}\n"
            f"INS：{sheet['INS']}\n"
            f"HP：{sheet['hp']}/{sheet['max_hp']}\n"
            f"SAN：{sheet['san']}/{sheet['max_san']}\n"
            f"MOV：{sheet['MOV']}"
        )

    def format_all_for_prompt(self, session_id):
        sheets = self.list_sheets(session_id)
        if not sheets:
            return "暂无本局角色卡。"
        lines = []
        for sheet in sheets:
            lines.append(
                f"角色ID {sheet['id']}：{sheet['name']}，"
                f"年龄 {sheet['age']}，性别 {sheet['gender']}，"
                f"STR {sheet['STR']}，DEX {sheet['DEX']}，POW {sheet['POW']}，"
                f"CON {sheet['CON']}，APP {sheet['APP']}，EDU {sheet['EDU']}，"
                f"SIZ {sheet['SIZ']}，INS {sheet['INS']}，"
                f"HP {sheet['hp']}/{sheet['max_hp']}，"
                f"SAN {sheet['san']}/{sheet['max_san']}，MOV {sheet['MOV']}"
            )
        return "\n".join(lines)

    def make_response(self, command, text, total=0):
        return {
            "rule": "sheet",
            "command": command,
            "type": "sheet",
            "expression": command,
            "terms": [],
            "rolls": [],
            "total": total,
            "text": text
        }

    def handle_command(self, session_id, full_command, owner_id="user", rule_config=None):
        """
        支持：
        @Dice card add 约翰 35 男 60 55 70 50 40 65 60 70
        @Dice 1 hp -3
        @Dice 2 san -5
        @Dice check 1 STR
        @Dice sheet 1
        @Dice cards
        """
        if rule_config is None:
            rule_config = {}
        if not session_id:
            raise SheetCommandError("角色卡指令需要 session_id")
        command = full_command.strip()
        if command.startswith("@Dice"):
            command = command.replace("@Dice", "", 1).strip()
        if not command:
            raise SheetCommandError("角色卡指令不能为空")
        parts = shlex.split(command)
        if not parts:
            raise SheetCommandError("角色卡指令不能为空")
        # @Dice card add 名字 年龄 性别 STR DEX POW CON APP EDU SIZ INS
        if len(parts) == 13 and parts[0].lower() == "card" and parts[1].lower() == "add":
            name = parts[2]
            age = int(parts[3])
            gender = parts[4]
            str_val = int(parts[5])
            dex = int(parts[6])
            pow_val = int(parts[7])
            con = int(parts[8])
            app = int(parts[9])
            edu = int(parts[10])
            siz = int(parts[11])
            ins = int(parts[12])
            sheet = self.create_sheet(
                session_id=session_id,
                owner_id=owner_id,
                name=name,
                age=age,
                gender=gender,
                str_val=str_val,
                dex=dex,
                pow_val=pow_val,
                con=con,
                app=app,
                edu=edu,
                siz=siz,
                ins=ins
            )
            text = (
                "角色卡录入成功。\n\n"
                f"绑定身份：{owner_id}\n"
                f"{self.format_sheet(sheet)}"
            )
            return self.make_response(full_command, text, total=sheet["id"])
        # @Dice 1 hp -3
        # @Dice 2 san -5
        if len(parts) == 3 and parts[0].isdigit() and parts[1].lower() in ["hp", "san"]:
            local_id = int(parts[0])
            resource = parts[1].lower()
            delta = int(parts[2])
            result = self.update_resource(
                session_id=session_id,
                local_id=local_id,
                resource=resource,
                delta=delta
            )
            sheet = result["sheet"]
            text = (
                f"{sheet['name']} 的 {result['resource']} 已更新。\n"
                f"变化：{result['old_value']} {delta:+d} → {result['new_value']}\n\n"
                f"当前状态：\n"
                f"HP：{sheet['hp']}/{sheet['max_hp']}\n"
                f"SAN：{sheet['san']}/{sheet['max_san']}\n"
                f"MOV：{sheet['MOV']}"
            )
            return self.make_response(full_command, text, total=result["new_value"])
        # @Dice check 1 STR
        if len(parts) == 3 and parts[0].lower() == "check" and parts[1].isdigit():
            local_id = int(parts[1])
            field = parts[2]
            result = self.check_value(
                session_id=session_id,
                local_id=local_id,
                field=field
            )
            sheet = result["sheet"]
            text = f"角色ID {sheet['id']}「{sheet['name']}」的 {result['field']} = {result.get('value_text', result['value'])}"
            return self.make_response(full_command, text, total=0)
        # @Dice check 力量
        # 查询当前 owner_id 绑定角色卡的属性或状态
        if len(parts) == 2 and parts[0].lower() == "check":
            raw_field = parts[1]
            try:
                result = self.check_bound_value(
                    session_id=session_id,
                    owner_id=owner_id,
                    field=raw_field
                )
            except SheetCommandError:
                raise
            return self.make_response(
                full_command,
                result["text"],
                total=0
            )
        # @Dice sheet 1
        if len(parts) == 2 and parts[0].lower() == "sheet" and parts[1].isdigit():
            local_id = int(parts[1])
            sheet = self.get_sheet(session_id, local_id)
            text = (
                "角色卡详情：\n\n"
                f"{self.format_sheet(sheet)}"
            )
            return self.make_response(full_command, text, total=sheet["id"])
        # @Dice cards
        if len(parts) == 1 and parts[0].lower() == "cards":
            sheets = self.list_sheets(session_id)
            if not sheets:
                return self.make_response(full_command, "本局暂无角色卡。", total=0)
            text = "本局角色卡列表：\n\n" + "\n\n".join(
                self.format_sheet(sheet) for sheet in sheets
            )
            return self.make_response(full_command, text, total=len(sheets))
        # @Dice ra力量 / @Dice raSTR / @Dice ra敏捷 / @Dice raDEX
        if len(parts) == 1 and parts[0].lower().startswith("ra"):
            raw_field = parts[0][2:].strip()
            if not raw_field:
                return None
            try:
                field = self.normalize_field(raw_field)
            except SheetCommandError:
                return None
            if field in ["HP", "SAN", "MOV"]:
                raise SheetCommandError("HP、SAN、MOV 是状态值，不适合作为 ra 检定目标。请使用 @Dice check 角色ID HP 或 @Dice sheet 角色ID 查询。")
            return self.ability_check_for_owner(
                session_id=session_id,
                owner_id=owner_id,
                field=field,
                rule_config=rule_config
            )
        return None