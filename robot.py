# -*- coding: utf-8 -*-

import logging
import re
import time
import xml.etree.ElementTree as ET
from queue import Empty
from threading import Thread
import os
import random
import shutil
from ai_providers.func_zhipu import ZhiPu
from image import CogView, AliyunImage, GeminiImage
from image.image_manager import ImageGenerationManager

from wcferry import Wcf, WxMsg

from ai_providers.func_bard import BardAssistant
from ai_providers.func_chatglm import ChatGLM
from ai_providers.func_ollama import Ollama
from ai_providers.func_chatgpt import ChatGPT
from ai_providers.func_deepseek import DeepSeek
from ai_providers.func_perplexity import Perplexity
from base.func_chengyu import cy
from base.func_weather import Weather
from base.func_news import News
from ai_providers.func_tigerbot import TigerBot
from ai_providers.func_xinghuo_web import XinghuoWeb
from base.func_duel import start_duel, get_rank_list, get_player_stats, change_player_name, DuelManager, attempt_sneak_attack
from base.func_summary import MessageSummary  # 导入新的MessageSummary类
from configuration import Config
from constants import ChatType
from job_mgmt import Job
from base.func_xml_process import XmlProcessor
from base.func_goblin_gift import GoblinGiftManager

__version__ = "39.2.4.0"


class Robot(Job):
    """个性化自己的机器人
    """

    def __init__(self, config: Config, wcf: Wcf, chat_type: int) -> None:
        self.wcf = wcf
        self.config = config
        self.LOG = logging.getLogger("Robot")
        self.wxid = self.wcf.get_self_wxid()
        self.allContacts = self.getAllContacts()
        self._msg_timestamps = []
        # 创建决斗管理器
        self.duel_manager = DuelManager(self.sendDuelMsg)
        
        # 初始化消息总结功能
        self.message_summary = MessageSummary(max_history=200)
        
        # 初始化XML处理器
        self.xml_processor = XmlProcessor(self.LOG)
        
        # 初始化所有可能需要的AI模型实例
        self.chat_models = {}
        self.LOG.info("开始初始化各种AI模型...")
        
        # 初始化TigerBot
        if TigerBot.value_check(self.config.TIGERBOT):
            self.chat_models[ChatType.TIGER_BOT.value] = TigerBot(self.config.TIGERBOT)
            self.LOG.info(f"已加载 TigerBot 模型")
            
        # 初始化ChatGPT
        if ChatGPT.value_check(self.config.CHATGPT):
            self.chat_models[ChatType.CHATGPT.value] = ChatGPT(self.config.CHATGPT)
            self.LOG.info(f"已加载 ChatGPT 模型")
            
        # 初始化讯飞星火
        if XinghuoWeb.value_check(self.config.XINGHUO_WEB):
            self.chat_models[ChatType.XINGHUO_WEB.value] = XinghuoWeb(self.config.XINGHUO_WEB)
            self.LOG.info(f"已加载 讯飞星火 模型")
            
        # 初始化ChatGLM
        if ChatGLM.value_check(self.config.CHATGLM):
            try:
                # 检查key是否有实际内容而不只是存在
                if self.config.CHATGLM.get('key') and self.config.CHATGLM.get('key').strip():
                    self.chat_models[ChatType.CHATGLM.value] = ChatGLM(self.config.CHATGLM)
                    self.LOG.info(f"已加载 ChatGLM 模型")
                else:
                    self.LOG.warning("ChatGLM 配置中缺少有效的API密钥，跳过初始化")
            except Exception as e:
                self.LOG.error(f"初始化 ChatGLM 模型时出错: {str(e)}")
            
        # 初始化BardAssistant
        if BardAssistant.value_check(self.config.BardAssistant):
            self.chat_models[ChatType.BardAssistant.value] = BardAssistant(self.config.BardAssistant)
            self.LOG.info(f"已加载 BardAssistant 模型")
            
        # 初始化ZhiPu
        if ZhiPu.value_check(self.config.ZhiPu):
            self.chat_models[ChatType.ZhiPu.value] = ZhiPu(self.config.ZhiPu)
            self.LOG.info(f"已加载 智谱 模型")
            
        # 初始化Ollama
        if Ollama.value_check(self.config.OLLAMA):
            self.chat_models[ChatType.OLLAMA.value] = Ollama(self.config.OLLAMA)
            self.LOG.info(f"已加载 Ollama 模型")
            
        # 初始化DeepSeek
        if DeepSeek.value_check(self.config.DEEPSEEK):
            self.chat_models[ChatType.DEEPSEEK.value] = DeepSeek(self.config.DEEPSEEK)
            self.LOG.info(f"已加载 DeepSeek 模型")
            
        # 初始化Perplexity
        if Perplexity.value_check(self.config.PERPLEXITY):
            self.chat_models[ChatType.PERPLEXITY.value] = Perplexity(self.config.PERPLEXITY)
            self.perplexity = self.chat_models[ChatType.PERPLEXITY.value]  # 单独保存一个引用用于特殊处理
            self.LOG.info(f"已加载 Perplexity 模型")
            
        # 根据chat_type参数选择默认模型
        if chat_type > 0 and chat_type in self.chat_models:
            self.chat = self.chat_models[chat_type]
            self.default_model_id = chat_type
        else:
            # 如果没有指定chat_type或指定的模型不可用，尝试使用配置文件中指定的默认模型
            self.default_model_id = self.config.GROUP_MODELS.get('default', 0)
            if self.default_model_id in self.chat_models:
                self.chat = self.chat_models[self.default_model_id]
            elif self.chat_models:  # 如果有任何可用模型，使用第一个
                self.default_model_id = list(self.chat_models.keys())[0]
                self.chat = self.chat_models[self.default_model_id]
            else:
                self.LOG.warning("未配置任何可用的模型")
                self.chat = None
                self.default_model_id = 0

        self.LOG.info(f"默认模型: {self.chat}，模型ID: {self.default_model_id}")
        
        # 显示群组-模型映射信息
        if hasattr(self.config, 'GROUP_MODELS'):
            # 显示群聊映射信息
            if self.config.GROUP_MODELS.get('mapping'):
                self.LOG.info("群聊-模型映射配置:")
                for mapping in self.config.GROUP_MODELS.get('mapping', []):
                    room_id = mapping.get('room_id', '')
                    model_id = mapping.get('model', 0)
                    if room_id and model_id in self.chat_models:
                        model_name = self.chat_models[model_id].__class__.__name__
                        self.LOG.info(f"  群聊 {room_id} -> 模型 {model_name}(ID:{model_id})")
                    elif room_id:
                        self.LOG.warning(f"  群聊 {room_id} 配置的模型ID {model_id} 不可用")
            
            # 显示私聊映射信息
            if self.config.GROUP_MODELS.get('private_mapping'):
                self.LOG.info("私聊-模型映射配置:")
                for mapping in self.config.GROUP_MODELS.get('private_mapping', []):
                    wxid = mapping.get('wxid', '')
                    model_id = mapping.get('model', 0)
                    if wxid and model_id in self.chat_models:
                        model_name = self.chat_models[model_id].__class__.__name__
                        contact_name = self.allContacts.get(wxid, wxid)
                        self.LOG.info(f"  私聊用户 {contact_name}({wxid}) -> 模型 {model_name}(ID:{model_id})")
                    elif wxid:
                        self.LOG.warning(f"  私聊用户 {wxid} 配置的模型ID {model_id} 不可用")
        
        # 初始化图像生成管理器
        self.image_manager = ImageGenerationManager(self.config, self.wcf, self.LOG, self.sendTextMsg)
                
        # 初始化古灵阁妖精馈赠管理器
        self.goblin_gift_manager = GoblinGiftManager(self.config, self.wcf, self.LOG, self.sendTextMsg)
        
    @staticmethod
    def value_check(args: dict) -> bool:
        if args:
            return all(value is not None for key, value in args.items() if key != 'proxy')
        return False

    def get_bot_help_info(self) -> str:
        """获取机器人的帮助信息，包含所有可用指令"""
        help_text = [
            "🤖 泡泡的指令列表 🤖",
            "",
            "【决斗 & 偷袭】",
            "▶️ 决斗@XX - 向某人发起决斗",
            "▶️ 偷袭@XX / 偷分@XX - 尝试偷取积分",
            "▶️ 决斗排行/排行榜",
            "▶️ 我的战绩/决斗战绩",
            "▶️ 我的装备/查看装备",
            "▶️ 改名 旧名 新名 - 更新昵称",
            "",
            "",
            "【成语】",
            "▶️ #成语 - 接龙",
            "▶️ ?成语 - 查询成语释义",
            "",
            "【群聊工具】",
            "▶️ summary/总结",
            "▶️ clearmessages/清除历史",
            "▶️ reset/重置",
            "",
            "【其他】",
            "▶️ info/帮助/指令",
            "▶️ 直接@泡泡 - 进行对话"
        ]
        return "\n".join(help_text)

    def toAt(self, msg: WxMsg) -> bool:
        """处理被 @ 消息
        :param msg: 微信消息结构
        :return: 处理状态，`True` 成功，`False` 失败
        """
        # CogView触发词
        cogview_trigger = self.config.COGVIEW.get('trigger_keyword', '牛智谱') if hasattr(self.config, 'COGVIEW') else '牛智谱'
        # 阿里文生图触发词
        aliyun_trigger = self.config.ALIYUN_IMAGE.get('trigger_keyword', '牛阿里') if hasattr(self.config, 'ALIYUN_IMAGE') else '牛阿里'
        # 谷歌AI画图触发词
        gemini_trigger = self.config.GEMINI_IMAGE.get('trigger_keyword', '牛谷歌') if hasattr(self.config, 'GEMINI_IMAGE') else '牛谷歌'
        # Perplexity触发词
        perplexity_trigger = self.config.PERPLEXITY.get('trigger_keyword', 'ask') if hasattr(self.config, 'PERPLEXITY') else 'ask'
        
        # 处理引用消息的特殊情况，提取用户实际消息内容
        if msg.type == 49 and ("<title>" in msg.content or "<appmsg" in msg.content):
            # 引用消息情况下，用户实际消息在title标签中
            title_match = re.search(r'<title>(.*?)</title>', msg.content)
            if title_match:
                # 提取title中的内容，并删除可能的@机器人前缀
                content = title_match.group(1)
                content = re.sub(r'^@[\w\s]+\s+', '', content).strip()
                self.LOG.info(f"从title提取用户消息: {content}")
            else:
                content = ""
        else:
            # 普通消息情况
            content = re.sub(r"@.*?[\u2005|\s]", "", msg.content).replace(" ", "")
        
        # --- 添加：处理@机器人时的"新闻"关键词 ---
        if content.lower() == "新闻":
            self.LOG.info(f"检测到 @机器人 新闻 请求: {msg.content}")
            return self.handleNewsRequest(msg) # 直接调用新闻处理并返回结果
        # --- 添加结束 ---
        
        # 处理重置对话记忆命令
        if content.lower() == "reset" or content == "重置" or content == "重置记忆":
            self.LOG.info(f"收到重置对话记忆请求: {msg.content}")
            chat_id = msg.roomid if msg.from_group() else msg.sender
            
            # 重置聊天记忆
            result = self._reset_chat_memory(chat_id)
            
            if msg.from_group():
                self.sendTextMsg(result, msg.roomid, msg.sender)
                self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            else:
                self.sendTextMsg(result, msg.sender)
                
            return True
        
        # 处理消息总结命令
        if content.lower() == "summary" or content == "总结":
            self.LOG.info(f"收到消息总结请求: {msg.content}")
            
            # 只处理群聊中的总结请求
            if not msg.from_group():
                self.sendTextMsg("⚠️ 消息总结功能仅支持群聊", msg.sender)
                return True
                
            # 获取群聊ID
            chat_id = msg.roomid
            
            # 使用MessageSummary生成总结
            summary = self.message_summary.summarize_messages(chat_id, self.chat)
            
            # 发送总结
            self.sendTextMsg(summary, msg.roomid, msg.sender)
            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            return True
        
        # 处理清除历史命令
        if content.lower() == "clearmessages" or content == "清除消息" or content == "清除历史":
            self.LOG.info(f"收到清除消息历史请求: {msg.content}")
            
            # 只处理群聊中的清除历史请求
            if not msg.from_group():
                self.sendTextMsg("⚠️ 消息历史管理功能仅支持群聊", msg.sender)
                return True
                
            # 获取群聊ID
            chat_id = msg.roomid
            
            # 清除历史
            if self.message_summary.clear_message_history(chat_id):
                self.sendTextMsg("✅ 已清除本群的消息历史记录", msg.roomid, msg.sender)
                self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            else:
                self.sendTextMsg("⚠️ 本群没有消息历史记录", msg.roomid, msg.sender)
                self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                    
            return True
        
        # 改名命令处理
        change_name_match = re.search(r"改名\s+([^\s]+)\s+([^\s]+)", msg.content)
        if change_name_match:
            self.LOG.info(f"检测到改名请求: {msg.content}")
            # 只支持"改名 旧名 新名"格式
            old_name = change_name_match.group(1)
            new_name = change_name_match.group(2)
            self.LOG.info(f"匹配到改名格式: 旧名={old_name}, 新名={new_name}")
            
            # 确保有新名字和旧名字
            if old_name and new_name:
                from base.func_duel import change_player_name
                result = change_player_name(old_name, new_name, msg.roomid)
                self.sendTextMsg(result, msg.roomid, msg.sender)
                self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                return True
        
        # --- 新增：偷袭功能处理 ---
        sneak_attack_match = re.search(r"(?:偷袭|偷分).*?@([^\s@]+)", msg.content)
        if sneak_attack_match:
            target_name = sneak_attack_match.group(1).strip()
            self.LOG.info(f"检测到偷袭请求: 目标={target_name}")

            if not msg.from_group():
                self.sendTextMsg("❌ 偷袭功能只支持群聊哦。", msg.sender)
                return True

            # 获取攻击者昵称
            attacker_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)

            # 调用偷袭逻辑
            result_message = attempt_sneak_attack(attacker_name, target_name, msg.roomid)

            # 发送结果
            self.sendTextMsg(result_message, msg.roomid, msg.sender)
            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            return True
        # --- 偷袭功能处理结束 ---

        # 决斗功能处理 - 优化正则匹配
        duel_match = re.search(r"决斗.*?(?:@|[与和]).*?([^\s@]+)", content)
        #self.LOG.info(f"决斗检测 - 原始内容: {msg.content}, 处理后内容: {content}, 匹配结果: {duel_match}")
        if duel_match:
            opponent_name = duel_match.group(1)
            self.LOG.info(f"决斗对手名称: {opponent_name}")
            # 寻找群内对应的成员
            room_members = self.wcf.get_chatroom_members(msg.roomid)
            opponent_wxid = None
            for member_wxid, member_name in room_members.items():
                if opponent_name in member_name:
                    opponent_wxid = member_wxid
                    break
            
            if opponent_wxid:
                # 获取挑战者昵称
                challenger_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
                
                # 检查并启动决斗线程
                if not self.duel_manager.start_duel_thread(challenger_name, opponent_name, msg.roomid, True):
                    self.sendTextMsg("⚠️ 目前有其他决斗正在进行中，请稍后再试！", msg.roomid)
                    return True
                
                return True
            else:
                self.sendTextMsg(f"❌ 没有找到名为 {opponent_name} 的群成员", msg.roomid)
                return True
        
        # 决斗排行榜查询
        if content == "决斗排行" or content == "决斗排名" or content == "排行榜":
            from base.func_duel import get_rank_list
            rank_list = get_rank_list(10, msg.roomid)  # 正确传递群组ID
            self.sendTextMsg(rank_list, msg.roomid)
            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            return
        
        # 个人战绩查询
        stats_match = re.search(r"(决斗战绩|我的战绩|战绩查询)(.*)", content)
        if stats_match:
            player_name = stats_match.group(2).strip()
            if not player_name:  # 如果没有指定名字，则查询发送者
                player_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
            
            stats = get_player_stats(player_name, msg.roomid)  # 传递群ID
            self.sendTextMsg(stats, msg.roomid)
            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            return
        
        # 查看装备功能
        if content == "我的装备" or content == "查看装备":
            player_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
            
            from base.func_duel import DuelRankSystem
            rank_system = DuelRankSystem(msg.roomid)
            player_data = rank_system.get_player_data(player_name)
            
            items = player_data["items"]
            result = [
                f"🧙‍♂️ {player_name} 的魔法装备:",
                f"🪄 老魔杖: {items['elder_wand']}次 ",
                f"💎 魔法石: {items['magic_stone']}次",
                f"🧥 隐身衣: {items['invisibility_cloak']}次 "
            ]
            
            self.sendTextMsg("\n".join(result), msg.roomid)
            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            return
        
        # 帮助信息查询
        if content.startswith("info") or content == "帮助" or content == "指令":
            help_info = self.get_bot_help_info()
            self.sendTextMsg(help_info, msg.roomid)
            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            return True
        
        # 阿里文生图处理
        if content.startswith(aliyun_trigger):
            prompt = content[len(aliyun_trigger):].strip()
            if prompt:
                result = self.image_manager.handle_image_generation('aliyun', prompt, msg.roomid, msg.sender)
                if result:
                    self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                    return True
                
        # CogView处理
        elif content.startswith(cogview_trigger):
            prompt = content[len(cogview_trigger):].strip()
            if prompt:
                result = self.image_manager.handle_image_generation('cogview', prompt, msg.roomid, msg.sender)
                if result:
                    self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                    return True
        
        # 谷歌AI画图处理
        elif content.startswith(gemini_trigger):
            prompt = content[len(gemini_trigger):].strip()
            if prompt:
                result = self.image_manager.handle_image_generation('gemini', prompt, msg.roomid or msg.sender, msg.sender if msg.roomid else None)
                if result and msg.from_group():
                    self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                return True
            else:
                self.sendTextMsg(f"请在{gemini_trigger}后面添加您想要生成的图像描述", msg.roomid or msg.sender, msg.sender if msg.roomid else None)
                return True
        
        # Perplexity处理
        elif content.startswith(perplexity_trigger):
            prompt = content[len(perplexity_trigger):].strip()
            if prompt:
                # 处理Perplexity请求
                perplexity_instance = self.get_perplexity_instance()
                if perplexity_instance:
                    chat_id = msg.roomid if msg.from_group() else msg.sender
                    result = perplexity_instance.process_message(
                        content=content,
                        chat_id=chat_id,
                        sender=msg.sender,
                        roomid=msg.roomid,
                        from_group=msg.from_group(),
                        send_text_func=self.sendTextMsg
                    )
                    if result and msg.from_group():
                        self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                    return result
                else:
                    self.sendTextMsg("Perplexity服务未配置", msg.roomid if msg.from_group() else msg.sender)
                    return True
            else:
                self.sendTextMsg(f"请在{perplexity_trigger}后面添加您的问题", msg.roomid if msg.from_group() else msg.sender)
                return True
        
        # 如果不是特殊命令，交给闲聊处理
        # 但检查是否有引用消息，让AI知道引用内容
        if "<refermsg>" in msg.content:
            self.LOG.info("检测到含引用内容的@消息，提取引用内容")
            # 引用内容的处理已整合到toChitchat方法中
            
        return self.toChitchat(msg)

    def toChengyu(self, msg: WxMsg) -> bool:
        """
        处理成语查询/接龙消息
        :param msg: 微信消息结构
        :return: 处理状态，`True` 成功，`False` 失败
        """
        status = False
        texts = re.findall(r"^([#?？])(.*)$", msg.content)
        # [('#', '天天向上')]
        if texts:
            flag = texts[0][0]
            text = texts[0][1]
            if flag == "#":  # 接龙
                if cy.isChengyu(text):
                    rsp = cy.getNext(text)
                    if rsp:
                        if msg.from_group():
                            self.sendTextMsg(rsp, msg.roomid)
                            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                        else:
                            self.sendTextMsg(rsp, msg.sender)
                        status = True
            elif flag in ["?", "？"]:  # 查词
                if cy.isChengyu(text):
                    rsp = cy.getMeaning(text)
                    if rsp:
                        if msg.from_group():
                            self.sendTextMsg(rsp, msg.roomid)
                            self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
                        else:
                            self.sendTextMsg(rsp, msg.sender)
                        status = True

        return status

    def toChitchat(self, msg: WxMsg) -> bool:
        """闲聊，接入 ChatGPT
        """
        if not self.chat:  # 没接 ChatGPT，固定回复
            rsp = "你@我干嘛？"
        else:  # 接了 ChatGPT，智能回复
            # 获取发送者昵称
            if msg.from_group():
                sender_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
            else:
                sender_name = self.allContacts.get(msg.sender, "用户")
            
            # 根据是否为群聊分别处理
            if msg.from_group():
                # 处理群聊消息
                self.LOG.info(f"处理群聊消息: 群ID={msg.roomid}, 发送者={msg.sender}, 类型={msg.type}")
                
                # 提取消息内容
                msg_data = self.xml_processor.extract_quoted_message(msg)
                
                # 如果没有从结构化提取中获取到用户消息，尝试从原始内容中提取
                if not msg_data["new_content"]:
                    # 处理类型49的消息（引用、卡片、链接等）
                    if msg.type == 49 and ("<title>" in msg.content or "<appmsg" in msg.content):
                        # 从title标签提取用户实际消息
                        title_match = re.search(r'<title>(.*?)</title>', msg.content)
                        if title_match:
                            msg_data["new_content"] = title_match.group(1).strip()
                            # 删除可能的@机器人前缀
                            msg_data["new_content"] = re.sub(r'^@[\w\s]+\s+', '', msg_data["new_content"]).strip()
                    else:
                        # 普通消息情况，去除@标记
                        msg_data["new_content"] = re.sub(r"@.*?[\u2005|\s]", "", msg.content).strip()
                
                # 格式化消息为AI可处理的文本
                q_with_info = self.xml_processor.format_message_for_ai(msg_data, sender_name)
                
                # 如果格式化后的消息为空，构造一个基本消息
                if not q_with_info:
                    current_time = time.strftime("%H:%M", time.localtime())
                    q_with_info = f"[{current_time}] {sender_name}: [空内容]"
                
            else:
                # --- 添加：处理私聊中的"新闻"关键词 ---
                if msg.content.strip() == "新闻":
                    if self.handleNewsRequest(msg):
                        return # 已处理，直接返回
                # --- 添加结束 ---
                
                # 私聊改名处理
                change_name_match = re.search(r"^改名\s+([^\s]+)\s+([^\s]+)$", msg.content)
                if change_name_match:
                    self.sendTextMsg("❌ 改名功能只支持群聊", msg.sender)
                    return

                # 使用专门的私聊消息处理函数
                msg_data = self.xml_processor.extract_private_quoted_message(msg)
                
                # 如果没有从结构化提取中获取到用户消息，尝试从原始内容中提取
                if not msg_data["new_content"] and msg.type == 0x01:
                    # 处理纯文本消息
                    msg_data["new_content"] = msg.content.strip()
                
                # 格式化消息为AI可处理的文本
                q_with_info = self.xml_processor.format_message_for_ai(msg_data, sender_name)
                
                # 如果格式化后的消息为空，构造一个基本消息
                if not q_with_info:
                    current_time = time.strftime("%H:%M", time.localtime())
                    media_type = msg_data["media_type"] if msg_data["media_type"] != "文本" else "消息"
                    q_with_info = f"[{current_time}] {sender_name} 发送了 [{media_type}]"
            
            # 记录最终发送给AI的消息内容
            self.LOG.info(f"发送给AI的消息内容: {q_with_info}")
            
            # 获取AI回复
            rsp = self.chat.get_answer(q_with_info, (msg.roomid if msg.from_group() else msg.sender))

        if rsp:
            if msg.from_group():
                self.sendTextMsg(rsp, msg.roomid, msg.sender)
                self._try_trigger_goblin_gift(msg)  # 添加：尝试触发馈赠
            else:
                self.sendTextMsg(rsp, msg.sender)

            return True
        else:
            self.LOG.error(f"无法从 AI 获得答案")
            return False

    def processMsg(self, msg: WxMsg) -> None:
        """当接收到消息的时候，会调用本方法。如果不实现本方法，则打印原始消息。
        此处可进行自定义发送的内容,如通过 msg.content 关键字自动获取当前天气信息，并发送到对应的群组@发送者
        群号：msg.roomid  微信ID：msg.sender  消息内容：msg.content
        content = "xx天气信息为："
        receivers = msg.roomid
        self.sendTextMsg(content, receivers, msg.sender)
        """
        try:
            # 使用MessageSummary记录消息
            self.message_summary.process_message_from_wxmsg(msg, self.wcf, self.allContacts, self.wxid)
            
            # 根据消息来源选择使用的AI模型
            self._select_model_for_message(msg)
            
            # 群聊消息
            if msg.from_group():
                # 检测新人加入群聊
                if msg.type == 10000:
                    # 使用正则表达式匹配邀请加入群聊的消息
                    new_member_match = re.search(r'"(.+?)"邀请"(.+?)"加入了群聊', msg.content)
                    if new_member_match:
                        inviter = new_member_match.group(1)  # 邀请人
                        new_member = new_member_match.group(2)  # 新成员
                        # 使用配置文件中的欢迎语，支持变量替换
                        welcome_msg = self.config.WELCOME_MSG.format(new_member=new_member, inviter=inviter)
                        self.sendTextMsg(welcome_msg, msg.roomid, msg.sender)
                        self.LOG.info(f"已发送欢迎消息给新成员 {new_member} 在群 {msg.roomid}")
                        return

                # 如果在群里被 @
                if msg.roomid not in self.config.GROUPS:  # 不在配置的响应的群列表里，忽略
                    return
                    
                # --- 添加：处理群聊中的"新闻"关键词 ---
                if msg.content.strip() == "新闻":
                    if self.handleNewsRequest(msg):
                        return # 已处理，直接返回
                # --- 添加结束 ---

                # 改名命令处理
                change_name_match = re.search(r"^改名\s+([^\s]+)\s+([^\s]+)$", msg.content)
                if change_name_match:
                    old_name = change_name_match.group(1)
                    new_name = change_name_match.group(2)
                    
                    from base.func_duel import change_player_name
                    result = change_player_name(old_name, new_name, msg.roomid)
                    self.sendTextMsg(result, msg.roomid)
                    return

                if msg.is_at(self.wxid):  # 被@
                    # 私聊改名处理
                    change_name_match = re.search(r"^改名\s+([^\s]+)\s+([^\s]+)$", msg.content)
                    if change_name_match:
                        self.sendTextMsg("❌ 改名功能只支持群聊", msg.sender)
                        return

                    # 决斗功能特殊处理 - 直接检测关键词
                    if "决斗" in msg.content:
                        self.LOG.info(f"群聊中检测到可能的决斗请求: {msg.content}")
                        # 尝试提取对手名称
                        duel_match = re.search(r"决斗.*?@([^\s]+)", msg.content)
                        if duel_match:
                            opponent_name = duel_match.group(1)
                            self.LOG.info(f"直接匹配到的决斗对手名称: {opponent_name}")
                            # 寻找群内对应的成员
                            room_members = self.wcf.get_chatroom_members(msg.roomid)
                            opponent_wxid = None
                            for member_wxid, member_name in room_members.items():
                                if opponent_name in member_name:
                                    opponent_wxid = member_wxid
                                    break
                            
                            if opponent_wxid:
                                # 获取挑战者昵称
                                challenger_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
                                
                                # 检查并启动决斗线程
                                if not self.duel_manager.start_duel_thread(challenger_name, opponent_name, msg.roomid, True):
                                    self.sendTextMsg("⚠️ 目前有其他决斗正在进行中，请稍后再试！", msg.roomid)
                                    return True
                                
                                return True
                
                    # 常规@处理
                    self.toAt(msg)

                else:  # 其他消息
                    self.toChengyu(msg)

                return  # 处理完群聊信息，后面就不需要处理了

            # 非群聊信息，按消息类型进行处理
            if msg.type == 37:  # 好友请求
                self.autoAcceptFriendRequest(msg)

            elif msg.type == 10000:  # 系统信息
                self.sayHiToNewFriend(msg)

            elif msg.type == 0x01:
                if msg.from_self():
                    if msg.content == "^更新$":
                        self.config.reload()
                        self.LOG.info("已更新")
                else:
                    # --- 添加：处理私聊中的"新闻"关键词 ---
                    if msg.content.strip() == "新闻":
                        if self.handleNewsRequest(msg):
                            return # 已处理，直接返回
                    # --- 添加结束 ---
                    
                    # 私聊改名处理
                    change_name_match = re.search(r"^改名\s+([^\s]+)\s+([^\s]+)$", msg.content)
                    if change_name_match:
                        old_name = change_name_match.group(1)
                        new_name = change_name_match.group(2)
                        
                        from base.func_duel import change_player_name
                        result = change_player_name(old_name, new_name)  # 私聊不传群ID
                        self.sendTextMsg(result, msg.sender)
                        return

                    # 决斗功能处理（私聊）
                    duel_match = re.search(r"^决斗\s*(?:@|[与和])\s*([^\s]+)$", msg.content)
                    if duel_match:
                        self.sendTextMsg("❌ 决斗功能只支持群聊", msg.sender)
                        return
                    
                    # 偷袭功能处理（私聊）
                    sneak_attack_match = re.search(r"^(?:偷袭|偷分)\s*(?:@|[与和])\s*([^\s]+)$", msg.content)
                    if sneak_attack_match:
                        self.sendTextMsg("❌ 偷袭功能只支持群聊", msg.sender)
                        return
                    
                    # 决斗排行榜查询
                    if msg.content == "决斗排行" or msg.content == "决斗排名" or msg.content == "排行榜":
                        self.sendTextMsg("❌ 决斗排行榜功能只支持群聊", msg.sender)
                        return
                    
                    # 个人战绩查询
                    stats_match = re.search(r"^(决斗战绩|我的战绩|战绩查询)(.*)$", msg.content)
                    if stats_match:
                        self.sendTextMsg("❌ 决斗战绩查询功能只支持群聊", msg.sender)
                        return
                    
                    # 查看装备功能
                    if msg.content == "我的装备" or msg.content == "查看装备":
                        player_name = self.allContacts.get(msg.sender, "未知用户")
                        
                        self.sendTextMsg("❌ 装备查看功能只支持群聊", msg.sender)
                        return
                    
                    # 帮助信息查询
                    if msg.content.startswith("info") or msg.content == "帮助" or msg.content == "指令":
                        help_info = self.get_bot_help_info()
                        self.sendTextMsg(help_info, msg.sender)
                        return
                    
                    # 阿里文生图触发词处理
                    aliyun_trigger = self.config.ALIYUN_IMAGE.get('trigger_keyword', '牛阿里') if hasattr(self.config, 'ALIYUN_IMAGE') else '牛阿里'
                    if msg.content.startswith(aliyun_trigger):
                        prompt = msg.content[len(aliyun_trigger):].strip()
                        if prompt:
                            result = self.image_manager.handle_image_generation('aliyun', prompt, msg.sender)
                            if result:
                                return
                    
                    # CogView触发词处理
                    cogview_trigger = self.config.COGVIEW.get('trigger_keyword', '牛智谱') if hasattr(self.config, 'COGVIEW') else '牛智谱'
                    if msg.content.startswith(cogview_trigger):
                        prompt = msg.content[len(cogview_trigger):].strip()
                        if prompt:
                            result = self.image_manager.handle_image_generation('cogview', prompt, msg.sender)
                            if result:
                                return
                    
                    # 谷歌AI画图触发词处理
                    gemini_trigger = self.config.GEMINI_IMAGE.get('trigger_keyword', '牛谷歌') if hasattr(self.config, 'GEMINI_IMAGE') else '牛谷歌'
                    if msg.content.startswith(gemini_trigger):
                        prompt = msg.content[len(gemini_trigger):].strip()
                        if prompt:
                            result = self.image_manager.handle_image_generation('gemini', prompt, msg.sender)
                            if result:
                                return
                    
                    # Perplexity触发词处理
                    perplexity_trigger = self.config.PERPLEXITY.get('trigger_keyword', 'ask') if hasattr(self.config, 'PERPLEXITY') else 'ask'
                    if msg.content.startswith(perplexity_trigger):
                        # 处理Perplexity请求
                        perplexity_instance = self.get_perplexity_instance()
                        if perplexity_instance:
                            chat_id = msg.roomid if msg.from_group() else msg.sender
                            if perplexity_instance.process_message(
                                content=msg.content,
                                chat_id=chat_id,
                                sender=msg.sender,
                                roomid=msg.roomid,
                                from_group=msg.from_group(),
                                send_text_func=self.sendTextMsg
                            ):
                                return True
                        else:
                            self.sendTextMsg("Perplexity服务未配置", msg.roomid if msg.from_group() else msg.sender)
                            return True

                    self.toChitchat(msg)  # 闲聊
                    
            # 新增：处理私聊引用消息
            elif msg.type == 49:  # App消息（包括引用消息、链接等）
                self.LOG.info(f"收到私聊引用/App消息 (Type 49) from {msg.sender}，转交 toChitchat 处理")
                self.toChitchat(msg)  # 直接转交给 toChitchat 处理

        except Exception as e:
            self.LOG.error(f"处理消息时发生错误: {e}")

    def enableRecvMsg(self) -> None:
        self.wcf.enable_recv_msg(self.onMsg)

    def enableReceivingMsg(self) -> None:
        def innerProcessMsg(wcf: Wcf):
            while wcf.is_receiving_msg():
                try:
                    msg = wcf.get_msg()
                    self.LOG.info(msg)
                    self.processMsg(msg)
                except Empty:
                    continue  # Empty message
                except Exception as e:
                    self.LOG.error(f"Receiving message error: {e}")

        self.wcf.enable_receiving_msg()
        Thread(target=innerProcessMsg, name="GetMessage", args=(self.wcf,), daemon=True).start()

    def sendTextMsg(self, msg: str, receiver: str, at_list: str = "") -> None:
        """ 发送消息
        :param msg: 消息字符串
        :param receiver: 接收人wxid或者群id
        :param at_list: 要@的wxid, @所有人的wxid为：notify@all
        """
        # 随机延迟0.3-1.3秒，并且一分钟内发送限制
        time.sleep(float(str(time.time()).split('.')[-1][-2:]) / 100.0 + 0.3)
        now = time.time()
        if self.config.SEND_RATE_LIMIT > 0:
            # 清除超过1分钟的记录
            self._msg_timestamps = [t for t in self._msg_timestamps if now - t < 60]
            if len(self._msg_timestamps) >= self.config.SEND_RATE_LIMIT:
                self.LOG.warning(f"发送消息过快，已达到每分钟{self.config.SEND_RATE_LIMIT}条上限。")
                return
            self._msg_timestamps.append(now)

        # msg 中需要有 @ 名单中一样数量的 @
        ats = ""
        if at_list:
            if at_list == "notify@all":  # @所有人
                ats = " @所有人"
            else:
                wxids = at_list.split(",")
                for wxid in wxids:
                    # 根据 wxid 查找群昵称
                    ats += f" @{self.wcf.get_alias_in_chatroom(wxid, receiver)}"

        # {msg}{ats} 表示要发送的消息内容后面紧跟@，例如 北京天气情况为：xxx @张三
        if ats == "":
            self.LOG.info(f"To {receiver}: {msg}")
            self.wcf.send_text(f"{msg}", receiver, at_list)
        else:
            self.LOG.info(f"To {receiver}: {ats}\r{msg}")
            self.wcf.send_text(f"{ats}\n\n{msg}", receiver, at_list)

    def getAllContacts(self) -> dict:
        """
        获取联系人（包括好友、公众号、服务号、群成员……）
        格式: {"wxid": "NickName"}
        """
        contacts = self.wcf.query_sql("MicroMsg.db", "SELECT UserName, NickName FROM Contact;")
        return {contact["UserName"]: contact["NickName"] for contact in contacts}

    def keepRunningAndBlockProcess(self) -> None:
        """
        保持机器人运行，不让进程退出
        """
        while True:
            self.runPendingJobs()
            time.sleep(1)

    def autoAcceptFriendRequest(self, msg: WxMsg) -> None:
        try:
            xml = ET.fromstring(msg.content)
            v3 = xml.attrib["encryptusername"]
            v4 = xml.attrib["ticket"]
            scene = int(xml.attrib["scene"])
            self.wcf.accept_new_friend(v3, v4, scene)

        except Exception as e:
            self.LOG.error(f"同意好友出错：{e}")

    def sayHiToNewFriend(self, msg: WxMsg) -> None:
        nickName = re.findall(r"你已添加了(.*)，现在可以开始聊天了。", msg.content)
        if nickName:
            # 添加了好友，更新好友列表
            self.allContacts[msg.sender] = nickName[0]
            self.sendTextMsg(f"Hi {nickName[0]}，我自动通过了你的好友请求。", msg.sender)

    def newsReport(self) -> None:
        receivers = self.config.NEWS
        if not receivers:
            self.LOG.info("未配置定时新闻接收人，跳过。")
            return

        self.LOG.info("开始执行定时新闻推送任务...")
        # 获取新闻，解包返回的元组
        is_today, news_content = News().get_important_news()

        # 必须是当天的新闻 (is_today=True) 并且有有效内容 (news_content非空) 才发送
        if is_today and news_content:
            self.LOG.info(f"成功获取当天新闻，准备推送给 {len(receivers)} 个接收人...")
            for r in receivers:
                self.sendTextMsg(news_content, r)
            self.LOG.info("定时新闻推送完成。")
        else:
            # 记录没有发送的原因
            if not is_today and news_content:
                self.LOG.warning("获取到的是旧闻，定时推送已跳过。")
            elif not news_content:
                self.LOG.warning("获取新闻内容失败或为空，定时推送已跳过。")
            else:  # 理论上不会执行到这里
                self.LOG.warning("获取新闻失败（未知原因），定时推送已跳过。")
            
    def handleNewsRequest(self, msg: WxMsg) -> bool:
        """处理用户通过关键词请求新闻的功能"""
        self.LOG.info(f"收到来自 {msg.sender} (群聊: {msg.roomid if msg.from_group() else '无'}) 的新闻请求")
        try:
            news_instance = News()
            # 调用修改后的方法，接收返回的元组(is_today, news_content)
            is_today, news_content = news_instance.get_important_news()

            receiver = msg.roomid if msg.from_group() else msg.sender
            sender_for_at = msg.sender if msg.from_group() else "" # 群聊中@请求者

            if is_today:
                # 是当天新闻，直接发送
                self.sendTextMsg(f"📰 今日要闻来啦：\n{news_content}", receiver, sender_for_at)
                # 如果是群聊，尝试触发馈赠
                if msg.from_group():
                    self._try_trigger_goblin_gift(msg)
                return True
            else:
                # 不是当天新闻或获取失败
                if news_content:
                    # 有内容，说明是旧闻
                    prompt = "ℹ️ 今日新闻暂未发布，为您找到最近的一条新闻："
                    self.sendTextMsg(f"{prompt}\n{news_content}", receiver, sender_for_at)
                    # 如果是群聊，也触发一下馈赠
                    if msg.from_group():
                        self._try_trigger_goblin_gift(msg)
                    return True
                else:
                    # 内容为空，说明获取彻底失败
                    self.sendTextMsg("❌ 获取新闻失败，请稍后重试或联系管理员。", receiver, sender_for_at)
                    # 如果是群聊，也触发一下馈赠
                    if msg.from_group():
                        self._try_trigger_goblin_gift(msg)
                    return True # 也算成功处理了请求

        except Exception as e:
            self.LOG.error(f"处理新闻请求时出错: {e}")
            receiver = msg.roomid if msg.from_group() else msg.sender
            sender_for_at = msg.sender if msg.from_group() else ""
            self.sendTextMsg("❌ 获取新闻时发生错误，请稍后重试。", receiver, sender_for_at)
            return False # 处理失败

    def weatherReport(self, receivers: list = None) -> None:
        if receivers is None:
            receivers = self.config.WEATHER
        if not receivers or not self.config.CITY_CODE:
            self.LOG.warning("未配置天气城市代码或接收人")
            return

        report = Weather(self.config.CITY_CODE).get_weather()
        for r in receivers:
            self.sendTextMsg(report, r)

    def sendDuelMsg(self, msg: str, receiver: str) -> None:
        """发送决斗消息，不受消息频率限制，不记入历史记录
        :param msg: 消息字符串
        :param receiver: 接收人wxid或者群id
        """
        try:
            self.wcf.send_text(f"{msg}", receiver, "")
        except Exception as e:
            self.LOG.error(f"发送决斗消息失败: {e}")

    def _reset_chat_memory(self, chat_id: str) -> str:
        """重置特定聊天的AI对话记忆
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            str: 处理结果消息
        """
        if not self.chat:
            return "⚠️ 未配置AI模型，无需重置"
            
        try:
            # 检查并调用不同AI模型的清除记忆方法
            if hasattr(self.chat, 'conversation_list') and chat_id in getattr(self.chat, 'conversation_list', {}):
                # 判断是哪种类型的模型并执行相应的重置操作
                if isinstance(self.chat, DeepSeek):
                    # DeepSeek模型
                    del self.chat.conversation_list[chat_id]
                    self.LOG.info(f"已重置DeepSeek对话记忆: {chat_id}")
                    return "✅ 已重置DeepSeek对话记忆，开始新的对话"
                    
                elif isinstance(self.chat, ChatGPT):
                    # ChatGPT模型
                    # 保留系统提示，删除其他历史
                    if len(self.chat.conversation_list[chat_id]) > 0:
                        system_msgs = [msg for msg in self.chat.conversation_list[chat_id] if msg["role"] == "system"]
                        self.chat.conversation_list[chat_id] = system_msgs
                        self.LOG.info(f"已重置ChatGPT对话记忆(保留系统提示): {chat_id}")
                        return "✅ 已重置ChatGPT对话记忆，保留系统提示，开始新的对话"
                        
                elif isinstance(self.chat, ChatGLM):
                    # ChatGLM模型
                    if hasattr(self.chat, 'chat_type') and chat_id in self.chat.chat_type:
                        chat_type = self.chat.chat_type[chat_id]
                        # 保留系统提示，删除对话历史
                        if chat_type in self.chat.conversation_list[chat_id]:
                            self.chat.conversation_list[chat_id][chat_type] = []
                            self.LOG.info(f"已重置ChatGLM对话记忆: {chat_id}")
                            return "✅ 已重置ChatGLM对话记忆，开始新的对话"
                    
                elif isinstance(self.chat, Ollama):
                    # Ollama模型
                    if chat_id in self.chat.conversation_list:
                        self.chat.conversation_list[chat_id] = []
                        self.LOG.info(f"已重置Ollama对话记忆: {chat_id}")
                        return "✅ 已重置Ollama对话记忆，开始新的对话"
                
                # 通用处理方式 - 直接删除对话记录
                del self.chat.conversation_list[chat_id]
                self.LOG.info(f"已重置{self.chat.__class__.__name__}对话记忆: {chat_id}")
                return f"✅ 已重置{self.chat.__class__.__name__}对话记忆，开始新的对话"
            
            # 对于没有找到会话记录的情况
            self.LOG.info(f"未找到{self.chat.__class__.__name__}对话记忆: {chat_id}")
            return f"⚠️ 未找到与{self.chat.__class__.__name__}的对话记忆，无需重置"
            
        except Exception as e:
            self.LOG.error(f"重置对话记忆失败: {e}")
            return f"❌ 重置对话记忆失败: {e}"

    def cleanup_perplexity_threads(self):
        """清理所有Perplexity线程"""
        # 如果已初始化Perplexity实例，调用其清理方法
        perplexity_instance = self.get_perplexity_instance()
        if perplexity_instance:
            perplexity_instance.cleanup()
        
        # 检查并等待决斗线程结束
        if hasattr(self, 'duel_manager') and self.duel_manager.is_duel_running():
            self.LOG.info("等待决斗线程结束...")
            # 最多等待5秒
            for i in range(5):
                if not self.duel_manager.is_duel_running():
                    break
                time.sleep(1)
                
            if self.duel_manager.is_duel_running():
                self.LOG.warning("决斗线程在退出时仍在运行")
            else:
                self.LOG.info("决斗线程已结束")
                
    def cleanup(self):
        """清理所有资源，在程序退出前调用"""
        self.LOG.info("开始清理机器人资源...")
        
        # 清理Perplexity线程
        self.cleanup_perplexity_threads()
        
        # 关闭消息历史数据库连接
        if hasattr(self, 'message_summary') and self.message_summary:
            self.LOG.info("正在关闭消息历史数据库...")
            self.message_summary.close_db()
        
        self.LOG.info("机器人资源清理完成")
                
    def get_perplexity_instance(self):
        """获取Perplexity实例
        
        Returns:
            Perplexity: Perplexity实例，如果未配置则返回None
        """
        # 检查是否已有Perplexity实例
        if hasattr(self, 'perplexity'):
            return self.perplexity
            
        # 检查config中是否有Perplexity配置
        if hasattr(self.config, 'PERPLEXITY') and Perplexity.value_check(self.config.PERPLEXITY):
            self.perplexity = Perplexity(self.config.PERPLEXITY)
            return self.perplexity
            
        # 检查chat是否是Perplexity类型
        if isinstance(self.chat, Perplexity):
            return self.chat
            
        # 如果存在chat_models字典，尝试从中获取
        if hasattr(self, 'chat_models') and ChatType.PERPLEXITY.value in self.chat_models:
            return self.chat_models[ChatType.PERPLEXITY.value]
            
        return None

    def _try_trigger_goblin_gift(self, msg: WxMsg) -> None:
        """尝试触发古灵阁妖精的馈赠事件
        
        用户与机器人互动时，有概率获得随机积分
        根据配置决定是否启用及在哪些群聊启用
        
        Args:
            msg: 微信消息对象
        """
        # 调用管理器的触发方法
        self.goblin_gift_manager.try_trigger(msg)

    def _select_model_for_message(self, msg: WxMsg) -> None:
        """根据消息来源选择对应的AI模型
        :param msg: 接收到的消息
        """
        if not hasattr(self, 'chat_models') or not self.chat_models:
            return  # 没有可用模型，无需切换
            
        # 获取消息来源ID
        source_id = msg.roomid if msg.from_group() else msg.sender
        
        # 检查配置
        if not hasattr(self.config, 'GROUP_MODELS'):
            # 没有配置，使用默认模型
            if self.default_model_id in self.chat_models:
                self.chat = self.chat_models[self.default_model_id]
            return
            
        # 群聊消息处理
        if msg.from_group():
            model_mappings = self.config.GROUP_MODELS.get('mapping', [])
            for mapping in model_mappings:
                if mapping.get('room_id') == source_id:
                    model_id = mapping.get('model')
                    if model_id in self.chat_models:
                        # 切换到指定模型
                        if self.chat != self.chat_models[model_id]:
                            self.chat = self.chat_models[model_id]
                            self.LOG.info(f"已为群 {source_id} 切换到模型: {self.chat.__class__.__name__}")
                    else:
                        self.LOG.warning(f"群 {source_id} 配置的模型ID {model_id} 不可用，使用默认模型")
                        if self.default_model_id in self.chat_models:
                            self.chat = self.chat_models[self.default_model_id]
                    return
        # 私聊消息处理
        else:
            private_mappings = self.config.GROUP_MODELS.get('private_mapping', [])
            for mapping in private_mappings:
                if mapping.get('wxid') == source_id:
                    model_id = mapping.get('model')
                    if model_id in self.chat_models:
                        # 切换到指定模型
                        if self.chat != self.chat_models[model_id]:
                            self.chat = self.chat_models[model_id]
                            self.LOG.info(f"已为私聊用户 {source_id} 切换到模型: {self.chat.__class__.__name__}")
                    else:
                        self.LOG.warning(f"私聊用户 {source_id} 配置的模型ID {model_id} 不可用，使用默认模型")
                        if self.default_model_id in self.chat_models:
                            self.chat = self.chat_models[self.default_model_id]
                    return
        
        # 如果没有找到对应配置，使用默认模型
        if self.default_model_id in self.chat_models:
            self.chat = self.chat_models[self.default_model_id]

    def onMsg(self, msg: WxMsg) -> int:
        try:
            self.LOG.info(msg)
            self.processMsg(msg)
        except Exception as e:
            self.LOG.error(e)

        return 0

