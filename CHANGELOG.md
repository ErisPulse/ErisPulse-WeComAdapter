# 更新日志

所有版本更新遵循 [语义化版本控制](https://semver.org/lang/zh-CN/) 规范。

---

## [0.1.0] - 2026/10/19

- 新仓库初始发布，版本号从 0.1.0 重新起步
- `Raw_ob12` 支持合并转发 node 段纯文本降级（每条「昵称: 正文」原文输出，内容不丢失）

## [4.1.0] - 2026/07/08

### 修复

- 修复 `WeComAccountConfig` 未声明 `bot_id` 字段导致启动报错的问题
  - 移除 `_load_accounts` 中 `instance.bot_id = instance.corpid` 的写入（bot 标识始终使用 `account.corpid`）

### 变更

- 配置字段 metadata 迁移至新格式：`webui` 键更名 `ui`
