#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import base64
import os
from datetime import datetime

import httpx
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI


class ChatGPT():
    def __init__(self, conf: dict) -> None:
        key = conf.get("key")
        api = conf.get("api")
        proxy = conf.get("proxy")
        prompt = conf.get("prompt")
        self.model = conf.get("model", "gpt-3.5-turbo")
        self.LOG = logging.getLogger("ChatGPT")
        if proxy:
            self.client = OpenAI(api_key=key, base_url=api, http_client=httpx.Client(proxy=proxy))
        else:
            self.client = OpenAI(api_key=key, base_url=api)
        self.conversation_list = {}
        self.system_content_msg = {"role": "system", "content": prompt}
        # 确认是否使用支持视觉的模型
        self.support_vision = self.model == "gpt-4-vision-preview" or self.model == "gpt-4o" or "-vision" in self.model

    def __repr__(self):
        return 'ChatGPT'

    @staticmethod
    def value_check(conf: dict) -> bool:
        if conf:
            if conf.get("key") and conf.get("api") and conf.get("prompt"):
                return True
        return False

    def get_answer(self, question: str, wxid: str, system_prompt_override=None) -> str:
        # wxid或者roomid,个人时为微信id，群消息时为群id
        
        # 检查是否是新对话
        is_new_conversation = wxid not in self.conversation_list
        
        # 保存临时系统提示的状态
        temp_system_used = False
        original_prompt = None
        
        if system_prompt_override:
            # 只有新对话才临时修改系统提示
            if is_new_conversation:
                # 临时保存原始系统提示，以便可以恢复
                original_prompt = self.system_content_msg["content"]
                # 设置临时系统提示
                self.system_content_msg["content"] = system_prompt_override
                temp_system_used = True
                self.LOG.debug(f"为新对话 {wxid} 临时设置系统提示")
            else:
                # 对于已存在的对话，我们将在API调用时临时使用覆盖提示，而不修改对话历史
                self.LOG.debug(f"对话 {wxid} 已存在，系统提示覆盖将仅用于本次API调用")
        
        # 添加用户问题到对话历史
        self.updateMessage(wxid, question, "user")
        
        # 如果修改了系统提示，现在恢复它
        if temp_system_used and original_prompt is not None:
            self.system_content_msg["content"] = original_prompt
            self.LOG.debug(f"已恢复默认系统提示")
        
        rsp = ""
        try:
            # 准备API调用的消息列表
            api_messages = []
            
            # 对于已存在的对话，临时应用系统提示覆盖（如果有）
            if not is_new_conversation and system_prompt_override:
                # 第一个消息可能是系统提示
                has_system = self.conversation_list[wxid][0]["role"] == "system"
                
                # 使用临时系统提示替代原始系统提示
                if has_system:
                    # 复制除了系统提示外的所有消息
                    api_messages = [{"role": "system", "content": system_prompt_override}]
                    api_messages.extend(self.conversation_list[wxid][1:])
                else:
                    # 如果没有系统提示，添加一个
                    api_messages = [{"role": "system", "content": system_prompt_override}]
                    api_messages.extend(self.conversation_list[wxid])
            else:
                # 对于新对话或没有临时系统提示的情况，使用原始对话历史
                api_messages = self.conversation_list[wxid]
            
            # o系列模型不支持自定义temperature，只能使用默认值1
            params = {
                "model": self.model,
                "messages": api_messages
            }
            
            # 只有非o系列模型才设置temperature
            if not self.model.startswith("o"):
                params["temperature"] = 0.2
                
            ret = self.client.chat.completions.create(**params)
            rsp = ret.choices[0].message.content
            rsp = rsp[2:] if rsp.startswith("\n\n") else rsp
            rsp = rsp.replace("\n\n", "\n")
            self.updateMessage(wxid, rsp, "assistant")
        except AuthenticationError:
            self.LOG.error("OpenAI API 认证失败，请检查 API 密钥是否正确")
        except APIConnectionError:
            self.LOG.error("无法连接到 OpenAI API，请检查网络连接")
        except APIError as e1:
            self.LOG.error(f"OpenAI API 返回了错误：{str(e1)}")
            rsp = "无法从 ChatGPT 获得答案"
        except Exception as e0:
            self.LOG.error(f"发生未知错误：{str(e0)}")
            rsp = "无法从 ChatGPT 获得答案"

        return rsp

    def encode_image_to_base64(self, image_path: str) -> str:
        """将图片文件转换为Base64编码

        Args:
            image_path (str): 图片文件路径

        Returns:
            str: Base64编码的图片数据
        """
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            self.LOG.error(f"图片编码失败: {str(e)}")
            return ""

    def get_image_description(self, image_path: str, prompt: str = "请详细描述这张图片中的内容") -> str:
        """使用GPT-4 Vision分析图片内容

        Args:
            image_path (str): 图片文件路径
            prompt (str, optional): 提示词. 默认为"请详细描述这张图片中的内容"

        Returns:
            str: 模型对图片的描述
        """
        if not self.support_vision:
            self.LOG.error(f"当前模型 {self.model} 不支持图片理解，请使用gpt-4-vision-preview或gpt-4o")
            return "当前模型不支持图片理解功能，请联系管理员配置支持视觉的模型（如gpt-4-vision-preview或gpt-4o）"
            
        if not os.path.exists(image_path):
            self.LOG.error(f"图片文件不存在: {image_path}")
            return "无法读取图片文件"
            
        try:
            base64_image = self.encode_image_to_base64(image_path)
            if not base64_image:
                return "图片编码失败"
                
            # 构建带有图片的消息
            messages = [
                {"role": "system", "content": "你是一个图片分析专家，擅长分析图片内容并提供详细描述。"},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
            
            # 使用GPT-4 Vision模型
            params = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 1000  # 限制输出长度
            }
            
            # 支持视觉的模型可能有不同参数要求
            if not self.model.startswith("o"):
                params["temperature"] = 0.7
                
            response = self.client.chat.completions.create(**params)
            description = response.choices[0].message.content
            description = description[2:] if description.startswith("\n\n") else description
            description = description.replace("\n\n", "\n")
            
            return description
            
        except AuthenticationError:
            self.LOG.error("OpenAI API 认证失败，请检查 API 密钥是否正确")
            return "API认证失败，无法分析图片"
        except APIConnectionError:
            self.LOG.error("无法连接到 OpenAI API，请检查网络连接")
            return "网络连接错误，无法分析图片"
        except APIError as e1:
            self.LOG.error(f"OpenAI API 返回了错误：{str(e1)}")
            return f"API错误：{str(e1)}"
        except Exception as e0:
            self.LOG.error(f"分析图片时发生未知错误：{str(e0)}")
            return f"处理图片时出错：{str(e0)}"

    def updateMessage(self, wxid: str, content: str, role: str) -> None:
        now_time = str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        time_mk = "当需要回答时间时请直接参考回复:"
        # 初始化聊天记录,组装系统信息
        if wxid not in self.conversation_list.keys():
            # 此时self.system_content_msg可能已经被get_answer临时修改
            # 但这没关系，因为在get_answer结束前会恢复
            question_ = [
                self.system_content_msg,
                {"role": "system", "content": "" + time_mk + now_time}
            ]
            self.conversation_list[wxid] = question_

        # 当前问题或回答
        content_message = {"role": role, "content": content}
        self.conversation_list[wxid].append(content_message)

        # 更新时间标记
        for cont in self.conversation_list[wxid]:
            if cont["role"] != "system":
                continue
            if cont["content"].startswith(time_mk):
                cont["content"] = time_mk + now_time

        # 控制对话历史长度
        # 只存储10条记录，超过滚动清除
        max_history = 12  # 包括1个系统提示和1个时间标记
        i = len(self.conversation_list[wxid])
        if i > max_history:
            # 计算需要删除多少条记录
            if self.conversation_list[wxid][0]["role"] == "system" and self.conversation_list[wxid][1]["role"] == "system":
                # 如果前两条都是系统消息，保留它们，删除较早的用户和助手消息
                to_delete = i - max_history
                del self.conversation_list[wxid][2:2+to_delete]
                self.LOG.debug(f"滚动清除微信记录：{wxid}，删除了{to_delete}条历史消息")
            else:
                # 如果结构不符合预期，简单地保留最近的消息
                self.conversation_list[wxid] = self.conversation_list[wxid][-max_history:]
                self.LOG.debug(f"滚动清除微信记录：{wxid}，只保留最近{max_history}条消息")


if __name__ == "__main__":
    from configuration import Config
    config = Config().CHATGPT
    if not config:
        exit(0)

    chat = ChatGPT(config)

    while True:
        q = input(">>> ")
        try:
            time_start = datetime.now()  # 记录开始时间
            print(chat.get_answer(q, "wxid"))
            time_end = datetime.now()  # 记录结束时间

            print(f"{round((time_end - time_start).total_seconds(), 2)}s")  # 计算的时间差为程序的执行时间，单位为秒/s
        except Exception as e:
            print(e)
