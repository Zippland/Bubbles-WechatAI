# Bubbles-WechatAI

![版本](https://img.shields.io/badge/版本-39.2.4.0-blue)
![Python](https://img.shields.io/badge/Python-3.8+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 📝 项目简介

Bubbles-WechatAI 是一个功能丰富的微信机器人框架，基于 [wcferry](https://github.com/lich0821/wcferry) 开发，支持接入多种大型语言模型（LLM），提供丰富的交互功能和定时任务。该项目旨在将微信客户端转变为一个智能的个人助手，可以执行多种实用功能，带来便捷的用户体验。

## ✨ 核心特性

### 🤖 多 AI 模型支持
- 支持多种主流 AI 大模型：
  - OpenAI (ChatGPT)
  - Google Gemini
  - 智谱 AI (ChatGLM)
  - 科大讯飞星火大模型
  - 阿里云通义千问
  - TigerBot
  - DeepSeek
  - Perplexity
  - Ollama (本地部署的模型)

### 🔄 灵活的模型配置
- 支持为不同的群聊和私聊设置不同的 AI 模型
- 可以通过命令行参数或配置文件设置默认模型

### 🎮 丰富的命令系统
- 强大的命令路由系统，支持自定义命令及参数
- 预设多种实用和娱乐命令

### 🎨 AI 图像生成
- 支持调用多种 AI 绘图模型生成图片

### ⏰ 定时任务
- 每日天气预报推送
- 每日新闻资讯推送
- 工作日报/周报/月报提醒

### 🎲 娱乐功能
- 决斗游戏系统（含排行榜、玩家统计、偷袭等）
- 成语接龙
- 古灵阁妖精馈赠（随机事件系统）

### 📊 对话管理
- 智能消息总结功能
- 处理各类微信消息（文本、图片、小程序、链接等）

### 🔧 实用工具
- 自动接受好友请求并打招呼
- 自动响应群聊和私聊消息

## 🛠️ 安装指南

### 系统要求
- Python 3.8 或更高版本
- Windows 操作系统（wcferry 要求）
- 微信 PC 版客户端

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/yourusername/Bubbles-WechatAI.git
   cd Bubbles-WechatAI
   ```

2. **创建并激活虚拟环境（可选但推荐）**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **安装 wcferry 服务**

   请参考 [wcferry 官方文档](https://github.com/lich0821/wcferry) 安装并启动 wcferry 服务。

5. **配置项目**
   ```bash
   # 复制配置模板
   cp config.yaml.template config.yaml
   
   # 编辑配置文件，填入您的 API 密钥等信息
   notepad config.yaml
   ```

## ⚙️ 配置说明

配置文件 `config.yaml` 包含以下主要部分：

### AI 模型配置

每个 AI 模型都有自己的配置部分，例如：

```yaml
# ChatGPT 配置
CHATGPT:
  key: "your-openai-api-key"
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o-mini"  # 可选：gpt-4, gpt-3.5-turbo 等
  temperature: 0.7
  max_tokens: 2000
  system_prompt: "你是一个有用的助手。"
  proxy: "http://127.0.0.1:7890"  # 可选：如需代理请填写
```

### 群组/私聊模型映射

您可以为不同的群聊或私聊指定不同的 AI 模型：

```yaml
# 群组模型配置
GROUP_MODELS:
  # 默认模型 ID
  default: 1  # 1 代表 CHATGPT
  
  # 群聊模型映射
  mapping:
    - room_id: "12345678@chatroom"  # 群聊 ID
      model: 2  # 2 代表 Gemini
  
  # 私聊模型映射
  private_mapping:
    - wxid: "wxid_abc123"  # 用户 wxid
      model: 3  # 3 代表 ChatGLM
```

### 功能开关

您可以启用或禁用各种功能：

```yaml
# 功能开关
FEATURES:
  news_report: true
  weather_report: true
  auto_accept_friend: true
  duel_game: true
  image_generation: true
```

## 🚀 使用方法

### 启动机器人

```bash
# 使用默认配置启动
python main.py

# 指定默认 AI 模型 ID 启动
python main.py -c 1  # 使用 ID 为 1 的模型（如 ChatGPT）
```

### 可用命令

机器人支持多种命令，以下是一些常用命令示例：

#### 基础命令
- `/help` - 显示帮助信息
- `/model` - 查看当前使用的 AI 模型
- `/switch <模型ID>` - 切换当前会话的 AI 模型

#### AI 对话
- `/ai <问题>` - 向 AI 提问
- `/clear` - 清除当前对话历史
- `/summary` - 获取对话总结

#### 图片生成
- `/draw <提示词>` - 生成 AI 图片

#### 实用工具
- `/weather <城市>` - 查询指定城市天气
- `/news` - 获取今日新闻

#### 娱乐功能
- `/duel <@用户>` - 邀请用户进行决斗
- `/rank` - 查看决斗排行榜
- `/stats` - 查看个人决斗统计
- `/chengyu <成语>` - 成语接龙

## 🎮 游戏功能详解

### 决斗系统

Bubbles-WechatAI 内置了一个有趣的决斗游戏系统，用户可以在群聊中挑战其他成员：

- **开始决斗**：使用 `/duel @用户` 开始一场决斗
- **查看排名**：使用 `/rank` 查看全服决斗排行榜
- **个人统计**：使用 `/stats` 查看个人决斗数据
- **更改名称**：使用 `/rename <新名称>` 更改自己在决斗系统中的显示名称
- **偷袭**：有概率触发随机偷袭事件

### 古灵阁妖精馈赠

这是一个随机事件系统，机器人会在聊天中随机触发"古灵阁妖精馈赠"事件，为用户提供惊喜奖励。

## 📋 项目结构

```
Bubbles-WechatAI/
├── ai_providers/       # AI 模型接口实现
├── commands/           # 命令系统实现
├── data/               # 数据文件
├── function/           # 功能模块
│   ├── func_chengyu.py     # 成语功能
│   ├── func_duel.py        # 决斗功能
│   ├── func_news.py        # 新闻功能
│   ├── func_weather.py     # 天气功能
│   └── ...
├── image/              # 图像生成相关
├── logs/               # 日志目录
├── config.yaml         # 配置文件
├── config.yaml.template # 配置模板
├── constants.py        # 常量定义
├── main.py             # 入口文件
├── robot.py            # 机器人核心实现
└── requirements.txt    # 项目依赖
```

## 🤝 贡献指南

欢迎对本项目做出贡献！您可以通过以下方式参与：

1. **报告问题**：提交 issue 报告 bug 或提出功能建议
2. **提交代码**：通过 Pull Request 提交您的改进
3. **完善文档**：帮助改进项目文档

## 📄 许可证

本项目采用 MIT 许可证，详情请参阅 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [wcferry](https://github.com/lich0821/wcferry) - 提供微信机器人底层支持
- 所有贡献者和用户

## ❓ 常见问题

**Q: 如何获取群聊 ID？**
A: 在群聊中发送一条消息，机器人日志会显示该消息的来源群聊 ID。

**Q: 如何添加新的 AI 模型？**
A: 在 `ai_providers` 目录下创建新的模型接口实现，然后在 `robot.py` 中注册该模型。

**Q: 出现 "AI 模型未响应" 错误怎么办？**
A: 检查相应 AI 模型的 API 密钥配置和网络连接，确保 API 可访问。

**Q: 机器人不回复消息怎么办？**
A: 检查 wcferry 服务是否正常运行，查看日志文件了解详细错误信息。

## 📞 联系方式

如有任何问题或建议，请通过以下方式联系我们：

- GitHub Issues: [提交问题](https://github.com/yourusername/Bubbles-WechatAI/issues)
- Email: youremail@example.com

---

**注意**：本项目仅供学习和个人使用，请遵守微信使用条款，不要用于任何违反法律法规的活动。
