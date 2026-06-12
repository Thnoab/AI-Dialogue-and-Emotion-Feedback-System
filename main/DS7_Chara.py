import os
import json

class Detection:
    def __init__(self, folder="characters"):
        self.folder = folder

    def list_character_cards(self):
        """
        扫描 characters 文件夹，返回所有可用人物卡的基础信息。
        给前端展示角色列表用。
        """
        characters = []
        if not os.path.exists(self.folder):
            print("人物卡文件夹不存在:", self.folder)
            return characters
        for filename in os.listdir(self.folder):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.folder, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    card = json.load(f)
                # 兼容两种写法：
                # 1. character_id
                # 2. id
                character_id = card.get("character_id") or card.get("id")
                name = card.get("name")
                if not character_id or not name:
                    print(f"跳过人物卡 {filename}: 缺少 character_id/id 或 name")
                    continue
                expressions = card.get("expressions", {})
                default_expression = card.get("default_expression", "neutral")
                # 默认立绘：优先使用 expressions[default_expression]
                default_image = expressions.get(default_expression)
                # 如果没有 neutral，就随便拿 expressions 里的第一张
                if not default_image and expressions:
                    default_image = next(iter(expressions.values()))
                # 头像：优先使用 avatar；没有就用默认立绘；再没有就空字符串
                avatar = card.get("avatar") or default_image or ""
                characters.append({
                    "character_id": character_id,
                    "name": name,
                    "file": filename,
                    "avatar": avatar,
                    "default_expression": default_expression,
                    "default_image": default_image or "",
                    "expressions": expressions
                })
            except Exception as e:
                print(f"人物卡读取失败: {filename}, 错误: {e}")
        return characters

    def elige(self, character_id):
        """
        根据 character_id 读取指定人物卡。
        默认规则：文件名必须是 character_id.json。
        """
        path = os.path.join(self.folder, f"{character_id}.json")
        if not os.path.exists(path):
            raise FileNotFoundError(f"人物卡不存在: {path}")
        with open(path, "r", encoding="utf-8") as f:
            card = json.load(f)
        # 标准化字段，避免主程序一会儿读 character_id，一会儿读 id
        card = self.normalize(card, character_id)
        self.validate(card)
        return card

    def normalize(self, card, fallback_id):
        """
        统一人物卡字段。
        支持旧字段和新字段混用。
        """
        # 统一 id
        if "character_id" not in card and "id" in card:
            card["character_id"] = card["id"]
        if "id" not in card and "character_id" in card:
            card["id"] = card["character_id"]
        if "character_id" not in card:
            card["character_id"] = fallback_id
        if "id" not in card:
            card["id"] = fallback_id
        # 统一 prompt
        # 你原本后端用的是 prompt，所以这里保证 prompt 一定存在
        if "prompt" not in card and "system_prompt" in card:
            card["prompt"] = card["system_prompt"]
        if "system_prompt" not in card and "prompt" in card:
            card["system_prompt"] = card["prompt"]
        # 表情字段默认值
        if "expressions" not in card:
            card["expressions"] = {}
        if "default_expression" not in card:
            card["default_expression"] = "neutral"
        expressions = card["expressions"]
        default_expression = card["default_expression"]
        default_image = expressions.get(default_expression)
        if not default_image and expressions:
            default_image = next(iter(expressions.values()))
        if "default_image" not in card:
            card["default_image"] = default_image or ""
        if "avatar" not in card:
            card["avatar"] = card["default_image"]
        return card

    def validate(self, card):
        """
        检查人物卡基础字段是否齐全。
        """
        required_fields = [
            "character_id",
            "name",
            "prompt",
            "personality_matrix",
            "inertia"
        ]
        for field in required_fields:
            if field not in card:
                raise ValueError(f"人物卡缺少字段: {field}")
        if not isinstance(card["character_id"], str) or not card["character_id"].strip():
            raise ValueError("character_id 必须是非空字符串")
        if not isinstance(card["name"], str) or not card["name"].strip():
            raise ValueError("name 必须是非空字符串")
        if not isinstance(card["prompt"], str) or not card["prompt"].strip():
            raise ValueError("prompt 必须是非空字符串")
        inertia = card["inertia"]
        if not isinstance(inertia, list):
            raise ValueError("inertia 必须是列表")
        if len(inertia) != 3:
            raise ValueError("inertia 必须是长度为3的向量")
        for value in inertia:
            if not isinstance(value, (int, float)):
                raise ValueError("inertia 内部必须全部是数字")
        matrix = card["personality_matrix"]
        if not isinstance(matrix, list):
            raise ValueError("personality_matrix 必须是列表")
        if len(matrix) != 3:
            raise ValueError("personality_matrix 必须是 3x3 矩阵")
        for row in matrix:
            if not isinstance(row, list) or len(row) != 3:
                raise ValueError("personality_matrix 必须是 3x3 矩阵")
            for value in row:
                if not isinstance(value, (int, float)):
                    raise ValueError("personality_matrix 内部必须全部是数字")
        expressions = card.get("expressions", {})
        if expressions and not isinstance(expressions, dict):
            raise ValueError("expressions 必须是字典")
        for key, value in expressions.items():
            if not isinstance(key, str):
                raise ValueError("expressions 的键必须是字符串")
            if not isinstance(value, str):
                raise ValueError("expressions 的路径必须是字符串")