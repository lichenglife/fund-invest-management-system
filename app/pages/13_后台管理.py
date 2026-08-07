"""后台管理(详设§2.16 系统监控 / §3.14 任务调度与监控 / §2.19.6 管理端点鉴权；P1-10b)。

三 Tab：
1. 定时任务执行状态 - scheduler_jobs 执行历史(§3.14.3) + 手动触发(§3.14.4)
2. 监控数据 - §2.16 五维监控(采集/质量/API/定时任务/资源) + 数据质量看板(P2-03c)
3. 变更评审评估 - §9.3 OQ 机制 + §2.16 阈值触发，评估是否发起变更评审(ADR/CR/发布DoD)

> 用户直接授权模块；对齐开发任务分解 P1-10b(admin trigger-job)、P2-03c(quality 接口)、
> P1-23/P2-09 上线监控生效。原型无此页(12 页之外第 13 页)，设计依据详设§2.16+§3.14+§2.19.6。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import api_client, utils  # noqa: E402
from app.components import ui  # noqa: E402
from app.components.kpi_card import kpi_card  # noqa: E402
from app.components.ranking_table import ranking_table  # noqa: E402

ui.inject_global_style()
ui.page_header("🛠️ 后台管理", "定时任务执行状态 · 监控数据(§2.16) · 变更评审评估(§9.3 OQ)")

if api_client.is_mock():
    ui.mock_hint()
else:
    # 真实模式需管理员登录(§2.19.6)；令牌存 session_state
    if not st.session_state.get("admin_token"):
        with st.container(border=True):
            st.markdown("**管理员登录**（§2.19.6 单用户 MVP）")
            cols = st.columns([2, 2, 1])
            user = cols[0].text_input("账户", value="admin", key="admin_user")
            pwd = cols[1].text_input("密码", type="password", key="admin_pwd")
            if cols[2].button("登录", use_container_width=True):
                try:
                    data = api_client.admin_login(user, pwd)
                    st.session_state["admin_token"] = data.get("access_token")
                    api_client.set_admin_token(st.session_state["admin_token"])
                    if data.get("must_change_password"):
                        st.warning("首次登录请修改密码(§2.19.6)")
                    st.rerun()
                except Exception:  # noqa: BLE001
                    st.error("登录失败(40101 用户名或密码错误)")
            st.caption("未登录访问 /api/admin/* 返回 40101；非管理员 40103(§3.14.5)")
        st.stop()
    api_client.set_admin_token(st.session_state["admin_token"])

# --- 数据加载 ---
jobs = api_client.get_admin_jobs()
monitor = api_client.get_admin_monitor()
quality = api_client.get_admin_quality()
assessment = api_client.get_admin_change_assessment()

tab_jobs, tab_monitor, tab_change = st.tabs(["⏰ 定时任务执行状态", "📊 监控数据", "🔄 变更评审评估"])

# =====================================================================
# Tab 1: 定时任务执行状态(§3.14.3 scheduler_jobs 历史)
# =====================================================================
with tab_jobs:
    kpi = monitor.get("kpi", {})
    success_rate = kpi.get("success_rate", 0)
    avg_ms = kpi.get("avg_duration_ms", 0)
    with ui.panel("今日执行概览", tag="§3.14.3 / §2.16 定时任务"):
        ui.kpi_grid(
            [
                {"label": "今日执行", "value": str(kpi.get("today_runs", 0)), "period": "近 24h"},
                {
                    "label": "成功率",
                    "value": f"{success_rate * 100:.1f}%",
                    "period": "近 24h",
                    "is_positive": success_rate >= 0.95,
                },
                {"label": "平均耗时", "value": f"{avg_ms / 1000:.1f}s", "period": "近 24h"},
                {
                    "label": "失败数",
                    "value": str(kpi.get("failed", 0)),
                    "period": "近 24h",
                    "is_positive": kpi.get("failed", 0) == 0,
                },
            ]
        )

    with ui.panel("任务执行历史", tag="§3.14.3 scheduler_jobs · 每行=一次执行"):
        if jobs:
            df = pd.DataFrame(jobs)
            # 状态加 emoji 着色(canvas 单元格不支持 HTML，用 emoji 前缀)
            status_map = {"success": "✅ success", "failed": "❌ failed", "running": "🟡 running"}
            df["status"] = df["status"].map(lambda x: status_map.get(x, x))
            df["duration_s"] = df["duration_ms"].map(lambda x: f"{x / 1000:.1f}s" if pd.notna(x) else "-")
            df["error"] = df["error"].fillna("-")
            show = df[
                ["job_id", "job_name", "trigger", "status", "started_at", "duration_s", "error"]
            ].rename(
                columns={
                    "job_id": "作业ID",
                    "job_name": "作业名",
                    "trigger": "触发",
                    "status": "状态",
                    "started_at": "开始时间",
                    "duration_s": "耗时",
                    "error": "错误摘要",
                }
            )
            ranking_table(
                show,
                columns_config={
                    "作业ID": st.column_config.TextColumn(width="small"),
                    "作业名": st.column_config.TextColumn(width="large"),
                    "触发": st.column_config.TextColumn(width="small"),
                    "状态": st.column_config.TextColumn(width="small"),
                    "开始时间": st.column_config.TextColumn(width="medium"),
                    "耗时": st.column_config.TextColumn(width="small"),
                    "错误摘要": st.column_config.TextColumn(width="large"),
                },
                height=360,
                as_of=monitor.get("as_of"),
                mock=api_client.is_mock(),
                caption="§3.14.5：所有定时任务写入日志，失败告警；任务幂等(§3.14.6 锁防重)。",
            )
        else:
            st.info("暂无执行历史")

    with ui.panel("手动触发作业", tag="§3.14.4 /admin/trigger-job · 须管理员(§2.19.6)"):
        cols = st.columns([2, 2, 1])
        job = cols[0].selectbox("作业", ["fund_list", "nav", "holdings"], key="trig_job")
        code = cols[1].text_input("基金代码(nav/holdings 必填)", value="005827", key="trig_code")
        if cols[2].button("触发", use_container_width=True, type="primary"):
            kwargs = {}
            if job in ("nav", "holdings"):
                kwargs["code"] = code
            with st.spinner("执行中…"):
                result = api_client.trigger_admin_job(job, **kwargs)
            if result.get("status") == "success":
                st.success(f"触发成功：{result.get('job')} upserted={result.get('upserted')}")
            else:
                st.error(f"触发失败：{result.get('job')}")
        st.caption("手动触发记录 trigger=manual 历史行；未登录 40101、非管理员 40103(§3.14.5)")

# =====================================================================
# Tab 2: 监控数据(§2.16 五维监控 + 数据质量看板 P2-03c)
# =====================================================================
with tab_monitor:
    with ui.panel("§2.16 五维监控", tag="告警阈值见详设§2.16"):
        items = monitor.get("items", [])
        for i in range(0, len(items), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                if i + j < len(items):
                    it = items[i + j]
                    with col:
                        level = it.get("level", "good")
                        is_pos = level == "good"
                        # bad/warn 用红/黄语义；good 用绿
                        kpi_card(
                            it.get("name", ""),
                            it.get("value", "-"),
                            period=f"阈值 {it.get('threshold', '')}",
                            delta=it.get("detail"),
                            is_positive=is_pos,
                        )
                        st.markdown(
                            f"<div style='margin-top:-6px;margin-bottom:8px'>{ui.status_pill(level)}</div>",
                            unsafe_allow_html=True,
                        )

    with ui.panel("数据质量看板", tag="P2-03c /quality/dashboard · §2.16 数据质量"):
        # 摘要
        for q in quality.get("summary", []):
            lv = q.get("level", "good")
            st.markdown(
                f"{utils.level_emoji(lv)} **{q.get('k')}**：{q.get('v')} "
                f"<small style='color:var(--text-muted)'>· {q.get('d', '')}</small>",
                unsafe_allow_html=True,
            )
        st.divider()
        logs = quality.get("logs", [])
        if logs:
            df = pd.DataFrame(logs)
            df["anomaly"] = df["anomaly_flag"].map(lambda x: "🔴 异常" if x else "🟢 正常")
            df["cv_error"] = df["cv_error"].map(lambda x: f"{x * 100:.4f}%" if pd.notna(x) else "-")
            df["note"] = df["note"].fillna("-")
            show = df[
                ["entity", "check_date", "missing_count", "anomaly", "cv_error", "source", "note"]
            ].rename(
                columns={
                    "entity": "实体",
                    "check_date": "检查日期",
                    "missing_count": "缺失数",
                    "anomaly": "异常标记",
                    "cv_error": "对账误差",
                    "source": "来源",
                    "note": "备注",
                }
            )
            ranking_table(
                show,
                columns_config={
                    "实体": st.column_config.TextColumn(width="small"),
                    "检查日期": st.column_config.TextColumn(width="small"),
                    "缺失数": st.column_config.NumberColumn(width="small"),
                    "异常标记": st.column_config.TextColumn(width="small"),
                    "对账误差": st.column_config.TextColumn(width="small"),
                    "来源": st.column_config.TextColumn(width="small"),
                    "备注": st.column_config.TextColumn(width="large"),
                },
                height=280,
                as_of=quality.get("as_of"),
                mock=api_client.is_mock(),
                caption="§2.16：对账误差>0.5% 或异常标记即标红告警。",
            )

# =====================================================================
# Tab 3: 变更评审评估(开发规范§9.3 OQ + §2.16 阈值触发)
# =====================================================================
with tab_change:
    need = assessment.get("need_review", False)
    sev = assessment.get("severity", "green")
    rtype = assessment.get("review_type", "none")
    type_label = {"ADR": "ADR 技术选型", "CR": "CR 需求变更", "release_dod": "发布 DoD", "none": "无需"}

    with ui.panel("变更评审评估结论", tag="开发规范§9.3 变更评审 OQ 机制"):
        sev_emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(sev, "⚪")
        st.markdown(
            f"### {sev_emoji} {'需要' if need else '暂不需要'}发起变更评审",
            unsafe_allow_html=True,
        )
        if need:
            st.markdown(
                f"**建议发起类型**：{type_label.get(rtype, rtype)}"
                f"<small style='color:var(--text-muted)'>（严重度 {sev}）</small>",
                unsafe_allow_html=True,
            )
        else:
            st.info("当前监控指标均在阈值内，暂无需发起变更评审(§2.16 全绿)。")

    col_l, col_r = st.columns(2)
    with col_l:
        with ui.panel("触发理由", tag="§2.16 阈值 breached"):
            for r in assessment.get("reasons", []):
                st.markdown(f"- {r}")
    with col_r:
        with ui.panel("建议动作", tag="§9.3 OQ + §11 ADR"):
            for a in assessment.get("actions", []):
                st.markdown(f"- {a}")

    with ui.panel("变更评审流程依据", tag="CLAUDE.md §11 / 开发规范 §9.3/§9.5"):
        for ref in assessment.get("process_refs", []):
            st.markdown(f"- {ref}")
        st.divider()
        st.caption(
            "流程：监控告警(§2.16) → 评估变更类型(ADR/CR/发布DoD) → 走对应评审 → "
            "ADR 写 docs/adr/；CR 走 13_需求变更管理规范/cr/；发布走 §9.5 DoD 清单。"
        )
