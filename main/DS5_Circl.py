import random

class Circulation:
    def __init__(self, active_characters, mode="cycle"):
        """
        active_characters:
            前端传来的、用户已经勾选好的角色列表。
            数量必须为 1-3。
        """
        self.active_characters = []
        self.pointer = 0
        self.mode = mode
        self.conscriptio(active_characters)

    def conscriptio(self, active_characters):
        """
        接收前端已经勾选好的角色列表，并登记为当前会话启用角色。
        前端负责选择交互，后端负责最终校验。
        """
        if not isinstance(active_characters, list):
            raise ValueError("active_characters 必须是列表")
        if len(active_characters) < 1:
            raise ValueError("至少需要启用 1 个 AI 角色")
        if len(active_characters) > 3:
            raise ValueError("最多只能启用 3 个 AI 角色")
        if len(active_characters) != len(set(active_characters)):
            raise ValueError("active_characters 不能包含重复角色")

        self.active_characters = active_characters
        self.pointer = 0

    def set_mode(self, mode):
        if mode not in ["cycle", "fixed", "random"]:
            raise ValueError("mode 必须是 cycle、fixed 或 random")
        self.mode = mode

    def order(self):
        if self.mode == "fixed":
            return self.active_characters.copy()
        if self.mode == "random":
            order = self.active_characters.copy()
            random.shuffle(order)
            return order
        if self.mode == "cycle":
            return (
                self.active_characters[self.pointer:]
                + self.active_characters[:self.pointer]
            )
        return self.active_characters.copy()

    def advance(self):
        if self.mode == "cycle":
            self.pointer = (self.pointer + 1) % len(self.active_characters)

    def get_and_advance(self):
        order = self.order()
        self.advance()
        return order

    def reset(self):
        self.pointer = 0