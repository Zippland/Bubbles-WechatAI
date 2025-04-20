# Bubbles - 多功能微信聊天助手

一个功能强大、高度可定制的微信机器人，基于 [WeChatFerry](https://github.com/lich0821/WeChatFerry) 开发，支持多种AI大模型、文生图、游戏互动等功能。

<p align="center">
  <img src="https://github.com/Zippland/Bubbles-WechatAI/assets/yourID/raw/main/assets/logo.png" alt="Bubbles Logo" width="200">
</p>

## ✨ 主要功能

### 🤖 多模型AI聊天
- 支持多种大语言模型：
  - ChatGPT
  - Google Gemini
  - 智谱AI
  - 讯飞星火
  - TigerBot
  - ChatGLM
  - Ollama（本地模型）
  - DeepSeek
  - Perplexity

### 🎨 文生图功能
- 支持多个文生图服务：
  - 智谱CogView
  - 阿里云文生图
  - Google Gemini文生图

### 🎮 互动游戏
- 成语接龙：根据尾字自动接龙
- 模拟决斗：支持玩家间进行虚拟对战，记录排名

### ⏰ 定时任务
- 每日天气预报
- 每日新闻推送
- 工作日报/周报提醒

### 🔄 消息管理
- 群聊消息总结
- 对话记忆和重置
- 动态切换AI模型

## 🚀 快速开始

### 环境要求
- Python 3.9+ (推荐3.10，不建议使用Python 3.12)
- 支持的微信版本：请参考[WeChatFerry发布页](https://github.com/lich0821/WeChatFerry/releases/latest)获取兼容版本

### 安装步骤

1. 克隆仓库
```bash
git clone https://github.com/Zippland/Bubbles-WechatAI.git
cd Bubbles-WechatAI
```

2. 安装依赖
```bash
# 升级pip
python -m pip install -U pip

# 安装依赖包
pip install -r requirements.txt

# 如果网络不稳定，可使用国内镜像
pip install -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt

# 使用ChatGLM需安装kernel
ipython kernel install --name chatglm3 --user
```

3. 首次运行生成配置文件
```bash
python main.py
# 此时会在项目目录下生成config.yaml配置文件
```

4. 修改配置文件
打开`config.yaml`，配置以下关键项：
- 允许响应的群聊ID
- AI模型API密钥和设置
- 文生图服务配置
- 定时任务接收者

5. 正式运行
```bash
# 使用默认配置运行
python main.py

# 指定使用特定AI模型运行
python main.py -c 模型编号
```

模型编号对应关系：
- 1: TigerBot
- 2: ChatGPT
- 3: 讯飞星火
- 4: ChatGLM
- 5: Google Gemini
- 6: 智谱AI
- 7: Ollama
- 8: DeepSeek
- 9: Perplexity

## 📝 配置说明

### 群聊配置
```yaml
groups:
  enable: [] # 允许响应的群聊ID，例如：2xxxxxxxxx3@chatroom,1xxxxxxxxx4@chatroom
```

### AI模型配置示例
```yaml
chatgpt:
  key: sk-xxxxxxxxxxxx  # OpenAI API密钥
  api: https://api.openai.com/v1
  proxy: http://127.0.0.1:7890  # 可选，代理设置
  prompt: 你是智能聊天机器人，你叫Bubbles  # 角色设定

bard:
  api_key: xx-xxxxxxxxx  # Google API密钥
  model_name: gemini-pro
  proxy: http://127.0.0.1:7890
  prompt: You are Bubbles, a helpful AI assistant

# 其他模型配置类似...
```

### 文生图配置
```yaml
cogview:
  enable: true  # 是否启用智谱文生图
  key: xxxxxxxxx  # API密钥
  fallback_to_chat: true  # 未启用时是否回退到聊天模型

aliyun_image:
  enable: false
  access_key_id: xxxx
  access_key_secret: xxxx
  model: wanx2.1-t2i  # 可选模型类型
```

## 🎯 使用指南

### 基础命令
- `@机器人 help` - 显示帮助信息
- `@机器人 [问题]` - 向AI提问
- `@机器人 画图 [提示词]` - 生成图片
- `@机器人 重置会话` - 清除对话历史
- `@机器人 切换模型 [编号]` - 动态切换AI模型

### 互动游戏
- `@机器人 决斗 @某人` - 发起决斗
- `@机器人 接受 @发起者` - 接受决斗
- `@机器人 拒绝 @发起者` - 拒绝决斗
- `@机器人 排名` - 查看决斗排名
- `@机器人 战绩` - 查看个人战绩
- `@机器人 改名 [新名字]` - 修改决斗昵称

### 高级功能
- `@机器人 总结` - 总结群聊最近消息
- `/thread` 或 `/话题` - 创建新的Perplexity对话线程
- `/end` 或 `/结束` - 结束当前Perplexity对话
- `/clear` 或 `/清除` - 清除所有Perplexity对话

## 📋 项目结构

```
Bubbles-WechatAI/
├── base/               # 基础功能模块
│   ├── func_bard.py    # Google Bard/Gemini API
│   ├── func_chatgpt.py # ChatGPT API
│   ├── func_chatglm.py # ChatGLM API
│   └── ...
├── image/              # 文生图相关模块
│   ├── cogview.py      # 智谱CogView实现
│   ├── aliyun_image.py # 阿里云文生图实现
│   └── gemini_image.py # Gemini文生图实现
├── config/             # 配置文件目录
├── constants.py        # 常量定义
├── configuration.py    # 配置加载
├── main.py             # 主入口文件
├── robot.py            # 机器人核心逻辑
└── requirements.txt    # 依赖包列表
```

## 🤝 贡献指南

欢迎提交Pull Request或Issue来帮助改进项目！

## 📜 许可证

[MIT License](LICENSE)

## 🙏 鸣谢

- [WeChatFerry](https://github.com/lich0821/WeChatFerry) - 提供微信通信能力
- [ChatGPT](https://openai.com/) - AI对话能力
- [Google Gemini](https://deepmind.google/technologies/gemini/) - AI对话和图像生成
- 以及所有其他依赖的开源项目

---

> 本项目仅供学习和研究使用，请勿用于非法用途。作者不对使用本项目产生的任何后果负责。
