import random
import re

class DiceRoller:
    def __init__(self):
        self.supported_rules = ["common", "coc", "dnd"]
        self.allowed_sides = {
            "common": {2, 3, 4, 6, 8, 10, 12, 20, 100},
            "coc": {4, 6, 10, 20, 100},
            "dnd": {4, 6, 8, 10, 12, 20, 100}
        }

    def roll(self, command, rule="common", rule_config=None):
        """
        支持：
        @Dice r1d6
        @Dice r3d6
        @Dice r1d6+2d4
        @Dice ra斗殴 60
        """
        if rule_config is None:
            rule_config = {}
        command = command.strip()
        if rule not in self.supported_rules:
            raise ValueError(f"不支持的骰子规则：{rule}")
        if command.startswith("@Dice"):
            command = command.replace("@Dice", "", 1).strip()
        if not command:
            raise ValueError("骰子指令不能为空")
        if command.startswith("ra"):
            return self.roll_check(command, rule, rule_config)
        if command.startswith("r"):
            return self.volvo(command, rule)
        raise ValueError(f"暂不支持的骰子指令：{command}")

    def roll_check(self, command, rule="common", rule_config=None):
        """
        COC式检定：
        ra斗殴 60
        ra 斗殴 60

        含义：
        投 1d100，如果结果 <= 目标值，则检定通过。
        可选规则：
        critical_enabled = True 时：
          1-5 为大成功
          96-100 为大失败
        """
        if rule_config is None:
            rule_config = {}
        if rule == "dnd":
            raise ValueError("当前 ra 检定指令暂按 COC/通用检定处理，DND 检定规则尚未实现")

        pattern = r"^ra\s*(.+?)\s+(\d{1,3})$"
        match = re.match(pattern, command)
        if not match:
            raise ValueError(
                "检定格式错误。正确示例：@Dice ra斗殴 60 或 @Dice ra 斗殴 60"
            )
        check_name = match.group(1).strip()
        target = int(match.group(2))
        if not check_name:
            raise ValueError("检定名称不能为空")
        if target < 1 or target > 100:
            raise ValueError("检定目标值必须在 1 到 100 之间")
        roll_value = random.randint(1, 100)
        critical_enabled = bool(rule_config.get("critical_enabled", False))
        # 基础通过/失败
        success = roll_value <= target
        # 大成功/大失败判定
        is_critical_success = False
        is_critical_failure = False
        if critical_enabled:
            if 1 <= roll_value <= 5:
                is_critical_success = True
            if 96 <= roll_value <= 100:
                is_critical_failure = True
        if roll_value <= target:
            operator = "<" if roll_value < target else "<="
        else:
            operator = ">"
        expression_text = f"1d100={roll_value}{operator}{target}"
        if critical_enabled and is_critical_success:
            result_text = f"{check_name}检定大成功！"
        elif critical_enabled and is_critical_failure:
            result_text = f"{check_name}检定大失败！"
        elif success:
            result_text = f"{check_name}检定通过"
        else:
            result_text = f"{check_name}检定失败"
        return {
            "rule": rule,
            "command": command,
            "type": "check",
            "check_name": check_name,
            "target": target,
            "roll": roll_value,
            "success": success,
            "critical_enabled": critical_enabled,
            "critical_success": is_critical_success,
            "critical_failure": is_critical_failure,
            "expression": expression_text,
            "terms": [],
            "rolls": [
                {
                    "dice": "1d100",
                    "rolls": [roll_value],
                    "raw_total": roll_value,
                    "sign": 1
                }
            ],
            "total": roll_value,
            "text": self.format_check_result(
                rule=rule,
                command=command,
                check_name=check_name,
                expression_text=expression_text,
                result_text=result_text
            )
        }

    def volvo(self, command, rule="common"):
        """
        解析普通骰子表达式：
        r1d6
        r3d6
        r1d6+2d4
        r1d6+2d4+3
        r2d6-1d4
        r1d20+5
        """
        original_command = command
        expression = command.strip()
        if not expression.startswith("r"):
            raise ValueError("骰子指令必须以 r 开头，例如：@Dice r1d6")
        expression = expression[1:].replace(" ", "")
        if not expression:
            raise ValueError("骰子表达式不能为空，例如：@Dice r1d6")
        if not re.fullmatch(r"[0-9dD+\-]+", expression):
            raise ValueError(
                "骰子格式错误。只允许数字、d、+、-。示例：@Dice r1d6、@Dice r1d6+2d4、@Dice r1d20+5"
            )
        tokens = re.findall(r"[+-]?[^+-]+", expression)
        if not tokens:
            raise ValueError("骰子表达式解析失败")
        terms = []
        total = 0
        all_rolls = []
        for token in tokens:
            if not token:
                continue
            sign = 1
            if token.startswith("+"):
                token_body = token[1:]
            elif token.startswith("-"):
                sign = -1
                token_body = token[1:]
            else:
                token_body = token
            if not token_body:
                raise ValueError("运算符后缺少内容")
            dice_match = re.fullmatch(r"(\d+)d(\d+)", token_body, re.IGNORECASE)
            if dice_match:
                count = int(dice_match.group(1))
                sides = int(dice_match.group(2))
                self.validate_dice(count, sides, rule)
                rolls = [random.randint(1, sides) for _ in range(count)]
                raw_total = sum(rolls)
                signed_total = sign * raw_total
                term = {
                    "type": "dice",
                    "sign": sign,
                    "count": count,
                    "sides": sides,
                    "rolls": rolls,
                    "raw_total": raw_total,
                    "signed_total": signed_total,
                    "display": self.format_dice_term_display(sign, rolls, raw_total)
                }
                terms.append(term)
                total += signed_total
                all_rolls.append({
                    "dice": f"{count}d{sides}",
                    "rolls": rolls,
                    "raw_total": raw_total,
                    "sign": sign
                })
                continue
            number_match = re.fullmatch(r"\d+", token_body)
            if number_match:
                value = int(token_body)
                signed_value = sign * value
                term = {
                    "type": "number",
                    "sign": sign,
                    "value": value,
                    "signed_total": signed_value,
                    "display": self.format_number_term_display(sign, value)
                }
                terms.append(term)
                total += signed_value
                continue
            raise ValueError(
                f"无法解析骰子项：{token}。正确示例：@Dice r1d6、@Dice r3d6、@Dice r1d6+2d4"
            )
        expression_text = self.format_expression_text(terms, total)
        return {
            "rule": rule,
            "command": original_command,
            "type": "roll",
            "expression": expression,
            "terms": terms,
            "rolls": all_rolls,
            "total": total,
            "text": self.format_result(
                rule=rule,
                command=original_command,
                expression_text=expression_text,
                total=total
            )
        }

    def validate_dice(self, count, sides, rule):
        if count < 1 or count > 100:
            raise ValueError("骰子数量必须在 1 到 100 之间")
        if sides < 2 or sides > 1000:
            raise ValueError("骰子面数必须在 2 到 1000 之间")
        allowed = self.allowed_sides.get(rule)
        if allowed and sides not in allowed:
            allowed_text = "、".join([f"d{s}" for s in sorted(allowed)])
            raise ValueError(
                f"{self.format_rule_name(rule)} 不支持 d{sides}。允许的骰子：{allowed_text}"
            )

    def format_dice_term_display(self, sign, rolls, raw_total):
        if len(rolls) == 1:
            body = str(rolls[0])
        else:
            body = "+".join(str(x) for x in rolls) + f"={raw_total}"
        if sign < 0:
            return f"-({body})"
        return body

    def format_number_term_display(self, sign, value):
        if sign < 0:
            return f"-{value}"
        return str(value)

    def format_expression_text(self, terms, total):
        if not terms:
            return f"= {total}"
        pieces = []

        for i, term in enumerate(terms):
            display = term["display"]
            sign = term["sign"]
            if i == 0:
                pieces.append(display)
                continue
            if sign >= 0:
                pieces.append(f"+{display}")
            else:
                pieces.append(display)
        left = "".join(pieces)
        return f"{left}={total}"

    def format_result(self, rule, command, expression_text, total):
        return (
            f"🎲 骰子结果\n"
            f"规则：{self.format_rule_name(rule)}\n"
            f"指令：{command}\n"
            f"算式：{expression_text}\n"
            f"结果：{total}"
        )

    def format_check_result(self, rule, command, check_name, expression_text, result_text):
        return (
            f"🎲 检定结果\n"
            f"规则：{self.format_rule_name(rule)}\n"
            f"检定：{check_name}\n"
            f"指令：{command}\n"
            f"算式：{expression_text}\n"
            f"结果：{result_text}"
        )

    def format_rule_name(self, rule):
        if rule == "coc":
            return "COC 规则"
        if rule == "dnd":
            return "DND 规则"
        return "通用骰子"