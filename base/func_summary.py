# -*- coding: utf-8 -*-

import logging
import time
import re
from collections import deque
from threading import Lock

class MessageSummary:
    """消息总结功能类
    用于记录、管理和生成聊天历史消息的总结
    """
    
    def __init__(self, max_history=200):
        """初始化消息总结功能
        
        Args:
            max_history: 每个聊天保存的最大消息数量
        """
        self.LOG = logging.getLogger("MessageSummary")
        self._msg_history = {}  # 使用字典，以群ID或用户ID为键
        self._msg_history_lock = Lock()  # 添加锁以保证线程安全
        self.max_history = max_history
        
    def record_message(self, chat_id, sender_name, content, timestamp=None):
        """记录单条消息到历史记录
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            sender_name: 发送者名称
            content: 消息内容
            timestamp: 时间戳，默认为当前时间
        """
        if not timestamp:
            timestamp = time.strftime("%H:%M", time.localtime())
            
        with self._msg_history_lock:
            # 如果该聊天没有历史记录，创建一个新的队列
            if chat_id not in self._msg_history:
                self._msg_history[chat_id] = deque(maxlen=self.max_history)
                
            # 记录消息，包含发送者昵称和内容
            self._msg_history[chat_id].append({
                "sender": sender_name,
                "content": content,
                "time": timestamp
            })
    
    def clear_message_history(self, chat_id):
        """清除指定聊天的消息历史记录
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            bool: 是否成功清除
        """
        with self._msg_history_lock:
            if chat_id in self._msg_history:
                self._msg_history[chat_id].clear()
                return True
            return False
    
    def get_message_count(self, chat_id):
        """获取指定聊天的消息数量
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            int: 消息数量
        """
        with self._msg_history_lock:
            if chat_id in self._msg_history:
                return len(self._msg_history[chat_id])
            return 0
    
    def get_messages(self, chat_id):
        """获取指定聊天的所有消息
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            list: 消息列表的副本
        """
        with self._msg_history_lock:
            if chat_id in self._msg_history:
                return list(self._msg_history[chat_id])
            return []
    
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
            "下面是一组聊天消息记录。请提供一个客观的总结，包括：\n"
            "- 讨论的主要话题\n"
            "- 关键信息和要点\n\n"
            "请直接给出总结内容，不要添加额外的评论或人格色彩。\n\n"
            "消息记录:\n" + "\n".join(formatted_msgs)
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
                
            return "📋 消息总结：\n\n" + summary
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