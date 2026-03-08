# 风险管理模块

这个目录用于承载交易系统中的风险管理能力。

第一阶段只关注两类基础能力：

- 持仓风险监控
- 交易限制计算

当前不在这个目录内处理以下能力：

- 通用规则引擎
- 复杂行为风控
- 多层事件流转
- 自动化强制平仓

建议后续优先新增：

- `rule_templates.py`：风险规则模板
- `rule_engine.py`：最小规则执行器
- `position_risk.py`：持仓风险监控
- `trade_limits.py`：交易限制计算

当前已经落地：

- `config.py`
- `rule_templates.py`
- `rule_engine.py`
- `position_risk.py`
- `trade_limits.py`

当前默认参数集中在 `config.py`：

- 单笔风险默认按账户总资产的 `1%`
- 单标的仓位占比默认上限 `20%`
- 默认下单数量步长 `1`
