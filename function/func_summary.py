# -*- coding: utf-8 -*-

import logging
import time
import re
from collections import deque
# from threading import Lock  # 不再需要锁，使用SQLite的事务机制
import sqlite3  # 添加sqlite3模块
import os  # 用于处理文件路径
from function.func_xml_process import XmlProcessor  # 导入XmlProcessor

class MessageSummary:
    """消息总结功能类 (使用SQLite持久化)
    用于记录、管理和生成聊天历史消息的总结
    """
    
    def __init__(self, max_history=300, db_path="data/message_history.db"):
        """初始化消息总结功能
        
        Args:
            max_history: 每个聊天保存的最大消息数量
            db_path: SQLite数据库文件路径
        """
        self.LOG = logging.getLogger("MessageSummary")
        self.max_history = max_history
        self.db_path = db_path
        
        # 实例化XML处理器用于提取引用消息
        self.xml_processor = XmlProcessor(self.LOG)
        
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
            
        # 构建总结
        res = ["以下是近期聊天记录摘要：\n"]
        for msg in messages:
            res.append(f"[{msg['time']}]{msg['sender']}: {msg['content']}")
            
        return "\n".join(res)
    
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
            formatted_msgs.append(f"[{msg['time']}]{msg['sender']}: {msg['content']}")
        
        # 构建提示词 - 更加客观、中立
        prompt = (
            "请仔细阅读并分析以下聊天记录，生成一简要的、结构清晰且抓住重点的摘要。\n\n"
            "摘要格式要求：\n"
            "1. 使用数字编号列表 (例如 1., 2., 3.) 来组织内容，每个编号代表一个独立的主要讨论主题，不要超过3个主题。\n"
            "2. 在每个编号的主题下，写成一段不带格式的文字，每个主题单独成段并空行，需包含以下内容：\n"
            "    - 这个讨论的核心的简要描述。\n"
            "    - 该讨论的关键成员 (用括号 [用户名] 格式) 和他们的关键发言内容、成员之间的关键互动。\n"
            "    - 该讨论的讨论结果。\n"
            "3. 总结需客观、精炼、简短精悍，直接呈现最核心且精简的事实，尽量不要添加额外的评论或分析。\n"
            "4. 不要暴露出格式，不要说核心是xxx参与者是xxx结果是xxx，自然一点。\n\n"
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
    
    def process_message_from_wxmsg(self, msg, wcf, all_contacts, bot_wxid=None):
        """从微信消息对象中处理并记录与总结相关的文本消息
        使用 XmlProcessor 提取用户实际输入的新内容或卡片标题。

        Args:
            msg: 微信消息对象(WxMsg)
            wcf: 微信接口对象
            all_contacts: 所有联系人字典
            bot_wxid: 机器人自己的wxid，用于检测@机器人的消息
        """
        # 1. 基本筛选：只记录群聊中的、非自己发送的文本消息或App消息
        if not msg.from_group():
            return
        if msg.type != 0x01 and msg.type != 49:  # 只记录文本消息和App消息(包括引用消息)
            return
        if msg.from_self():
            return

        chat_id = msg.roomid

        # 2. 检查是否 @机器人 (如果提供了 bot_wxid)
        original_content = msg.content  # 获取原始content用于检测@和后续处理
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
            if re.search(rf"@{re.escape(bot_name_in_group)}(\u2005|\s|$)", original_content):
                self.LOG.debug(f"通过正则跳过包含@机器人的消息: {original_content[:30]}...")
                return

        # 3. 使用 XmlProcessor 提取消息详情
        try:
            extracted_data = self.xml_processor.extract_quoted_message(msg)
        except Exception as e:
            self.LOG.error(f"使用XmlProcessor提取消息内容时出错 (msg.id={msg.id}): {e}")
            return  # 出错时，保守起见，不记录

        # 4. 确定要记录的内容 (content_to_record)
        content_to_record = ""
        source_info = "未知来源"

        # 优先使用提取到的新内容 (来自回复或普通文本或<title>)
        if extracted_data.get("new_content", "").strip():
            content_to_record = extracted_data["new_content"].strip()
            source_info = "来自 new_content (回复/文本/标题)"
            
            # 如果是引用类型消息，添加引用标记和引用内容的简略信息
            if extracted_data.get("has_quote", False):
                quoted_sender = extracted_data.get("quoted_sender", "")
                quoted_content = extracted_data.get("quoted_content", "")
                
                # 处理被引用内容
                if quoted_content:
                    # 对较长的引用内容进行截断
                    max_quote_length = 30
                    if len(quoted_content) > max_quote_length:
                        quoted_content = quoted_content[:max_quote_length] + "..."
                    
                    # 如果被引用的是卡片，则使用标准卡片格式
                    if extracted_data.get("quoted_is_card", False):
                        quoted_card_title = extracted_data.get("quoted_card_title", "")
                        quoted_card_type = extracted_data.get("quoted_card_type", "")
                        
                        # 根据卡片类型确定内容类型
                        card_type = "卡片"
                        if "链接" in quoted_card_type or "消息" in quoted_card_type:
                            card_type = "链接"
                        elif "视频" in quoted_card_type or "音乐" in quoted_card_type:
                            card_type = "媒体"
                        elif "位置" in quoted_card_type:
                            card_type = "位置"
                        elif "图片" in quoted_card_type:
                            card_type = "图片"
                        elif "文件" in quoted_card_type:
                            card_type = "文件"
                            
                        # 整个卡片内容包裹在【】中
                        quoted_content = f"【{card_type}: {quoted_card_title}】"
                    
                    # 根据是否有被引用者信息构建引用前缀
                    if quoted_sender:
                        # 添加带引用人的引用格式，将新内容放在前面，引用内容放在后面
                        content_to_record = f"{content_to_record} 【回复 {quoted_sender}：{quoted_content}】"
                    else:
                        # 仅添加引用内容，将新内容放在前面，引用内容放在后面
                        content_to_record = f"{content_to_record} 【回复：{quoted_content}】"
        # 其次，如果新内容为空，但这是一个卡片且有标题，则使用卡片标题
        elif extracted_data.get("is_card") and extracted_data.get("card_title", "").strip():
            # 卡片消息使用固定格式，包含标题和描述
            card_title = extracted_data.get("card_title", "").strip()
            card_description = extracted_data.get("card_description", "").strip()
            card_type = extracted_data.get("card_type", "")
            card_source = extracted_data.get("card_appname") or extracted_data.get("card_sourcedisplayname", "")
            
            # 构建格式化的卡片内容，包含标题和描述
            # 根据卡片类型进行特殊处理
            if "链接" in card_type or "消息" in card_type:
                content_type = "链接"
            elif "视频" in card_type or "音乐" in card_type:
                content_type = "媒体"
            elif "位置" in card_type:
                content_type = "位置"
            elif "图片" in card_type:
                content_type = "图片"
            elif "文件" in card_type:
                content_type = "文件"
            else:
                content_type = "卡片"
                
            # 构建完整卡片内容
            card_content = f"{content_type}: {card_title}"
            
            # 添加描述内容（如果有）
            if card_description:
                # 对较长的描述进行截断
                max_desc_length = 50
                if len(card_description) > max_desc_length:
                    card_description = card_description[:max_desc_length] + "..."
                card_content += f" - {card_description}"
                
            # 添加来源信息（如果有）
            if card_source:
                card_content += f" (来自:{card_source})"
                
            # 将整个卡片内容包裹在【】中
            content_to_record = f"【{card_content}】"
                
            source_info = "来自 卡片(标题+描述)"
        # 普通文本消息的保底处理
        elif msg.type == 0x01 and not ("<" in original_content and ">" in original_content):
            content_to_record = original_content.strip()
            source_info = "来自 纯文本消息"

        # 5. 如果最终没有提取到有效内容，则不记录
        if not content_to_record:
            self.LOG.debug(f"XmlProcessor未能提取到有效文本内容，跳过记录 (msg.id={msg.id}) - Quote: {extracted_data.get('has_quote', False)}, IsCard: {extracted_data.get('is_card', False)}")
            return

        # 6. 获取发送者昵称
        sender_name = wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
        if not sender_name:  # 如果没有群昵称，尝试获取微信昵称
            sender_data = all_contacts.get(msg.sender)
            sender_name = sender_data if sender_data else msg.sender  # 最后使用wxid

        # 获取当前时间(只用于记录，不再打印)
        current_time_str = time.strftime("%H:%M", time.localtime())

        # 8. 记录提取到的有效内容
        self.LOG.debug(f"记录消息 (来源: {source_info}): '[{current_time_str}]{sender_name}: {content_to_record}' (来自 msg.id={msg.id})")
        self.record_message(chat_id, sender_name, content_to_record, current_time_str) 