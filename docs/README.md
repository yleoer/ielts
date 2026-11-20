# 文档索引

仓库以桌面端“词间”为主体，同步服务和 Anki 牌组为其提供数据。目录说明见 [仓库 README](../README.zh-CN.md)。

## 桌面端（desktop/）

- [桌面端说明（安装、使用与开发）](../desktop/README.md)
- [Tauri 2 桌面端设计](desktop/DESIGN.md)
- [前端说明](desktop/FRONTEND.md)
- [选词策略](desktop/WORD-SELECTION.md)
- [FSRS 单词记忆与参数优化](desktop/SRS-PLAN.md)
- [独立媒体资源包](desktop/MEDIA.md)
- [测试与真实窗口检查](desktop/TESTING.md)
- [发布](desktop/RELEASING.md)

### 学习统计

- [统计功能总结](desktop/statistics/SUMMARY.md)
- [统计模型和接口说明](desktop/statistics/SPEC.md)
- [统计页面说明](desktop/statistics/FRONTEND.md)

## 同步服务（server/）

- [服务说明](../server/README.md)
- [服务概览](server/SPEC.md)
- [Docker 部署](server/DOCKER-DEPLOY.md)
- [自动部署](server/AUTO-DEPLOY.md)
- [本地构建说明](server/LOCAL-BUILD.md)
- [测试范围](server/TESTING.md)
- [镜像验证](server/IMAGE-CHECK.md)

## Anki 牌组（deck/）

- [Word Atlas 牌组](deck/word-atlas.md)
- [Word Atlas 卡片设计约定](deck/word-atlas-surface.md)
- [Word Atlas 英美与拼写变体核对清单](deck/word-atlas-variant-audit.md)
- [本地修订表](../deck/data/word-atlas-revisions/README.md)

## 工程约定

- [防御性代码审计](DEFENSIVE-PROGRAMMING.md)

## 文档原则

- 只保留项目决策、边界、接口和排障信息。
- 代码示例只保留必要部分。
- 具体实现以源码和测试为准。
