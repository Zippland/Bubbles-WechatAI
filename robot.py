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

        if ChatType.is_in_chat_types(chat_type):
            if chat_type == ChatType.TIGER_BOT.value and TigerBot.value_check(self.config.TIGERBOT):
                self.chat = TigerBot(self.config.TIGERBOT)
            elif chat_type == ChatType.CHATGPT.value and ChatGPT.value_check(self.config.CHATGPT):
                self.chat = ChatGPT(self.config.CHATGPT)
            elif chat_type == ChatType.XINGHUO_WEB.value and XinghuoWeb.value_check(self.config.XINGHUO_WEB):
                self.chat = XinghuoWeb(self.config.XINGHUO_WEB)
            elif chat_type == ChatType.CHATGLM.value and ChatGLM.value_check(self.config.CHATGLM):
                self.chat = ChatGLM(self.config.CHATGLM)
            elif chat_type == ChatType.BardAssistant.value and BardAssistant.value_check(self.config.BardAssistant):
                self.chat = BardAssistant(self.config.BardAssistant)
            elif chat_type == ChatType.ZhiPu.value and ZhiPu.value_check(self.config.ZhiPu):
                self.chat = ZhiPu(self.config.ZhiPu)
            elif chat_type == ChatType.OLLAMA.value and Ollama.value_check(self.config.OLLAMA):
                self.chat = Ollama(self.config.OLLAMA)
            elif chat_type == ChatType.DEEPSEEK.value and DeepSeek.value_check(self.config.DEEPSEEK):
                self.chat = DeepSeek(self.config.DEEPSEEK)
            elif chat_type == ChatType.PERPLEXITY.value and Perplexity.value_check(self.config.PERPLEXITY):
                self.chat = Perplexity(self.config.PERPLEXITY)
            else:
                self.LOG.warning("未配置模型")
                self.chat = None
        else:
            if TigerBot.value_check(self.config.TIGERBOT):
                self.chat = TigerBot(self.config.TIGERBOT)
            elif ChatGPT.value_check(self.config.CHATGPT):
                self.chat = ChatGPT(self.config.CHATGPT)
            elif Ollama.value_check(self.config.OLLAMA):
                self.chat = Ollama(self.config.OLLAMA)
            elif XinghuoWeb.value_check(self.config.XINGHUO_WEB):
                self.chat = XinghuoWeb(self.config.XINGHUO_WEB)
            elif ChatGLM.value_check(self.config.CHATGLM):
                self.chat = ChatGLM(self.config.CHATGLM)
            elif BardAssistant.value_check(self.config.BardAssistant):
                self.chat = BardAssistant(self.config.BardAssistant)
            elif ZhiPu.value_check(self.config.ZhiPu):
                self.chat = ZhiPu(self.config.ZhiPu)
            elif DeepSeek.value_check(self.config.DEEPSEEK):
                self.chat = DeepSeek(self.config.DEEPSEEK)
            elif Perplexity.value_check(self.config.PERPLEXITY):
                self.chat = Perplexity(self.config.PERPLEXITY)
            else:
                self.LOG.warning("未配置模型")
                self.chat = None

        self.LOG.info(f"已选择: {self.chat}")

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
            "▶️ 决斗排行/排行榜 - 查看决斗排行榜",
            "▶️ 我的战绩/决斗战绩 - 查看自己的决斗战绩",
            "▶️ 改名 旧名 新名 - 修改自己的昵称",
            "",
            "",
            "【成语】",
            "▶️ #成语 - 接龙",
            "▶️ ?成语 - 查询成语释义",
            "",
            "【其他】",
            "▶️ info/帮助/指令 - 显示此帮助信息",
            "▶️ 直接@机器人 - 进行对话"
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
        
        content = re.sub(r"@.*?[\u2005|\s]", "", msg.content).replace(" ", "")
        
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
        self.LOG.info(f"决斗检测 - 原始内容: {msg.content}, 处理后内容: {content}, 匹配结果: {duel_match}")
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
            rank_list = get_rank_list(10, msg.roomid)  # 传递群ID
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
                        self.sendTextMsg("Perplexity服务未配置", msg.roomid, msg.sender)
                        return True
                
                # 使用现有的chat实例如果它是Perplexity
                perplexity_instance = self.perplexity if hasattr(self, 'perplexity') else (self.chat if isinstance(self.chat, Perplexity) else None)
                
                if perplexity_instance:
                    self.sendTextMsg("正在查询Perplexity，请稍候...", msg.roomid, msg.sender)
                    response = perplexity_instance.get_answer(prompt, msg.roomid if msg.from_group() else msg.sender)
                    if response:
                        self.sendTextMsg(response, msg.roomid, msg.sender)
                        return True
                    else:
                        self.sendTextMsg("无法从Perplexity获取回答", msg.roomid, msg.sender)
                        return True
                else:
                    self.sendTextMsg("Perplexity服务未配置", msg.roomid, msg.sender)
                    return True
            else:
                self.sendTextMsg(f"请在{perplexity_trigger}后面添加您的问题", msg.roomid, msg.sender)
                return True
        
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
            q = re.sub(r"@.*?[\u2005|\s]", "", msg.content).replace(" ", "")
            rsp = self.chat.get_answer(q, (msg.roomid if msg.from_group() else msg.sender))

        if rsp:
            if msg.from_group():
                self.sendTextMsg(rsp, msg.roomid, msg.sender)
            else:
                self.sendTextMsg(rsp, msg.sender)

            return True
        else:
            self.LOG.error(f"无法从 ChatGPT 获得答案")
            return False

    def processMsg(self, msg: WxMsg) -> None:
        """当接收到消息的时候，会调用本方法。如果不实现本方法，则打印原始消息。
        此处可进行自定义发送的内容,如通过 msg.content 关键字自动获取当前天气信息，并发送到对应的群组@发送者
        群号：msg.roomid  微信ID：msg.sender  消息内容：msg.content
        content = "xx天气信息为："
        receivers = msg.roomid
        self.sendTextMsg(content, receivers, msg.sender)
        """

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
                    opponent_name = duel_match.group(1)
                    # 获取发送者昵称
                    sender_name = self.allContacts.get(msg.sender, "挑战者")
                    
                    # 检查并启动决斗线程
                    if not self.start_duel_thread(sender_name, opponent_name, msg.sender, False):
                        self.sendTextMsg("⚠️ 目前有其他决斗正在进行中，请稍后再试！", msg.sender)
                        return True
                    
                    return True
                
                # 决斗排行榜查询
                if msg.content == "决斗排行" or msg.content == "决斗排名" or msg.content == "排行榜":
                    rank_list = get_rank_list(10)  # 私聊不传群ID
                    self.sendTextMsg(rank_list, msg.sender)
                    return
                
                # 个人战绩查询
                stats_match = re.search(r"^(决斗战绩|我的战绩|战绩查询)(.*)$", msg.content)
                if stats_match:
                    player_name = stats_match.group(2).strip()
                    if not player_name:  # 如果没有指定名字，则查询发送者
                        player_name = self.allContacts.get(msg.sender, "未知用户")
                    
                    stats = get_player_stats(player_name)  # 私聊不传群ID
                    self.sendTextMsg(stats, msg.sender)
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
                                self.sendTextMsg("Perplexity服务未配置", msg.sender)
                                return
                        
                        # 使用现有的chat实例如果它是Perplexity
                        perplexity_instance = self.perplexity if hasattr(self, 'perplexity') else (self.chat if isinstance(self.chat, Perplexity) else None)
                        
                        if perplexity_instance:
                            self.sendTextMsg("正在查询Perplexity，请稍候...", msg.sender)
                            response = perplexity_instance.get_answer(prompt, msg.sender)
                            if response:
                                self.sendTextMsg(response, msg.sender)
                                return
                            else:
                                self.sendTextMsg("无法从Perplexity获取回答", msg.sender)
                                return
                        else:
                            self.sendTextMsg("Perplexity服务未配置", msg.sender)
                            return
                    else:
                        self.sendTextMsg(f"请在{perplexity_trigger}后面添加您的问题", msg.sender)
                        return

                self.toChitchat(msg)  # 闲聊

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
            # 开始决斗
            self.sendDuelMsg("⚔️ 决斗即将开始，请稍等...", receiver)
            # 传递群组ID参数，私聊时为None
            group_id = receiver if is_group else None
            duel_steps = start_duel(challenger_name, opponent_name, group_id)
            
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
