# Choice Service

[![CI](https://github.com/lxfight/astrbot_plugin_choice_service/actions/workflows/ci.yml/badge.svg)](https://github.com/lxfight/astrbot_plugin_choice_service/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/lxfight/astrbot_plugin_choice_service)](https://github.com/lxfight/astrbot_plugin_choice_service/releases)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![AstrBot](https://img.shields.io/badge/AstrBot-4.28%2B-5B8DEF)](https://github.com/AstrBotDevs/AstrBot)

Choice Service 为 AstrBot 提供通用判断能力。插件通过 System One 协议调用 Jev 或其他兼容判断模型，在给定选项或是非命题中返回结构化结果，可用于主动回复、意图分流、动作选择、回复前审核等场景。

插件不绑定特定服务商。你可以使用内置的 TypeSafe、OpenRouter、Vercel AI Gateway，也可以接入其他兼容 System One 的端点。

## 功能

- **通用单选**：给出一组选项和可选上下文，返回被选中的选项、概率、置信度及完整概率分布。
- **是非判断**：返回 0 到 1 之间的概率，由调用方通过阈值决定最终结果。
- **多服务商**：内置常用端点预设，并支持自定义 `base_url` 与 `model`。
- **跨插件调用**：其他 AstrBot 插件可直接获取 `DecisionService`，无需重复实现模型请求。
- **实时统计**：插件页面展示调用量、成功率、平均延迟、选项分布及最近 30 次判断。
- **多语言界面**：支持简体中文、English、日本語、Русский。

## 环境要求

- AstrBot `>=4.28.0,<5`
- 可访问所选判断服务的网络环境
- 对应服务商的 API Key

## 安装

### 从 GitHub 安装

1. 打开 AstrBot WebUI，进入 **插件**。
2. 点击 **安装插件**，选择 **从链接安装**。
3. 填写仓库地址：`https://github.com/lxfight/astrbot_plugin_choice_service`
4. 安装完成后，确认插件已启用且没有加载错误。

### 从 Release 安装

从 [Releases](https://github.com/lxfight/astrbot_plugin_choice_service/releases/latest) 下载最新的 `astrbot_plugin_choice_service-v*.zip`，然后在 WebUI 中选择 **从文件安装** 并上传。

### 首次配置

打开插件配置，选择服务商并填写 API Key，保存配置后重载插件。默认使用 TypeSafe 与 `jev-latest`，仅填写 API Key 即可开始使用。

## 配置

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `provider` | `typesafe` | 服务商预设：`typesafe`、`openrouter`、`vercel` 或 `custom` |
| `api_key` | 空 | 与所选服务商匹配的 API Key |
| `base_url` | 空 | 留空使用预设；自定义服务商时必须填写完整的 System One 地址 |
| `model` | 空 | 留空使用预设；自定义服务商时必须填写 |
| `language` | `auto` | 聊天回复语言：跟随 AstrBot、`zh-CN`、`en-US`、`ja-JP`、`ru-RU` |
| `timeout_sec` | `10` | 单次请求超时时间，单位为秒 |

### 服务商预设

| 服务商 | 接口地址 | 默认模型 |
| --- | --- | --- |
| TypeSafe | `https://api.typesafe.ai/v1/systemone` | `jev-latest` |
| OpenRouter | `https://openrouter.ai/api/v1/systemone` | `jev-latest` |
| Vercel AI Gateway | `https://ai-gateway.vercel.sh/typesafe/v1/systemone` | `typesafe-ai/jev` |
| 自定义 | 由 `base_url` 指定 | 由 `model` 指定 |

自定义地址必须包含完整的 System One 路径，例如：

```text
https://example.com/v1/systemone
```

仅填写服务根地址或 `/v1` 无法完成判断请求。

## 使用

### 聊天指令

```text
/choose 当前消息是否需要机器人主动回复？ :: 回复 | 等待 | 仅表情
```

指令格式为 `/choose 问题 :: 选项1 | 选项2`，至少提供两个选项。回复内容包括选中项、概率、置信度和请求耗时。

聊天指令只对问题本身进行判断。需要传入消息记录、用户资料或其他上下文时，请通过下方插件 API 调用并设置 `state`。

### 统计页面

在插件详情页打开统计页面，可以查看：

- 总调用次数、成功率、平均延迟
- 单选与是非调用次数
- 各选项的选中分布
- 当前服务商、模型、接口、超时与 API Key 配置状态
- 最近 30 次判断的问题、结果、概率与耗时

统计数据保存在内存中，重载插件或重启 AstrBot 后清零。

## 插件 API

其他插件启用后，可以通过 AstrBot 的插件注册表获取共享服务：

```python
service = self.context.get_registered_star(
    "astrbot_plugin_choice_service"
).star_cls.service
```

### 单选

```python
result = await service.choose(
    "机器人下一步应该做什么？",
    {
        "reply": "直接回复当前消息",
        "wait": "保持沉默，等待更多消息",
        "react": "只添加表情回应",
    },
    state={"messages": recent_messages, "bot_name": "小助手"},
)

if result.choice == "reply":
    await send_reply()
elif result.choice == "react":
    await send_reaction()
```

`options` 也可以是字符串列表：

```python
result = await service.choose(
    "这段文本是什么语气？",
    ["友好", "中性", "敌意"],
    state=text,
)
```

`state` 支持可序列化为 JSON 的文本、对象或数组。返回的 `ChoiceResult` 包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `choice` | `str` | 被选中的原始选项值 |
| `probability` | `float` | 选中项的概率 |
| `confidence` | `float` | 模型给出的置信度 |
| `probabilities` | `dict[str, float]` | 以原始选项值为键的完整概率分布 |
| `model` | `str` | 实际返回结果的模型 |
| `latency_ms` | `int` | 请求耗时，单位为毫秒 |

### 是非判断

```python
decision = await service.yes_no(
    "机器人现在应该主动发言吗？",
    state={"messages": recent_messages, "goal": "参与当前话题"},
    threshold=0.65,
)

if decision.value:
    await send_proactive_reply()
```

`threshold` 默认为 `0.5`。`BoolResult` 包含 `value`、`probability`、`model` 和 `latency_ms`。

## 兼容接口

自定义服务商需要接受 `POST` 请求，并通过 Bearer Token 鉴权。请求体包含 `model`、`state` 和 `questions`：

```json
{
  "model": "jev-latest",
  "state": {},
  "questions": {
    "answer": {
      "type": "choice",
      "instructions": "选择最合适的动作",
      "criteria": {
        "o1": "直接回复",
        "o2": "保持沉默"
      }
    }
  }
}
```

单选应答需包含 `answers.answer.choice`、`answers.answer.confidence` 与 `answers.answer.probabilities`；是非应答使用 `answers.answer.noul` 返回 0 到 1 的概率。响应顶层还需包含 `model`。

## 常见问题

| 现象 | 处理方式 |
| --- | --- |
| 提示 `HTTP 401` 或 `HTTP 403` | 检查 API Key 是否与当前服务商匹配 |
| 提示 `HTTP 404` | 检查 `base_url` 是否指向完整的 System One 路径 |
| 提示 API Key 未配置 | 在插件配置中填写 `api_key` 并重载插件 |
| 统计页面没有数据 | 先执行一次判断；统计数据不会跨重载保留 |

## 数据与隐私

- API Key 由 AstrBot 插件配置保存，仅用于向所选判断服务发起请求。
- 判断请求直接发送到配置的服务端点，不经过本插件的其他中转服务。
- 统计数据仅保存在进程内存中，不写入数据库或日志文件。

## 许可

本项目使用 [AGPL-3.0-or-later](LICENSE)。
