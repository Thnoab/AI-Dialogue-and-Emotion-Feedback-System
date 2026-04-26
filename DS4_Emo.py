import numpy as np

class Calculator():
    def __init__(self,login,history,personality,inertia):
        if history is None:
            history = [0, 0, 0]
        self.emotion = np.array(login,dtype=float)
        self.previous = np.array(history,dtype=float)
        # login 代表当前获取到的向量
        # history 代表过去所获得的所有向量得出的结果
        self.personality_matrix = np.array(personality,dtype=float)
        self.inertia = np.array(inertia,dtype=float)
        # personality 代表人格特点的矩阵，3x3矩阵
        # inertia 代表每次情绪更新的惯性的三维向量（目前不考虑矩阵）

        # 检测传入内容是否合法
        if self.emotion.shape != (3,):
            raise ValueError("login 必须是长度为3的向量")
        if self.previous.shape != (3,):
            raise ValueError("history 必须是长度为3的向量")
        if self.inertia.shape != (3,):
            raise ValueError("inertia 必须是长度为3的向量")
        if self.personality_matrix.shape != (3, 3):
            raise ValueError("personality 必须是 3x3 矩阵")

    def calculate(self):
        # 人格修正（当前输入 → 角色化输入）
        modified = self.personality_matrix @ self.emotion
        # 惯性保留（旧状态衰减后留下）
        retained = self.inertia * self.previous
        # 边界压缩更新
        new_state = retained.copy()
        for i in range(len(new_state)):
            if modified[i] > 0:
                # 往正方向推，越接近1越难涨
                new_state[i] = retained[i] + modified[i] * (1 - retained[i])
            elif modified[i] < 0:
                # 往负方向推，越接近-1越难降
                new_state[i] = retained[i] + modified[i] * (1 + retained[i])
            else:
                # 没变化
                new_state[i] = retained[i]
        # 最后保险裁剪
        new_state = np.clip(new_state, -1.0, 1.0)
        return new_state
    
    def dikastis(self, old, emt, history_list):
        glee, buzz, stance = history_list
        if glee > 0.4 and buzz > 0.4:
            expression = "happy"
        elif glee > 0.4:
            expression = "shy"
        elif glee < -0.4 and stance > 0.3:
            expression = "angry"
        elif glee < -0.4 and stance < -0.3:
            expression = "sad"
        else:
            expression = "neutral"
        print("旧history =", old)
        print("本轮emotion =", emt)
        print("新history =", history_list)
        print("当前表情 =", expression)
        return expression