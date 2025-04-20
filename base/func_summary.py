# -*- coding: utf-8 -*-

import logging
import time
import re
from collections import deque
# from threading import Lock  # 不再需要锁，使用SQLite的事务机制
import sqlite3  # 添加sqlite3模块
import os  # 用于处理文件路径

class MessageSummary:
    """消息总结功能类 (使用SQLite持久化)
    用于记录、管理和生成聊天历史消息的总结
    """
    
    def __init__(self, max_history=200, db_path="data/message_history.db"):
        """初始化消息总结功能
        
        Args:
            max_history: 每个聊天保存的最大消息数量
            db_path: SQLite数据库文件路径
        """
        self.LOG = logging.getLogger("MessageSummary")
        self.max_history = max_history
        self.db_path = db_path
        
        # 移除旧的内存存储相关代码
        # self._msg_history = {}  # 使用字典，以群ID或用户ID为键
        # self._msg_history_lock = Lock()  # 添加锁以保证线程安全
        
        try:
            # 确保数据库文件所在的目录存在
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
                self.LOG.info(f"创建数据库目录: {db_dir}")
                
            # 连接到数据库 (如果文件不存在会自动创建)
            # check_same_thread=False 允许在不同线程中使用此连接
            # 这在多线程机器人应用中是必要的，但要注意事务管理
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.LOG.info(f"已连接到 SQLite 数据库: {self.db_path}")
            
            # 创建消息表 (如果不存在)
            # 使用 INTEGER PRIMARY KEY AUTOINCREMENT 作为 rowid 的别名，方便管理
            # timestamp_float 用于排序和限制数量
            # timestamp_str 用于显示
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp_float REAL NOT NULL,
                    timestamp_str TEXT NOT NULL
                )
            """)
            # 为 chat_id 和 timestamp_float 创建索引，提高查询效率
            self.cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_time ON messages (chat_id, timestamp_float)
            """)
            self.conn.commit() # 提交更改
            self.LOG.info("消息表已准备就绪")
            
        except sqlite3.Error as e:
            self.LOG.error(f"数据库初始化失败: {e}")
            # 如果数据库连接失败，抛出异常或进行其他错误处理
            raise ConnectionError(f"无法连接或初始化数据库: {e}") from e
        except OSError as e:
            self.LOG.error(f"创建数据库目录失败: {e}")
            raise OSError(f"无法创建数据库目录: {e}") from e
    
    def close_db(self):
        """关闭数据库连接"""
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.commit() # 确保所有更改都已保存
                self.conn.close()
                self.LOG.info("数据库连接已关闭")
            except sqlite3.Error as e:
                self.LOG.error(f"关闭数据库连接时出错: {e}")
        
    def record_message(self, chat_id, sender_name, content, timestamp=None):
        """记录单条消息到数据库
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            sender_name: 发送者名称
            content: 消息内容
            timestamp: 时间戳，默认为当前时间
        """
        try:
            # 生成浮点数时间戳用于排序
            current_time_float = time.time()
            
            # 生成或使用传入的时间字符串
            if not timestamp:
                timestamp_str = time.strftime("%H:%M", time.localtime(current_time_float))
            else:
                timestamp_str = timestamp
                
            # 插入新消息
            self.cursor.execute("""
                INSERT INTO messages (chat_id, sender, content, timestamp_float, timestamp_str)
                VALUES (?, ?, ?, ?, ?)
            """, (chat_id, sender_name, content, current_time_float, timestamp_str))
            
            # 删除超出 max_history 的旧消息
            # 使用子查询找到要保留的最新 N 条消息的 id，然后删除不在这个列表中的该 chat_id 的其他消息
            self.cursor.execute("""
                DELETE FROM messages
                WHERE chat_id = ? AND id NOT IN (
                    SELECT id
                    FROM messages
                    WHERE chat_id = ?
                    ORDER BY timestamp_float DESC
                    LIMIT ?
                )
            """, (chat_id, chat_id, self.max_history))
            
            self.conn.commit() # 提交事务
            
        except sqlite3.Error as e:
            self.LOG.error(f"记录消息到数据库时出错: {e}")
            # 可以考虑回滚事务
            try:
                self.conn.rollback()
            except:
                pass
    
    def clear_message_history(self, chat_id):
        """清除指定聊天的消息历史记录
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            bool: 是否成功清除
        """
        try:
            # 删除指定chat_id的所有消息
            self.cursor.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            rows_deleted = self.cursor.rowcount # 获取删除的行数
            self.conn.commit()
            self.LOG.info(f"为 chat_id={chat_id} 清除了 {rows_deleted} 条历史消息")
            return True # 删除0条也视为成功完成操作
            
        except sqlite3.Error as e:
            self.LOG.error(f"清除消息历史时出错 (chat_id={chat_id}): {e}")
            return False
    
    def get_message_count(self, chat_id):
        """获取指定聊天的消息数量
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            int: 消息数量
        """
        try:
            # 使用COUNT查询获取消息数量
            self.cursor.execute("SELECT COUNT(*) FROM messages WHERE chat_id = ?", (chat_id,))
            result = self.cursor.fetchone() # fetchone() 返回一个元组，例如 (5,)
            return result[0] if result else 0
            
        except sqlite3.Error as e:
            self.LOG.error(f"获取消息数量时出错 (chat_id={chat_id}): {e}")
            return 0
    
    def get_messages(self, chat_id):
        """获取指定聊天的所有消息 (按时间升序)
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            list: 消息列表，格式为 [{"sender": ..., "content": ..., "time": ...}]
        """
        messages = []
        try:
            # 查询需要的字段，按浮点时间戳升序排序，限制数量
            self.cursor.execute("""
                SELECT sender, content, timestamp_str
                FROM messages
                WHERE chat_id = ?
                ORDER BY timestamp_float ASC
                LIMIT ?
            """, (chat_id, self.max_history))
            
            rows = self.cursor.fetchall() # fetchall() 返回包含元组的列表
            
            # 将数据库行转换为期望的字典列表格式
            for row in rows:
                messages.append({
                    "sender": row[0],
                    "content": row[1],
                    "time": row[2] # 使用存储的 timestamp_str
                })
                
        except sqlite3.Error as e:
            self.LOG.error(f"获取消息列表时出错 (chat_id={chat_id}): {e}")
            # 出错时返回空列表，保持与原逻辑一致
            
        return messages
    
    def _basic_summarize(self, messages):
        """基本的消息总结逻辑，不使用AI
        
        Args:
            messages: 消息列表
            
        Returns:
            str: 消息总结
        """
        if not messages:
            return "没有可以总结的历史消息。"
            
        # 统计每个发送者的消息数量
        sender_counts = {}
        for msg in messages:
            sender = msg["sender"]
            if sender not in sender_counts:
                sender_counts[sender] = 0
            sender_counts[sender] += 1
            
        # 生成总结
        summary_lines = ["📋 最近消息总结："]
        summary_lines.append(f"总共有 {len(messages)} 条消息")
        summary_lines.append("\n发言统计：")
        
        for sender, count in sorted(sender_counts.items(), key=lambda x: x[1], reverse=True):
            summary_lines.append(f"- {sender}: {count}条消息")
            
        # 添加最近的几条消息作为示例
        recent_msgs = messages[-5:]  # 最近5条
        summary_lines.append("\n最近消息示例：")
        for msg in recent_msgs:
            summary_lines.append(f"[{msg['time']}] {msg['sender']}: {msg['content'][:30]}...")
            
        return "\n".join(summary_lines)
    
    def _ai_summarize(self, messages, chat_model, chat_id):
        """使用AI模型生成消息总结
        
        Args:
            messages: 消息列表
            chat_model: AI聊天模型对象
            chat_id: 聊天ID
            
        Returns:
            str: 消息总结
        """
        if not messages:
            return "没有可以总结的历史消息。"
            
        # 构建用于AI总结的消息格式
        formatted_msgs = []
        for msg in messages:
            formatted_msgs.append(f"[{msg['time']}] {msg['sender']}: {msg['content']}")
        
        # 构建提示词 - 更加客观、中立
        prompt = (
            "请仔细阅读并分析以下聊天记录，生成一份详细、结构清晰且抓住重点的摘要。\n\n"
            "摘要格式要求：\n"
            "1. 使用数字编号列表 (例如 1., 2., 3.) 来组织内容，每个编号代表一个独立的主要讨论主题。\n"
            "2. 在每个编号的主题下，必须清晰地包含以下三句话，且写成一段不带格式的文字，每个主题单独成段：\n"
            "    - 主题: 第一句，简要说明这个讨论的核心议题。\n"
            "    - 参与者和内容和互动: 第二句话，列出该主题的关键讨论成员 (使用 [用户名] 格式) 和他们的发言内容，以及成员之间的互动 (如表达的 感受 (如羡慕、共鸣、惊讶)、反应 (如赞同、提问、讨论))。\n"
            "    - 结果: 第三句话，总结这个主题的讨论结果。\n"
            "3. 总结需客观、精炼，直接呈现事实，不要添加额外的评论或分析。\n\n"
            "聊天记录如下：\n" + "\n".join(formatted_msgs)
        )
        
        # 使用AI模型生成总结 - 创建一个临时的聊天会话ID，避免污染正常对话上下文
        try:
            # 对于支持新会话参数的模型，使用特殊标记告知这是独立的总结请求
            if hasattr(chat_model, 'get_answer_with_context') and callable(getattr(chat_model, 'get_answer_with_context')):
                # 使用带上下文参数的方法
                summary = chat_model.get_answer_with_context(prompt, "summary_" + chat_id, clear_context=True)
            else:
                # 普通方法，使用特殊会话ID
                summary = chat_model.get_answer(prompt, "summary_" + chat_id)
                
            if not summary:
                return self._basic_summarize(messages)
                
            return summary
        except Exception as e:
            self.LOG.error(f"使用AI生成总结失败: {e}")
            return self._basic_summarize(messages)
    
    def summarize_messages(self, chat_id, chat_model=None):
        """生成消息总结
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            chat_model: AI聊天模型对象，如果为None则使用基础总结
            
        Returns:
            str: 消息总结
        """
        messages = self.get_messages(chat_id)
        if not messages:
            return "没有可以总结的历史消息。"
        
        # 根据是否提供了AI模型决定使用哪种总结方式
        if chat_model:
            return self._ai_summarize(messages, chat_model, chat_id)
        else:
            return self._basic_summarize(messages)
    
    def _extract_new_content_from_quote(self, content):
        """从引用消息中提取新内容
        
        Args:
            content: 原始消息内容
            
        Returns:
            str: 提取出的新内容，如果无法提取则返回原始内容
        """
        try:
            # 检查是否为引用消息
            if "<refermsg>" not in content:
                return content
                
            # 查找XML开始位置
            xml_start_tags = ["<msg>", "<appmsg", "<?xml", "<refermsg>"]
            xml_start_index = -1
            
            for tag in xml_start_tags:
                pos = content.find(tag)
                if pos >= 0:
                    xml_start_index = pos
                    break
                    
            # 如果找到了XML开始位置且不在开头，说明前面部分是新消息
            if xml_start_index > 0:
                new_content = content[:xml_start_index].strip()
                
                # 清理@提及 (微信@后面通常有特殊空格\u2005)
                if new_content.startswith("@") and '\u2005' in new_content:
                    mention_end = new_content.find('\u2005')
                    if mention_end != -1:
                        new_content = new_content[mention_end + 1:].strip()
                
                # 如果清理后内容不为空，返回它
                if new_content:
                    return new_content
            
            # 如果无法提取新内容，返回原始内容
            return content
            
        except Exception as e:
            self.LOG.error(f"提取引用消息新内容时出错: {e}")
            return content  # 出错时返回原始内容
    
    def process_message_from_wxmsg(self, msg, wcf, all_contacts, bot_wxid=None):
        """从微信消息对象中处理并记录消息
        
        Args:
            msg: 微信消息对象(WxMsg)
            wcf: 微信接口对象
            all_contacts: 所有联系人字典
            bot_wxid: 机器人自己的wxid，用于检测@机器人的消息
        """
        # 只记录群聊消息
        if not msg.from_group():
            return
            
        # 跳过特定类型的消息
        if msg.type != 0x01:  # 只记录文本消息
            return
            
        # 跳过自己发送的消息
        if msg.from_self():
            return
            
        # 获取群聊ID
        chat_id = msg.roomid
        
        # 获取发送者昵称
        sender_name = wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
        if not sender_name:  # 如果没有群昵称，尝试获取微信昵称
            sender_data = all_contacts.get(msg.sender)
            sender_name = sender_data if sender_data else msg.sender  # 最后使用wxid
            
        # 获取消息内容
        original_content = msg.content
        
        # 如果提供了机器人wxid，检查是否是@机器人的消息
        if bot_wxid:
            # 获取机器人在群里的昵称
            bot_name_in_group = wcf.get_alias_in_chatroom(bot_wxid, chat_id)
            if not bot_name_in_group:
                # 如果获取不到群昵称，使用通讯录中的名称或默认名称
                bot_name_in_group = all_contacts.get(bot_wxid, "泡泡")  # 默认使用"泡泡"
                
            # 检查消息中任意位置是否@机器人（含特殊空格\u2005）
            mention_pattern = f"@{bot_name_in_group}"
            if mention_pattern in original_content:
                # 消息提及了机器人，不记录
                self.LOG.debug(f"跳过包含@机器人的消息: {original_content[:30]}...")
                return
                
            # 使用正则表达式匹配更复杂的情况（考虑特殊空格）
            if re.search(rf"@{re.escape(bot_name_in_group)}(\u2005|\\s|$)", original_content):
                self.LOG.debug(f"通过正则跳过包含@机器人的消息: {original_content[:30]}...")
                return
        
        # 对于引用消息，提取新的内容部分
        if "<refermsg>" in original_content:
            content_to_record = self._extract_new_content_from_quote(original_content)
            self.LOG.debug(f"处理引用消息: 原始长度={len(original_content)}, 提取后长度={len(content_to_record)}")
        else:
            content_to_record = original_content
            
        # 记录消息
        self.record_message(chat_id, sender_name, content_to_record) 