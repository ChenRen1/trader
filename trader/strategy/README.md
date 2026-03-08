# Strategy 模块规范

## 目录约定
- `core/`: 策略抽象与注册器（统一接口，策略发现）。
- `strategies/`: 策略引擎实现（如 `dividend.py`）。
- `services/`: 与策略相关的数据服务与业务服务（股票池、股息率、标记同步）。
- `backtest/`: 回测逻辑。
- `reports/`: 报告产物（运行时输出）。

## 开发流程（新增策略）
1. 在 `strategies/` 新建策略引擎，至少实现 `strategy_key` 和 `generate_signals()`。
2. 在 `strategies/__init__.py` 注册到 `core.registry`。
3. 在 `services/` 补齐该策略所需数据准备逻辑（如指标计算、数据清洗）。
4. 在 `management/commands/` 增加运行命令（同步、回填、报告）。
5. 在 `tests/` 增加最小可运行测试（信号正确性 + 数据链路）。

## 高股息策略现状
- 策略键：`dividend_yield`
- 信号口径：`最近完整年报分红 / 当前价`
- 依赖字段：
  - `Instrument.is_high_dividend`
  - `InstrumentPrice.annual_cash_dividend_per_10`
  - `InstrumentPrice.annual_dividend_per_share`
  - `InstrumentPrice.annual_dividend_yield_pct`
  - `InstrumentPrice.annual_dividend_report`

## 常用命令
- 同步高股息标的：`python manage.py sync_high_dividend_instruments`
- 回填价格股息字段：`python manage.py backfill_price_dividend_fields --all-cn`
- 生成买入候选报告：`python manage.py generate_dividend_buy_report`
- 计算单标的年报股息率：`python manage.py calc_high_dividend_yields --symbol 600036`
