"""基金数据中心(原型②；FR-01~05 / DC-002)。全类型检索/分类树/发现/档案/净值。"""

import streamlit as st

st.title("🗂️ 基金数据中心")
st.caption("搜索 + 分类树 + 发现 · 档案分组 + 字段解释 · 净值复权/下载/盘中估算 · 跳穿透")

with st.container(border=True):
    st.warning("🏗️ 建设中 · 关联 FR-01~05 / DC-002")
    st.caption("P1-02a/b 检索与档案接口 + P1-13a/b/c 页面待实现。")

st.text_input("搜索基金代码/名称", placeholder="如 000001 / 华夏成长")
