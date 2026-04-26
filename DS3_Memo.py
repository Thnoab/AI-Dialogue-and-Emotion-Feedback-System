import sqlite3

class Memorize:
    def __init__(self):
        self.conn = sqlite3.connect('Memory_ConverContent.db', check_same_thread=False)
        self.cor = self.conn.cursor()
        self.cor.execute("""
        CREATE TABLE IF NOT EXISTS memory(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submit TEXT NOT NULL,
        reply TEXT,
        summary TEXT NOT NULL,
        motto TEXT,
        emotion TEXT,
        history TEXT)
        """)
        self.conn.commit()

    def communicate(self, msg, abr):
        print("communicate开始")
        self.cor.execute('INSERT INTO memory(submit,summary) VALUES (?,?)', (msg, abr))
        self.conn.commit()
        row_id = self.cor.lastrowid
        print("communicate完成, row_id =", row_id)
        return row_id

    def reply(self, ret, abr, emt, row_id):
        print("reply开始, row_id =", row_id)
        self.cor.execute(
            'UPDATE memory SET reply = ?, motto = ?, emotion = ? WHERE id = ?',
            (ret, abr, emt, row_id)
        )
        self.conn.commit()
        print("reply完成")

    def calcu_result(self,his,row_id):
        print("calcu_result开始, row_id =", row_id)
        self.cor.execute(
            'UPDATE memory SET history = ? WHERE id = ?',
            (his,row_id)
        )
        self.conn.commit()

    def request(self, msg, abr1, ret, abr2, emt, his):
        print("request开始")
        row_id = self.communicate(msg, abr1)
        self.reply(ret, abr2, emt, row_id)
        print("request完成")
        self.calcu_result(his,row_id)
        print("calcu_result完成")

    # 这里不是存储数据的，是打开上一个history，即先前的向量总值的，应该用在request前面的代码中的
    def quote(self):
        print('quote开始')
        self.cor.execute(
        'SELECT history FROM memory WHERE history IS NOT NULL ORDER BY id DESC LIMIT 1'
        )
        row = self.cor.fetchone()
        if row is None:
            return None
        print('quote结束')
        return row[0]
    
    # 这里是打开新存入的缩略内容，即两个abbreviation
    def rappelez(self, n):
        print('rappelez开始')
        # 参数安全检查
        if n < 0 or n > 20:
            raise ValueError("n 必须在 0 到 20 之间")
        m = 20 - n
        # ==================== 冷启动检测 ====================
        self.cor.execute('SELECT COUNT(*) FROM memory')
        count = self.cor.fetchone()[0]
        if count == 0:
            print("数据库为空（冷启动）")
            return {
                "status": "empty",
                "recent_submit": [],
                "recent_reply": [],
                "old_summary": [],
                "old_motto": []
            }
        # ===================================================
        recent_submit = []
        recent_reply = []
        old_summary = []
        old_motto = []
        # 取最近n行id
        if n > 0:
            self.cor.execute(
                'SELECT id FROM memory ORDER BY id DESC LIMIT ?',
                (n,)
            )
            recent_ids = [row[0] for row in self.cor.fetchall()]
        else:
            recent_ids = []
        # recent：取 submit + reply
        if recent_ids:
            placeholders = ','.join(['?'] * len(recent_ids))
            self.cor.execute(
                f'''
                SELECT submit, reply
                FROM memory
                WHERE id IN ({placeholders})
                ORDER BY id ASC
                ''',
                recent_ids
            )
            rows = self.cor.fetchall()
            recent_submit = [row[0] for row in rows if row[0] is not None]
            recent_reply = [row[1] for row in rows if row[1] is not None]
        # old：取 summary + motto
        if m > 0:
            if recent_ids:
                placeholders = ','.join(['?'] * len(recent_ids))
                params = list(recent_ids)
                params.append(m)
                self.cor.execute(
                    f'''
                    SELECT summary, motto
                    FROM memory
                    WHERE id NOT IN ({placeholders})
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    params
                )
            else:
                self.cor.execute(
                    '''
                    SELECT summary, motto
                    FROM memory
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    (m,)
                )
            old_rows = self.cor.fetchall()
            old_rows.reverse()
            old_summary = [row[0] for row in old_rows if row[0] is not None]
            old_motto = [row[1] for row in old_rows if row[1] is not None]
        print('rappelez结束')
        return {
            "status": "fine",
            "recent_submit": recent_submit,
            "recent_reply": recent_reply,
            "old_summary": old_summary,
            "old_motto": old_motto
        }

    def close(self):
        self.conn.close()

    def show_all(self):
        self.cor.execute('SELECT * FROM memory')
        return self.cor.fetchall()