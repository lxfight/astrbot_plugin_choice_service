# astrbot_plugin_choice_service

[![CI](https://github.com/lxfight/astrbot_plugin_choice_service/actions/workflows/ci.yml/badge.svg)](https://github.com/lxfight/astrbot_plugin_choice_service/actions/workflows/ci.yml)

[GitHub 仓库](https://github.com/lxfight/astrbot_plugin_choice_service)

通用选择判断插件。它使用 **System One 兼容协议**，不绑定 TypeSafe 或 Jev：可以接入 TypeSafe、OpenRouter、Vercel AI Gateway，也可以填写任意兼容该请求/响应格式的端点。

适用于主动回复、意图分类、是否打断、回复前复核、动作选择等简单判断。

## 功能

- 任意单选：传入问题、选项与上下文，返回选项、概率、置信度和完整分布。
- 是非判断：返回 0～1 概率，阈值由调用方决定。
- 多服务商：内置 TypeSafe、OpenRouter、Vercel AI Gateway 预设，支持自定义端点。
- 跨插件调用：其他 AstrBot 插件直接取得服务实例。
- 实时统计：WebUI 页面展示调用量、成功率、延迟、选项分布和最近判断。
- 四语支持：简体中文、English、日本語、Русский。

## 安装与配置

将插件目录放到 `AstrBot/data/plugins/astrbot_plugin_choice_service`，在 WebUI 重载插件后填写配置。

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `provider` | `typesafe` | `typesafe`、`openrouter`、`vercel` 或 `custom` |
| `api_key` | 空 | 与当前服务商匹配的密钥 |
| `base_url` | 空 | 留空使用预设；自定义时必须填写完整 System One 地址 |
| `model` | 空 | 留空使用预设；自定义时必须填写 |
| `language` | `auto` | `auto` 跟随 AstrBot，或指定 `zh-CN`、`en-US`、`ja-JP`、`ru-RU` |
| `timeout_sec` | `10` | 单次请求超时 |

内置预设：

| 服务商 | 接口 | 模型 |
| --- | --- | --- |
| TypeSafe | `https://api.typesafe.ai/v1/systemone` | `jev-latest` |
| OpenRouter | `https://openrouter.ai/api/v1/systemone` | `jev-latest` |
| Vercel AI Gateway | `https://ai-gateway.vercel.sh/typesafe/v1/systemone` | `typesafe-ai/jev` |
| 自定义 | 由 `base_url` 指定 | 由 `model` 指定 |

自定义地址必须包含完整的 System One 路径，例如 `https://api.typesafe.ai/v1/systemone`；只填写 `/v1` 会返回 404。

自定义端点只需兼容以下约定：请求包含 `model`、`state`、`questions`，Choice 应答包含 `choice`、`confidence`、`probabilities`，Noul 应答包含 `noul`。

## 跨插件调用

```python
meta = self.context.get_registered_star("astrbot_plugin_choice_service")
service = meta.star_cls.service if meta and meta.star_cls else None
```

### 任意单选

```python
result = await service.choose(
    "机器人下一步应该做什么？",
    {
        "reply": "直接回复当前消息",
        "wait": "保持沉默，等待更多消息",
        "react": "只做表情回应",
    },
    state={"messages": recent_messages, "bot_name": "小助手"},
)

match result.choice:
    case "reply":
        ...
    case "wait":
        ...
    case "react":
        ...
```

`result` 包含 `choice`、`probability`、`confidence`、`probabilities`、`model`、`latency_ms`。

选项也可以直接使用字符串列表：

```python
result = await service.choose(
    "这段文本是什么语气？",
    ["友好", "中性", "敌意"],
    state=text,
)
```

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

## 统计页面

在插件详情页打开“统计”视图，可查看：

- 调用次数、成功率、平均延迟、单选/是非调用数。
- 各选项被选中的次数分布。
- 当前服务商、模型、接口、超时与密钥状态。
- 最近 30 次判断的耗时、概率和结果。

统计只保存在内存中，插件重载后清零。页面提供刷新与重置按钮。

## 测试命令

```text
/choose 周末适合出门吗？ :: 适合 | 不适合
```

## 开发

```bash
pytest -q
ruff check .
ruff format --check .
```

## 许可

AGPL-3.0-or-later，见 [LICENSE](LICENSE)。
