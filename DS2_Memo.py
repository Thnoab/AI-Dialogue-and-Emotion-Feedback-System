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
        emotion TEXT)
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
            'UPDATE memory SET reply = ?, summary = ?, emotion = ? WHERE id = ?',
            (ret, abr, emt, row_id)
        )
        self.conn.commit()
        print("reply完成")

    def request(self, msg, abr1, ret, abr2, emt):
        print("request开始")
        row_id = self.communicate(msg, abr1)
        self.reply(ret, abr2, emt, row_id)
        print("request完成")

    def close(self):
        self.conn.close()

    def show_all(self):
        self.cor.execute('SELECT * FROM memory')
        return self.cor.fetchall()