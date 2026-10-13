# 架构

CLI → API 请求校验与版本绑定 → 完整前缀 beam search/启发式评分 → worker JSONL v2 → ocgcore FFI → 消息、提示、状态 → 报告与独立重放。

Rust domain 负责卡片与牌组规则；storage 只读 CDB 并建立不可变 JSON 快照；engine-adapter 隔离真实核心、回调、超时和协议；search 只使用 worker 提示枚举响应；api 组织分析／重放合同；cli 暴露本机命令。Python 提供规范化 JSON 合同校验和离线评估入口。

核心执行权威是固定 ocgcore。没有自主编写完整卡效模拟器。评分不影响动作合法性，启发式强度与引擎验证分开标注。缓存完整决策前缀，不因可见状态相等而合并。错误包含阶段、版本及证据。
