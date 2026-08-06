你现在是 FundLens 项目的阶段评审官。请基于仓库实际状态产出一份《阶段评审报告》。

输入（请自行读取/运行）：
- 任务真相源：docs/基金评估系统_交付文档/09_开发计划/基金评估系统_开发任务分解.md
- 变更台账：CHANGELOG.md + docs/基金评估系统_交付文档/13_需求变更管理规范/cr/
- 已知问题：docs/DEFERRED.md
- 客观指标：运行 pytest --cov=domain --cov-report=term-missing、ruff check .、mypy .、git log --since="<上次于审日>"

请执行：
1. 进度：按 Phase 与 P0/P1/P2 统计任务完成率（已合并/已关闭 vs 计划），列偏差。
2. 质量：汇总覆盖率、lint/type 问题数，对照 DoD（覆盖率≥80%、接口100%命中§2.21）。
3. 问题：汇总 DEFERRED 未闭环项、未关闭 CR、技术债。
4. 风险：评估 E1-E14 回退（跑对应 TP test oracle）、范围蔓延、文档脱节(R7)、外部依赖、密钥安全。
5. 目标与计划：给本 Phase Go/No-Go，提未来计划调整建议。

输出：Markdown 评审报告，含 进度/质量/风险 各 0-5 评分 + 结论 + 行动项(负责人/期限)，
写入 docs/基金评估系统_交付文档/14_阶段评审/REVIEW_<YYYYMMDD>.md，并登记 CHANGELOG。
