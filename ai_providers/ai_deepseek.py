#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
from datetime import datetime

import httpx
from openai import APIConnectionError, APIError, AuthenticationError, OpenAI


class DeepSeek():
    def __init__(self, conf: dict) -> None:
        key = conf.get("key")
        api = conf.get("api", "https://api.deepseek.com")
        proxy = conf.get("proxy")
        prompt = conf.get("prompt")
        self.model = conf.get("model", "deepseek-chat")
        self.LOG = logging.getLogger("DeepSeek")
        
        self.reasoning_supported = (self.model == "deepseek-reasoner")
        
        if conf.get("enable_reasoning", False) and not self.reasoning_supported:
            self.LOG.warning("思维链功能只在使用 deepseek-reasoner 模型时可用，当前模型不支持此功能")
        
        self.enable_reasoning = conf.get("enable_reasoning", False) and self.reasoning_supported
        self.show_reasoning = conf.get("show_reasoning", False) and self.enable_reasoning
        
        if proxy:
            self.client = OpenAI(api_key=key, base_url=api, http_client=httpx.Client(proxy=proxy))
        else:
            self.client = OpenAI(api_key=key, base_url=api)
        
        self.conversation_list = {}
        
        self.system_content_msg = {"role": "system", "content": prompt}
        
    def __repr__(self):
        return 'DeepSeek'

    @staticmethod
    def value_check(conf: dict) -> bool:
        if conf:
            if conf.get("key") and conf.get("prompt"):
                return True
        return False

    def get_answer(self, question: str, wxid: str, system_prompt_override=None) -> str:
        if question == "#清除对话":
            if wxid in self.conversation_list.keys():
                del self.conversation_list[wxid]
            return "已清除上下文"
        
        if question.lower() in ["#开启思维链", "#enable reasoning"]:
            if not self.reasoning_supported:
                return "当前模型不支持思维链功能，请使用 deepseek-reasoner 模型"
            self.enable_reasoning = True
            self.show_reasoning = True
            return "已开启思维链模式，将显示完整的推理过程"
            
        if question.lower() in ["#关闭思维链", "#disable reasoning"]:
            if not self.reasoning_supported:
                return "当前模型不支持思维链功能，无需关闭"
            self.enable_reasoning = False
            self.show_reasoning = False
            return "已关闭思维链模式"
            
        if question.lower() in ["#隐藏思维链", "#hide reasoning"]:
            if not self.enable_reasoning:
                return "思维链功能未开启，无法设置隐藏/显示"
            self.show_reasoning = False
            return "已设置隐藏思维链，但模型仍会进行深度思考"
            
        if question.lower() in ["#显示思维链", "#show reasoning"]:
            if not self.enable_reasoning:
                return "思维链功能未开启，无法设置隐藏/显示"
            self.show_reasoning = True
            return "已设置显示思维链"
            
        # 初始化对话历史（只在首次时添加系统提示）
        if wxid not in self.conversation_list:
            self.conversation_list[wxid] = []
            # 只有在这里才添加默认的系统提示到对话历史中
            if self.system_content_msg["content"]:
                self.conversation_list[wxid].append(self.system_content_msg)
        
        # 添加用户问题到对话历史
        self.conversation_list[wxid].append({"role": "user", "content": question})

        try:
            # 准备API调用的消息列表
            api_messages = []
            
            # 检查是否需要使用临时系统提示
            if system_prompt_override:
                # 如果提供了临时系统提示，在API调用时使用它（不修改对话历史）
                api_messages.append({"role": "system", "content": system_prompt_override})
                # 添加除了系统提示外的所有历史消息
                for msg in self.conversation_list[wxid]:
                    if msg["role"] != "system":
                        api_messages.append({"role": msg["role"], "content": msg["content"]})
            else:
                # 如果没有临时系统提示，使用完整的对话历史
                for msg in self.conversation_list[wxid]:
                    api_messages.append({"role": msg["role"], "content": msg["content"]})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                stream=False
            )

            if self.reasoning_supported and self.enable_reasoning:
                # deepseek-reasoner模型返回的特殊字段: reasoning_content和content
                # 单独处理思维链模式的响应
                reasoning_content = getattr(response.choices[0].message, "reasoning_content", None)
                content = response.choices[0].message.content

                if self.show_reasoning and reasoning_content:
                    final_response = f"🤔思考过程：\n{reasoning_content}\n\n🎉最终答案：\n{content}"
                    #最好不要删除表情，因为微信内的信息没有办法做自定义显示，这里是为了做两个分隔，来区分思考过程和最终答案！💡
                else:
                    final_response = content
                self.conversation_list[wxid].append({"role": "assistant", "content": content})
            else:
                final_response = response.choices[0].message.content
                self.conversation_list[wxid].append({"role": "assistant", "content": final_response})
            
            # 控制对话长度，保留最近的历史记录
            # 系统消息(如果有) + 最近9轮对话(问答各算一轮)
            max_history = 11
            if len(self.conversation_list[wxid]) > max_history:
                has_system = self.conversation_list[wxid][0]["role"] == "system"
                if has_system:
                    self.conversation_list[wxid] = [self.conversation_list[wxid][0]] + self.conversation_list[wxid][-(max_history-1):]
                else:
                    self.conversation_list[wxid] = self.conversation_list[wxid][-max_history:]
            
            return final_response
                
        except (APIConnectionError, APIError, AuthenticationError) as e1:
            self.LOG.error(f"DeepSeek API 返回了错误：{str(e1)}")
            return f"DeepSeek API 返回了错误：{str(e1)}"
        except Exception as e0:
            self.LOG.error(f"发生未知错误：{str(e0)}")
            return "抱歉，处理您的请求时出现了错误"


if __name__ == "__main__":
    from configuration import Config
    config = Config().DEEPSEEK
    if not config:
        exit(0)

    chat = DeepSeek(config)

    while True:
        q = input(">>> ")
        try:
            time_start = datetime.now()
            print(chat.get_answer(q, "wxid"))
            time_end = datetime.now()
            print(f"{round((time_end - time_start).total_seconds(), 2)}s")
        except Exception as e:
            print(e)
