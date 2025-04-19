# -*- coding: utf-8 -*-

import logging
import re
import time
import xml.etree.ElementTree as ET
from queue import Empty
from threading import Thread, Lock
import os
import random
import shutil
from collections import deque  # 添加deque用于消息历史记录
from base.func_zhipu import ZhiPu
from image import CogView, AliyunImage, GeminiImage

from wcferry import Wcf, WxMsg

from base.func_bard import BardAssistant
from base.func_chatglm import ChatGLM
from base.func_ollama import Ollama
from base.func_chatgpt import ChatGPT
from base.func_deepseek import DeepSeek
from base.func_perplexity import Perplexity
from base.func_chengyu import cy
from base.func_weather import Weather
from base.func_news import News
from base.func_tigerbot import TigerBot
from base.func_xinghuo_web import XinghuoWeb
from base.func_duel import start_duel, get_rank_list, get_player_stats, change_player_name
from configuration import Config
from constants import ChatType
from job_mgmt import Job

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
        # 决斗线程管理
        self._duel_thread = None
        self._duel_lock = Lock()
        
        # Perplexity请求线程管理
        self._perplexity_threads = {}
        self._perplexity_lock = Lock()
        
        # 消息历史记录 - 存储最近的200条消息
        self._msg_history = {}  # 使用字典，以群ID或用户ID为键
        self._msg_history_lock = Lock()  # 添加锁以保证线程安全
        
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
        
        # 初始化图像生成服务
        self.cogview = None
        self.aliyun_image = None
        self.gemini_image = None
        
        # 初始化Gemini图像生成服务
        try:
            if hasattr(self.config, 'GEMINI_IMAGE'):
                self.gemini_image = GeminiImage(self.config.GEMINI_IMAGE)
            else:
                self.gemini_image = GeminiImage({})
            
            if getattr(self.gemini_image, 'enable', False):
                self.LOG.info("谷歌Gemini图像生成功能已启用")
        except Exception as e:
            self.LOG.error(f"初始化谷歌Gemini图像生成服务失败: {e}")
        
        # 初始化CogView和AliyunImage服务
        if hasattr(self.config, 'COGVIEW') and self.config.COGVIEW.get('enable', False):
            try:
                self.cogview = CogView(self.config.COGVIEW)
                self.LOG.info("智谱CogView文生图功能已初始化")
            except Exception as e:
                self.LOG.error(f"初始化智谱CogView文生图服务失败: {str(e)}")
        if hasattr(self.config, 'ALIYUN_IMAGE') and self.config.ALIYUN_IMAGE.get('enable', False):
            try:
                self.aliyun_image = AliyunImage(self.config.ALIYUN_IMAGE)
                self.LOG.info("阿里Aliyun功能已初始化")
            except Exception as e:
                self.LOG.error(f"初始化阿里云文生图服务失败: {str(e)}")
                
    @staticmethod
    def value_check(args: dict) -> bool:
        if args:
            return all(value is not None for key, value in args.items() if key != 'proxy')
        return False

    def handle_image_generation(self, service_type, prompt, receiver, at_user=None):
        """处理图像生成请求的通用函数
        :param service_type: 服务类型，'cogview'/'aliyun'/'gemini'
        :param prompt: 图像生成提示词
        :param receiver: 接收者ID
        :param at_user: 被@的用户ID，用于群聊
        :return: 处理状态，True成功，False失败
        """
        if service_type == 'cogview':
            if not self.cogview or not hasattr(self.config, 'COGVIEW') or not self.config.COGVIEW.get('enable', False):
                self.LOG.info(f"收到智谱文生图请求但功能未启用: {prompt}")
                fallback_to_chat = self.config.COGVIEW.get('fallback_to_chat', False) if hasattr(self.config, 'COGVIEW') else False
                if not fallback_to_chat:
                    self.sendTextMsg("报一丝，智谱文生图功能没有开启，请联系管理员开启此功能。（可以贿赂他开启）", receiver, at_user)
                    return True
                return False
            service = self.cogview
            wait_message = "正在生成图像，请稍等..."
        elif service_type == 'aliyun':
            if not self.aliyun_image or not hasattr(self.config, 'ALIYUN_IMAGE') or not self.config.ALIYUN_IMAGE.get('enable', False):
                self.LOG.info(f"收到阿里文生图请求但功能未启用: {prompt}")
                fallback_to_chat = self.config.ALIYUN_IMAGE.get('fallback_to_chat', False) if hasattr(self.config, 'ALIYUN_IMAGE') else False
                if not fallback_to_chat:
                    self.sendTextMsg("报一丝，阿里文生图功能没有开启，请联系管理员开启此功能。（可以贿赂他开启）", receiver, at_user)
                    return True
                return False
            service = self.aliyun_image
            model_type = self.config.ALIYUN_IMAGE.get('model', '')
            if model_type == 'wanx2.1-t2i-plus':
                wait_message = "当前模型为阿里PLUS模型，生成速度较慢，请耐心等候..."
            elif model_type == 'wanx-v1':
                wait_message = "当前模型为阿里V1模型，生成速度非常慢，可能需要等待较长时间，请耐心等候..."
            else:
                wait_message = "正在生成图像，请稍等..."
        elif service_type == 'gemini':
            if not self.gemini_image or not getattr(self.gemini_image, 'enable', False):
                self.sendTextMsg("谷歌文生图服务未启用", receiver, at_user)
                return True
                
            service = self.gemini_image
            wait_message = "正在通过谷歌AI生成图像，请稍等..."
        else:
            self.LOG.error(f"未知的图像生成服务类型: {service_type}")
            return False
            
        self.LOG.info(f"收到图像生成请求 [{service_type}]: {prompt}")
        self.sendTextMsg(wait_message, receiver, at_user)
        
        image_url = service.generate_image(prompt)
        
        if image_url and (image_url.startswith("http") or os.path.exists(image_url)):
            try:
                self.LOG.info(f"开始处理图片: {image_url}")
                # 谷歌API直接返回本地文件路径，无需下载
                image_path = image_url if service_type == 'gemini' else service.download_image(image_url)
                
                if image_path:
                    # 创建一个临时副本，避免文件占用问题
                    temp_dir = os.path.dirname(image_path)
                    file_ext = os.path.splitext(image_path)[1]
                    temp_copy = os.path.join(
                        temp_dir,
                        f"temp_{service_type}_{int(time.time())}_{random.randint(1000, 9999)}{file_ext}"
                    )
                    
                    try:
                        # 创建文件副本
                        shutil.copy2(image_path, temp_copy)
                        self.LOG.info(f"创建临时副本: {temp_copy}")
                        
                        # 发送临时副本
                        self.LOG.info(f"发送图片到 {receiver}: {temp_copy}")
                        self.wcf.send_image(temp_copy, receiver)
                        
                        # 等待一小段时间确保微信API完成处理
                        time.sleep(1.5)
                        
                    except Exception as e:
                        self.LOG.error(f"创建或发送临时副本失败: {str(e)}")
                        # 如果副本处理失败，尝试直接发送原图
                        self.LOG.info(f"尝试直接发送原图: {image_path}")
                        self.wcf.send_image(image_path, receiver)
                    
                    # 安全删除文件
                    self._safe_delete_file(image_path)
                    if os.path.exists(temp_copy):
                        self._safe_delete_file(temp_copy)
                                   
                else:
                    self.LOG.warning(f"图片下载失败，发送URL链接作为备用: {image_url}")
                    self.sendTextMsg(f"图像已生成，但无法自动显示，点链接也能查看:\n{image_url}", receiver, at_user)
            except Exception as e:
                self.LOG.error(f"发送图片过程出错: {str(e)}")
                self.sendTextMsg(f"图像已生成，但发送过程出错，点链接也能查看:\n{image_url}", receiver, at_user)
        else:
            self.LOG.error(f"图像生成失败: {image_url}")
            self.sendTextMsg(f"图像生成失败: {image_url}", receiver, at_user)
        
        return True

    def _safe_delete_file(self, file_path, max_retries=3, retry_delay=1.0):
        """安全删除文件，带有重试机制
        
        :param file_path: 要删除的文件路径
        :param max_retries: 最大重试次数
        :param retry_delay: 重试间隔(秒)
        :return: 是否成功删除
        """
        if not os.path.exists(file_path):
            return True
            
        for attempt in range(max_retries):
            try:
                os.remove(file_path)
                self.LOG.info(f"成功删除文件: {file_path}")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    self.LOG.warning(f"删除文件 {file_path} 失败, 将在 {retry_delay} 秒后重试: {str(e)}")
                    time.sleep(retry_delay)
                else:
                    self.LOG.error(f"无法删除文件 {file_path} 经过 {max_retries} 次尝试: {str(e)}")
        
        return False

    def get_bot_help_info(self) -> str:
        """获取机器人的帮助信息，包含所有可用指令"""
        help_text = [
            "🤖 泡泡的指令列表 🤖",
            "",
            "【决斗系统】",
            "▶️ 决斗@XX - 向某人发起决斗",
            "▶️ 决斗排行/排行榜",
            "▶️ 我的战绩/决斗战绩",
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
        
        # 处理重置对话记忆命令
        if content.lower() == "reset" or content == "重置" or content == "重置记忆":
            self.LOG.info(f"收到重置对话记忆请求: {msg.content}")
            chat_id = msg.roomid if msg.from_group() else msg.sender
            
            # 重置聊天记忆
            result = self._reset_chat_memory(chat_id)
            
            if msg.from_group():
                self.sendTextMsg(result, msg.roomid, msg.sender)
            else:
                self.sendTextMsg(result, msg.sender)
                
            return True
        
        # 处理消息总结命令
        if content.lower() == "summary" or content == "总结":
            self.LOG.info(f"收到消息总结请求: {msg.content}")
            # 获取聊天ID
            chat_id = msg.roomid if msg.from_group() else msg.sender
            
            # 生成总结
            summary = self._summarize_messages(chat_id)
            
            # 发送总结
            if msg.from_group():
                self.sendTextMsg(summary, msg.roomid, msg.sender)
            else:
                self.sendTextMsg(summary, msg.sender)
                
            return True
        
        # 处理清除历史命令
        if content.lower() == "clearmessages" or content == "清除消息" or content == "清除历史":
            self.LOG.info(f"收到清除消息历史请求: {msg.content}")
            # 获取聊天ID
            chat_id = msg.roomid if msg.from_group() else msg.sender
            
            # 清除历史
            if self._clear_message_history(chat_id):
                if msg.from_group():
                    self.sendTextMsg("✅ 已清除本群的消息历史记录", msg.roomid, msg.sender)
                else:
                    self.sendTextMsg("✅ 已清除与您的消息历史记录", msg.sender)
            else:
                if msg.from_group():
                    self.sendTextMsg("⚠️ 本群没有消息历史记录", msg.roomid, msg.sender)
                else:
                    self.sendTextMsg("⚠️ 没有与您的消息历史记录", msg.sender)
                    
            return True
        
        # 改名命令处理 - 添加到toAt方法中处理被@的情况
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
                return True
        
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
                if not self.start_duel_thread(challenger_name, opponent_name, msg.roomid, True):
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
            return True
        
        # 个人战绩查询
        stats_match = re.search(r"(决斗战绩|我的战绩|战绩查询)(.*)", content)
        if stats_match:
            player_name = stats_match.group(2).strip()
            if not player_name:  # 如果没有指定名字，则查询发送者
                player_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
            
            stats = get_player_stats(player_name, msg.roomid)  # 传递群ID
            self.sendTextMsg(stats, msg.roomid)
            return True
        
        # 查看装备功能
        if content == "我的装备" or content == "查看装备":
            player_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
            
            from base.func_duel import DuelRankSystem
            rank_system = DuelRankSystem(msg.roomid)
            player_data = rank_system.get_player_data(player_name)
            
            items = player_data["items"]
            result = [
                f"🧙‍♂️ {player_name} 的魔法装备:",
                f"🪄 老魔杖: {items['elder_wand']}次 (胜利积分×10)",
                f"💎 魔法石: {items['magic_stone']}次 (失败不扣分)",
                f"🧥 隐身衣: {items['invisibility_cloak']}次 (自动获胜)"
            ]
            
            self.sendTextMsg("\n".join(result), msg.roomid)
            return True
        
        # 帮助信息查询
        if content.startswith("info") or content == "帮助" or content == "指令":
            help_info = self.get_bot_help_info()
            self.sendTextMsg(help_info, msg.roomid)
            return True
        
        # 阿里文生图处理
        if content.startswith(aliyun_trigger):
            prompt = content[len(aliyun_trigger):].strip()
            if prompt:
                result = self.handle_image_generation('aliyun', prompt, msg.roomid, msg.sender)
                if result:
                    return True
                
        # CogView处理
        elif content.startswith(cogview_trigger):
            prompt = content[len(cogview_trigger):].strip()
            if prompt:
                result = self.handle_image_generation('cogview', prompt, msg.roomid, msg.sender)
                if result:
                    return True
        
        # 谷歌AI画图处理
        elif content.startswith(gemini_trigger):
            prompt = content[len(gemini_trigger):].strip()
            if prompt:
                return self.handle_image_generation('gemini', prompt, msg.roomid or msg.sender, msg.sender if msg.roomid else None)
            else:
                self.sendTextMsg(f"请在{gemini_trigger}后面添加您想要生成的图像描述", msg.roomid or msg.sender, msg.sender if msg.roomid else None)
                return True
        
        # Perplexity处理
        elif content.startswith(perplexity_trigger):
            prompt = content[len(perplexity_trigger):].strip()
            if prompt:
                # 获取Perplexity实例
                if not hasattr(self, 'perplexity'):
                    if hasattr(self.config, 'PERPLEXITY') and Perplexity.value_check(self.config.PERPLEXITY):
                        self.perplexity = Perplexity(self.config.PERPLEXITY)
                    else:
                        self.sendTextMsg("Perplexity服务未配置", msg.roomid if msg.from_group() else msg.sender)
                        return True
                
                # 使用现有的chat实例如果它是Perplexity
                perplexity_instance = self.perplexity if hasattr(self, 'perplexity') else (self.chat if isinstance(self.chat, Perplexity) else None)
                
                if perplexity_instance:
                    chat_id = msg.roomid if msg.from_group() else msg.sender
                    receiver = msg.roomid if msg.from_group() else msg.sender
                    at_user = msg.sender if msg.from_group() else None
                    
                    # 检查是否已有正在处理的相同请求
                    thread_key = f"{receiver}_{chat_id}"
                    with self._perplexity_lock:
                        if thread_key in self._perplexity_threads and self._perplexity_threads[thread_key].is_alive():
                            self.sendTextMsg("⚠️ 已有一个Perplexity请求正在处理中，请稍后再试", receiver, at_user)
                            return True
                    
                    # 发送等待消息
                    self.sendTextMsg("正在使用Perplexity进行深度研究，请稍候...", receiver, at_user)
                    
                    # 创建并启动新线程处理请求
                    perplexity_thread = PerplexityThread(
                        perplexity_instance=perplexity_instance,
                        prompt=prompt,
                        chat_id=chat_id,
                        robot=self,
                        receiver=receiver,
                        at_user=at_user
                    )
                    
                    # 添加到线程管理字典
                    with self._perplexity_lock:
                        self._perplexity_threads[thread_key] = perplexity_thread
                    
                    # 启动线程
                    perplexity_thread.start()
                    self.LOG.info(f"已启动Perplexity请求线程: {thread_key}")
                    
                    return True
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
                        self.sendTextMsg(rsp, msg.roomid)
                        status = True
            elif flag in ["?", "？"]:  # 查词
                if cy.isChengyu(text):
                    rsp = cy.getMeaning(text)
                    if rsp:
                        self.sendTextMsg(rsp, msg.roomid)
                        status = True

        return status

    def toChitchat(self, msg: WxMsg) -> bool:
        """闲聊，接入 ChatGPT
        """
        if not self.chat:  # 没接 ChatGPT，固定回复
            rsp = "你@我干嘛？"
        else:  # 接了 ChatGPT，智能回复
            # 提取消息内容，处理引用消息的特殊情况
            user_msg = ""
            
            # 处理类型49的消息（引用、卡片、链接等）
            if msg.type == 49 and ("<title>" in msg.content or "<appmsg" in msg.content):
                # 从title标签提取用户实际消息
                title_match = re.search(r'<title>(.*?)</title>', msg.content)
                if title_match:
                    user_msg = title_match.group(1).strip()
                    # 删除可能的@机器人前缀
                    user_msg = re.sub(r'^@[\w\s]+\s+', '', user_msg).strip()
                    
                    # 记录提取到的用户消息
                    self.LOG.info(f"从title标签中提取到用户消息: {user_msg}")
                else:
                    self.LOG.warning("引用消息中没有找到title标签内容")
            else:
                # 普通消息情况，去除@标记
                user_msg = re.sub(r"@.*?[\u2005|\s]", "", msg.content).strip()
            
            # 处理可能存在的引用消息
            quoted_content = self._extract_quoted_message(msg)
            
            # 获取发送者昵称
            if msg.from_group():
                sender_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
            else:
                sender_name = self.allContacts.get(msg.sender, "用户")
            
            # 添加时间戳和发送者信息到用户消息前面
            current_time = time.strftime("%H:%M", time.localtime())
            
            # 构建完整消息，包含用户消息和引用内容（如果有）
            if not user_msg and quoted_content:
                # 如果没有提取到用户消息但有引用内容，可能是纯引用消息
                self.LOG.info(f"处理纯引用消息: 用户={sender_name}, 引用={quoted_content}")
                q_with_info = f"[{current_time}] {sender_name} 分享了内容: {quoted_content}"
            elif quoted_content:
                # 有用户消息和引用内容
                self.LOG.info(f"处理带引用的消息: 用户={sender_name}, 消息={user_msg}, 引用={quoted_content}")
                q_with_info = f"[{current_time}] {sender_name}: {user_msg}\n\n[用户引用] {quoted_content}"
            else:
                # 只有用户消息
                q_with_info = f"[{current_time}] {sender_name}: {user_msg}"
            
            rsp = self.chat.get_answer(q_with_info, (msg.roomid if msg.from_group() else msg.sender))

        if rsp:
            if msg.from_group():
                self.sendTextMsg(rsp, msg.roomid, msg.sender)
            else:
                self.sendTextMsg(rsp, msg.sender)

            return True
        else:
            self.LOG.error(f"无法从 ChatGPT 获得答案")
            return False

    def _extract_quoted_message(self, msg: WxMsg) -> str:
        """从微信消息中提取引用内容
        
        Args:
            msg: 微信消息对象
            
        Returns:
            str: 提取的引用内容，如果没有引用返回空字符串
        """
        try:
            # 检查消息类型
            if msg.type != 0x01 and msg.type != 49:  # 普通文本消息或APP消息
                return ""
            
            # 记录调试信息，帮助排查私聊问题    
            is_group = msg.from_group()
            chat_id = msg.roomid if is_group else msg.sender
            self.LOG.info(f"尝试提取引用消息: 消息类型={msg.type}, 是否群聊={is_group}, 接收ID={chat_id}")
                
            # 检查是否包含XML格式的内容 - 增强检测能力
            has_xml = (msg.content.startswith("<?xml") or 
                       msg.content.startswith("<msg>") or 
                       "<appmsg" in msg.content or 
                       "<refermsg>" in msg.content)
            has_refer = ("<refermsg>" in msg.content or 
                         "引用" in msg.content or 
                         "回复" in msg.content)
            
            # 如果非XML且无引用标记，快速返回
            if not (has_xml or has_refer):
                return ""
                
            self.LOG.info(f"检测到可能包含引用的消息: 类型={msg.type}, XML={has_xml}, 引用={has_refer}, 内容前100字符: {msg.content[:100]}")
                
            # 解析XML内容
            import xml.etree.ElementTree as ET
            
            # 处理微信消息可能的格式，特别是私聊消息
            xml_content = msg.content
            
            # 有时私聊消息会有额外的前缀，尝试找到XML的开始位置
            if not (msg.content.startswith("<?xml") or msg.content.startswith("<msg>")):
                xml_start_tags = ["<msg>", "<appmsg", "<?xml", "<refermsg>"]
                for tag in xml_start_tags:
                    pos = msg.content.find(tag)
                    if pos >= 0:
                        xml_content = msg.content[pos:]
                        self.LOG.info(f"找到XML开始标签 {tag} 位置 {pos}, 截取后内容长度: {len(xml_content)}")
                        break
                
                # 如果找到了XML开始但不是标准XML声明，添加声明
                if not xml_content.startswith("<?xml"):
                    xml_content = f"<?xml version='1.0'?>\n{xml_content}"
                    
            # 尝试清理可能导致解析失败的字符
            xml_content = self._clean_xml_for_parsing(xml_content)
                    
            # 尝试解析XML
            root = None
            try:
                root = ET.fromstring(xml_content)
                self.LOG.info("成功解析XML内容")
            except ET.ParseError as e:
                self.LOG.warning(f"初次解析XML失败: {e}, 尝试进一步修复")
                # 尝试更激进的清理
                xml_content = xml_content.replace("&", "&amp;").replace("<!", "<!--").replace("![", "<!--[").replace("]>", "]-->")
                try:
                    root = ET.fromstring(xml_content)
                    self.LOG.info("在进行额外清理后成功解析XML")
                except ET.ParseError as e2:
                    self.LOG.error(f"解析引用消息XML失败: {e2}, 原始内容: {msg.content[:100]}...")
                    return self._extract_quoted_fallback(msg.content)
            
            if root is None:
                self.LOG.error("无法解析XML内容")
                return self._extract_quoted_fallback(msg.content)
            
            # 记录解析后的XML结构用于调试
            try:
                self.LOG.debug(f"解析后的XML根节点标签: {root.tag}")
            except:
                pass
            
            # 提取引用内容 - 处理多种可能的XML结构，包括私聊特有格式
            extracted_content = ""
            
            # 方式1: 直接在根节点查找refermsg
            extracted_content = self._extract_from_refermsg(root)
            if extracted_content:
                return extracted_content
            
            # 方式2: 在appmsg中查找refermsg
            appmsg = root.find(".//appmsg")
            if appmsg is not None:
                # 首先检查标题
                title = appmsg.find("title")
                title_text = title.text if title is not None and title.text else ""
                
                # 从appmsg的refermsg中提取
                extracted_content = self._extract_from_refermsg(appmsg)
                if extracted_content:
                    return extracted_content
                
                # 如果有标题但没有提取到refermsg内容
                if title_text:
                    self.LOG.info(f"只找到appmsg标题: {title_text}")
                    # 查找是否有标记为title的引用内容
                    if "引用" in title_text or "回复" in title_text:
                        return f"引用内容: {title_text}"
                    return f"相关内容: {title_text}"
            
            # 方式3: 寻找任何可能包含引用信息的元素
            if "引用" in xml_content or "回复" in xml_content:
                for elem in root.findall(".//*"):
                    if elem.text and ("引用" in elem.text or "回复" in elem.text):
                        self.LOG.info(f"通过关键词找到可能的引用内容: {elem.text[:30]}...")
                        return f"引用内容: {elem.text}"
            
            # 最后的后备方案：直接从原始内容提取
            return self._extract_quoted_fallback(msg.content)
            
        except Exception as e:
            self.LOG.error(f"提取引用消息时出错: {e}")
            # 即使出错也尝试提取
            return self._extract_quoted_fallback(msg.content)
    
    def _extract_from_refermsg(self, element) -> str:
        """从refermsg元素中提取引用内容
        
        Args:
            element: XML元素，可能包含refermsg子元素
            
        Returns:
            str: 提取的引用内容，如果未找到返回空字符串
        """
        try:
            refer_msg = element.find(".//refermsg")
            if refer_msg is None:
                return ""
                
            # 提取引用的发送者和内容
            display_name = refer_msg.find("displayname")
            content = refer_msg.find("content")
            
            display_name_text = display_name.text if display_name is not None and display_name.text else ""
            content_text = content.text if content is not None and content.text else ""
            
            # 清理可能存在的HTML/XML标签，确保纯文本
            if content_text:
                content_text = re.sub(r'<.*?>', '', content_text)
                # 不再限制引用内容长度
            
            if display_name_text and content_text:
                return f"{display_name_text}: {content_text}"
            elif content_text:
                return content_text
                
            return ""
        except Exception as e:
            self.LOG.error(f"从refermsg提取内容时出错: {e}")
            return ""
    
    def _clean_xml_for_parsing(self, xml_content: str) -> str:
        """清理XML内容，使其更容易被解析
        
        Args:
            xml_content: 原始XML内容
            
        Returns:
            str: 清理后的XML内容
        """
        try:
            # 替换常见的问题字符
            cleaned = xml_content.replace("&", "&amp;")
            
            # 处理CDATA部分
            cleaned = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', cleaned, flags=re.DOTALL)
            
            # 移除可能导致解析问题的控制字符
            cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', cleaned)
            
            # 如果清理后的内容太长，截取合理长度以提高解析效率
            if len(cleaned) > 10000:  # 10KB上限
                cleaned = cleaned[:10000]
                self.LOG.warning(f"XML内容过长，已截断至10000字符")
            
            return cleaned
        except Exception as e:
            self.LOG.error(f"清理XML内容时出错: {e}")
            return xml_content
    
    def _extract_quoted_fallback(self, content: str) -> str:
        """当XML解析失败时的后备提取方法
        
        Args:
            content: 原始消息内容
            
        Returns:
            str: 提取的引用内容，如果未找到返回空字符串
        """
        try:
            # 使用正则表达式直接从内容中提取
            # 查找<content>标签内容
            content_match = re.search(r'<content>(.*?)</content>', content, re.DOTALL)
            if content_match:
                extracted = content_match.group(1)
                # 清理可能存在的XML标签
                extracted = re.sub(r'<.*?>', '', extracted)
                # 不再限制内容长度
                return extracted
                
            # 查找displayname和content的组合
            display_name_match = re.search(r'<displayname>(.*?)</displayname>', content, re.DOTALL)
            content_match = re.search(r'<content>(.*?)</content>', content, re.DOTALL)
            
            if display_name_match and content_match:
                name = re.sub(r'<.*?>', '', display_name_match.group(1))
                text = re.sub(r'<.*?>', '', content_match.group(1))
                # 不再限制内容长度
                return f"{name}: {text}"
                
            # 查找引用或回复的关键词
            if "引用" in content or "回复" in content:
                # 寻找引用关键词后的内容
                match = re.search(r'[引用|回复].*?[:：](.*?)(?:<|$)', content, re.DOTALL)
                if match:
                    text = match.group(1).strip()
                    text = re.sub(r'<.*?>', '', text)
                    # 不再限制内容长度
                    return text
            
            return ""
        except Exception as e:
            self.LOG.error(f"后备提取引用内容时出错: {e}")
            return ""

    def processMsg(self, msg: WxMsg) -> None:
        """当接收到消息的时候，会调用本方法。如果不实现本方法，则打印原始消息。
        此处可进行自定义发送的内容,如通过 msg.content 关键字自动获取当前天气信息，并发送到对应的群组@发送者
        群号：msg.roomid  微信ID：msg.sender  消息内容：msg.content
        content = "xx天气信息为："
        receivers = msg.roomid
        self.sendTextMsg(content, receivers, msg.sender)
        """
        try:
            # 记录消息到历史记录
            self._record_message(msg)
            
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
                                if not self.start_duel_thread(challenger_name, opponent_name, msg.roomid, True):
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
                            result = self.handle_image_generation('aliyun', prompt, msg.sender)
                            if result:
                                return
                    
                    # CogView触发词处理
                    cogview_trigger = self.config.COGVIEW.get('trigger_keyword', '牛智谱') if hasattr(self.config, 'COGVIEW') else '牛智谱'
                    if msg.content.startswith(cogview_trigger):
                        prompt = msg.content[len(cogview_trigger):].strip()
                        if prompt:
                            result = self.handle_image_generation('cogview', prompt, msg.sender)
                            if result:
                                return
                    
                    # 谷歌AI画图触发词处理
                    gemini_trigger = self.config.GEMINI_IMAGE.get('trigger_keyword', '牛谷歌') if hasattr(self.config, 'GEMINI_IMAGE') else '牛谷歌'
                    if msg.content.startswith(gemini_trigger):
                        prompt = msg.content[len(gemini_trigger):].strip()
                        if prompt:
                            result = self.handle_image_generation('gemini', prompt, msg.sender)
                            if result:
                                return
                    
                    # Perplexity触发词处理
                    perplexity_trigger = self.config.PERPLEXITY.get('trigger_keyword', 'ask') if hasattr(self.config, 'PERPLEXITY') else 'ask'
                    if msg.content.startswith(perplexity_trigger):
                        prompt = msg.content[len(perplexity_trigger):].strip()
                        if prompt:
                            # 获取Perplexity实例
                            if not hasattr(self, 'perplexity'):
                                if hasattr(self.config, 'PERPLEXITY') and Perplexity.value_check(self.config.PERPLEXITY):
                                    self.perplexity = Perplexity(self.config.PERPLEXITY)
                                else:
                                    self.sendTextMsg("Perplexity服务未配置", msg.roomid if msg.from_group() else msg.sender)
                                    return True
                            
                            # 使用现有的chat实例如果它是Perplexity
                            perplexity_instance = self.perplexity if hasattr(self, 'perplexity') else (self.chat if isinstance(self.chat, Perplexity) else None)
                            
                            if perplexity_instance:
                                chat_id = msg.roomid if msg.from_group() else msg.sender
                                receiver = msg.roomid if msg.from_group() else msg.sender
                                at_user = msg.sender if msg.from_group() else None
                                
                                # 检查是否已有正在处理的相同请求
                                thread_key = f"{receiver}_{chat_id}"
                                with self._perplexity_lock:
                                    if thread_key in self._perplexity_threads and self._perplexity_threads[thread_key].is_alive():
                                        self.sendTextMsg("⚠️ 已有一个Perplexity请求正在处理中，请稍后再试", receiver, at_user)
                                        return True
                                
                                # 发送等待消息
                                self.sendTextMsg("正在使用Perplexity进行深度研究，请稍候...", receiver, at_user)
                                
                                # 创建并启动新线程处理请求
                                perplexity_thread = PerplexityThread(
                                    perplexity_instance=perplexity_instance,
                                    prompt=prompt,
                                    chat_id=chat_id,
                                    robot=self,
                                    receiver=receiver,
                                    at_user=at_user
                                )
                                
                                # 添加到线程管理字典
                                with self._perplexity_lock:
                                    self._perplexity_threads[thread_key] = perplexity_thread
                                
                                # 启动线程
                                perplexity_thread.start()
                                self.LOG.info(f"已启动Perplexity请求线程: {thread_key}")
                                
                                return True
                            else:
                                self.sendTextMsg("Perplexity服务未配置", msg.roomid if msg.from_group() else msg.sender)
                                return True
                        else:
                            self.sendTextMsg(f"请在{perplexity_trigger}后面添加您的问题", msg.roomid if msg.from_group() else msg.sender)
                            return True

                    self.toChitchat(msg)  # 闲聊

        except Exception as e:
            self.LOG.error(f"处理消息时发生错误: {e}")

    def _record_message(self, msg: WxMsg) -> None:
        """记录消息到历史记录
        
        Args:
            msg: 微信消息
        """
        # 跳过特定类型的消息
        if msg.type != 0x01:  # 只记录文本消息
            return
            
        # 跳过自己发送的消息
        if msg.from_self():
            return
            
        with self._msg_history_lock:
            # 获取接收者ID（群ID或用户ID）
            chat_id = msg.roomid if msg.from_group() else msg.sender
            
            # 如果该聊天没有历史记录，创建一个新的队列
            if chat_id not in self._msg_history:
                self._msg_history[chat_id] = deque(maxlen=200)
                
            # 获取发送者昵称
            if msg.from_group():
                sender_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
            else:
                sender_name = self.allContacts.get(msg.sender, msg.sender)
                
            # 记录消息，包含发送者昵称和内容
            self._msg_history[chat_id].append({
                "sender": sender_name,
                "content": msg.content,
                "time": time.strftime("%H:%M", time.localtime())
            })
    
    def _clear_message_history(self, chat_id: str) -> bool:
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
    
    def _summarize_messages(self, chat_id: str) -> str:
        """生成消息总结
        
        Args:
            chat_id: 聊天ID（群ID或用户ID）
            
        Returns:
            str: 消息总结
        """
        with self._msg_history_lock:
            if chat_id not in self._msg_history or not self._msg_history[chat_id]:
                return "没有可以总结的历史消息。"
                
            # 复制历史消息，以防在处理过程中有变动
            messages = list(self._msg_history[chat_id])
            
        # 如果没有消息模型，返回基本总结
        if not self.chat:
            return self._basic_summarize(messages)
            
        # 使用AI模型生成总结
        return self._ai_summarize(messages, chat_id)
    
    def _basic_summarize(self, messages: list) -> str:
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
    
    def _ai_summarize(self, messages: list, chat_id: str) -> str:
        """使用AI模型生成消息总结
        
        Args:
            messages: 消息列表
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
            "- 主要参与者\n"
            "- 讨论的主要话题\n"
            "- 关键信息和要点\n\n"
            "请直接给出总结内容，不要添加额外的评论或人格色彩。\n\n"
            "消息记录:\n" + "\n".join(formatted_msgs)
        )
        
        # 使用AI模型生成总结 - 创建一个临时的聊天会话ID，避免污染正常对话上下文
        try:
            # 对于支持新会话参数的模型，使用特殊标记告知这是独立的总结请求
            if hasattr(self.chat, 'get_answer_with_context') and callable(getattr(self.chat, 'get_answer_with_context')):
                # 使用带上下文参数的方法
                summary = self.chat.get_answer_with_context(prompt, "summary_" + chat_id, clear_context=True)
            else:
                # 普通方法，使用特殊会话ID
                summary = self.chat.get_answer(prompt, "summary_" + chat_id)
                
            if not summary:
                return self._basic_summarize(messages)
                
            return "📋 消息总结：\n\n" + summary
        except Exception as e:
            self.LOG.error(f"使用AI生成总结失败: {e}")
            return self._basic_summarize(messages)

    def onMsg(self, msg: WxMsg) -> int:
        try:
            self.LOG.info(msg)
            self.processMsg(msg)
        except Exception as e:
            self.LOG.error(e)

        return 0

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
            return

        news = News().get_important_news()
        for r in receivers:
            self.sendTextMsg(news, r)

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
            self.LOG.info(f"发送决斗消息 To {receiver}: {msg[:20]}...")
            self.wcf.send_text(f"{msg}", receiver, "")
        except Exception as e:
            self.LOG.error(f"发送决斗消息失败: {e}")

    def run_duel(self, challenger_name, opponent_name, receiver, is_group=False):
        """在单独线程中运行决斗
        
        Args:
            challenger_name: 挑战者名称
            opponent_name: 对手名称
            receiver: 消息接收者(群id或者个人wxid)
            is_group: 是否是群聊
        """
        try:
            # 确保只在群聊中运行决斗
            if not is_group:
                self.sendDuelMsg("❌ 决斗功能只支持群聊", receiver)
                return
                
            # 开始决斗
            self.sendDuelMsg("⚔️ 决斗即将开始，请稍等...", receiver)
            # 传递群组ID参数
            group_id = receiver
            duel_steps = start_duel(challenger_name, opponent_name, group_id, True)  # challenger_name是发起者
            
            # 逐步发送决斗过程
            for step in duel_steps:
                self.sendDuelMsg(step, receiver)
                time.sleep(1.5)  # 每步之间添加适当延迟
        except Exception as e:
            self.LOG.error(f"决斗过程中发生错误: {e}")
            self.sendDuelMsg(f"决斗过程中发生错误: {e}", receiver)
        finally:
            # 释放决斗线程
            with self._duel_lock:
                self._duel_thread = None
            self.LOG.info("决斗线程已结束并销毁")
    
    def start_duel_thread(self, challenger_name, opponent_name, receiver, is_group=False):
        """启动决斗线程
        
        Args:
            challenger_name: 挑战者名称
            opponent_name: 对手名称
            receiver: 消息接收者
            is_group: 是否是群聊
            
        Returns:
            bool: 是否成功启动决斗线程
        """
        with self._duel_lock:
            if self._duel_thread is not None and self._duel_thread.is_alive():
                return False
            
            self._duel_thread = Thread(
                target=self.run_duel,
                args=(challenger_name, opponent_name, receiver, is_group),
                daemon=True
            )
            self._duel_thread.start()
            return True

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
        with self._perplexity_lock:
            active_threads = []
            for thread_key, thread in self._perplexity_threads.items():
                if thread.is_alive():
                    active_threads.append(thread_key)
                    
            if active_threads:
                self.LOG.info(f"等待{len(active_threads)}个Perplexity线程结束: {active_threads}")
                
                # 等待所有线程结束，但最多等待10秒
                for i in range(10):
                    active_count = 0
                    for thread_key, thread in self._perplexity_threads.items():
                        if thread.is_alive():
                            active_count += 1
                    
                    if active_count == 0:
                        break
                        
                    time.sleep(1)
                
                # 记录未能结束的线程
                still_active = [thread_key for thread_key, thread in self._perplexity_threads.items() if thread.is_alive()]
                if still_active:
                    self.LOG.warning(f"以下Perplexity线程在退出时仍在运行: {still_active}")
            
            # 清空线程字典
            self._perplexity_threads.clear()
            self.LOG.info("Perplexity线程管理已清理")

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

# 添加Perplexity处理线程类
class PerplexityThread(Thread):
    """处理Perplexity请求的线程"""
    
    def __init__(self, perplexity_instance, prompt, chat_id, robot, receiver, at_user=None):
        """初始化Perplexity处理线程
        
        Args:
            perplexity_instance: Perplexity实例
            prompt: 查询内容
            chat_id: 聊天ID
            robot: Robot实例，用于发送消息
            receiver: 接收消息的ID
            at_user: 被@的用户ID
        """
        super().__init__(daemon=True)
        self.perplexity = perplexity_instance
        self.prompt = prompt
        self.chat_id = chat_id
        self.robot = robot
        self.receiver = receiver
        self.at_user = at_user
        self.LOG = logging.getLogger("PerplexityThread")
        
        # 检查是否使用reasoning模型
        self.is_reasoning_model = False
        if hasattr(self.perplexity, 'config'):
            model_name = self.perplexity.config.get('model', 'sonar').lower()
            self.is_reasoning_model = 'reasoning' in model_name
            self.LOG.info(f"Perplexity使用模型: {model_name}, 是否为reasoning模型: {self.is_reasoning_model}")
        
    def run(self):
        """线程执行函数"""
        try:
            self.LOG.info(f"开始处理Perplexity请求: {self.prompt[:30]}...")
            
            # 获取回答
            response = self.perplexity.get_answer(self.prompt, self.chat_id)
            
            # 处理sonar-reasoning和sonar-reasoning-pro模型的<think>标签
            if response:
                # 只有对reasoning模型才应用清理逻辑
                if self.is_reasoning_model:
                    response = self.remove_thinking_content(response)
                
                # 移除Markdown格式符号
                response = self.remove_markdown_formatting(response)
                
                self.robot.sendTextMsg(response, self.receiver, self.at_user)
            else:
                self.robot.sendTextMsg("无法从Perplexity获取回答", self.receiver, self.at_user)
                
            self.LOG.info(f"Perplexity请求处理完成: {self.prompt[:30]}...")
            
        except Exception as e:
            self.LOG.error(f"处理Perplexity请求时出错: {e}")
            self.robot.sendTextMsg(f"处理请求时出错: {e}", self.receiver, self.at_user)
        finally:
            # 从活动线程列表中移除
            if hasattr(self.robot, '_perplexity_threads'):
                thread_key = f"{self.receiver}_{self.chat_id}"
                if thread_key in self.robot._perplexity_threads:
                    del self.robot._perplexity_threads[thread_key]
    
    def remove_thinking_content(self, text):
        """移除<think></think>标签之间的思考内容
        
        Args:
            text: 原始响应文本
            
        Returns:
            str: 处理后的文本
        """
        try:
            # 检查是否包含思考标签
            has_thinking = '<think>' in text or '</think>' in text
            
            if has_thinking:
                self.LOG.info("检测到思考内容标签，准备移除...")
                
                # 导入正则表达式库
                import re
                
                # 移除不完整的标签对情况
                if text.count('<think>') != text.count('</think>'):
                    self.LOG.warning(f"检测到不匹配的思考标签: <think>数量={text.count('<think>')}, </think>数量={text.count('</think>')}")
                
                # 提取思考内容用于日志记录
                thinking_pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL)
                thinking_matches = thinking_pattern.findall(text)
                
                if thinking_matches:
                    for i, thinking in enumerate(thinking_matches):
                        short_thinking = thinking[:100] + '...' if len(thinking) > 100 else thinking
                        self.LOG.debug(f"思考内容 #{i+1}: {short_thinking}")
                
                # 替换所有的<think>...</think>内容 - 使用非贪婪模式
                cleaned_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
                
                # 处理不完整的标签
                cleaned_text = re.sub(r'<think>.*?$', '', cleaned_text, flags=re.DOTALL)  # 处理未闭合的开始标签
                cleaned_text = re.sub(r'^.*?</think>', '', cleaned_text, flags=re.DOTALL)  # 处理未开始的闭合标签
                
                # 处理可能的多余空行
                cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
                
                # 移除前后空白
                cleaned_text = cleaned_text.strip()
                
                self.LOG.info(f"思考内容已移除，原文本长度: {len(text)} -> 清理后: {len(cleaned_text)}")
                
                # 如果清理后文本为空，返回一个提示信息
                if not cleaned_text:
                    return "回答内容为空，可能是模型仅返回了思考过程。请重新提问。"
                
                return cleaned_text
            else:
                return text  # 没有思考标签，直接返回原文本
                
        except Exception as e:
            self.LOG.error(f"清理思考内容时出错: {e}")
            return text  # 出错时返回原始文本
            
    def remove_markdown_formatting(self, text):
        """移除Markdown格式符号，如*和#
        
        Args:
            text: 包含Markdown格式的文本
            
        Returns:
            str: 移除Markdown格式后的文本
        """
        try:
            # 导入正则表达式库
            import re
            
            self.LOG.info("开始移除Markdown格式符号...")
            
            # 保存原始文本长度
            original_length = len(text)
            
            # 移除标题符号 (#)
            # 替换 # 开头的标题，保留文本内容
            cleaned_text = re.sub(r'^\s*#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
            
            # 移除强调符号 (*)
            # 替换 **粗体** 和 *斜体* 格式，保留文本内容
            cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned_text)
            cleaned_text = re.sub(r'\*(.*?)\*', r'\1', cleaned_text)
            
            self.LOG.info(f"Markdown格式符号已移除，原文本长度: {original_length} -> 清理后: {len(cleaned_text)}")
            
            return cleaned_text
            
        except Exception as e:
            self.LOG.error(f"移除Markdown格式符号时出错: {e}")
            return text  # 出错时返回原始文本
