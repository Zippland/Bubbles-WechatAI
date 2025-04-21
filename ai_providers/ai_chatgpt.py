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

    def get_answer(self, question: str, wxid: str) -> str:
        # wxid或者roomid,个人时为微信id，群消息时为群id
        self.updateMessage(wxid, question, "user")
        rsp = ""
        try:
            # o系列模型不支持自定义temperature，只能使用默认值1
            params = {
                "model": self.model,
                "messages": self.conversation_list[wxid]
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

    def updateMessage(self, wxid: str, question: str, role: str) -> None:
        now_time = str(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        time_mk = "当需要回答时间时请直接参考回复:"
        # 初始化聊天记录,组装系统信息
        if wxid not in self.conversation_list.keys():
            question_ = [
                self.system_content_msg,
                {"role": "system", "content": "" + time_mk + now_time}
            ]
            self.conversation_list[wxid] = question_

        # 当前问题
        content_question_ = {"role": role, "content": question}
        self.conversation_list[wxid].append(content_question_)

        for cont in self.conversation_list[wxid]:
            if cont["role"] != "system":
                continue
            if cont["content"].startswith(time_mk):
                cont["content"] = time_mk + now_time

        # 只存储10条记录，超过滚动清除
        i = len(self.conversation_list[wxid])
        if i > 10:
            print("滚动清除微信记录：" + wxid)
            # 删除多余的记录，倒着删，且跳过第一个的系统消息
            del self.conversation_list[wxid][1]


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
