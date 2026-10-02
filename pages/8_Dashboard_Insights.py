"""Dashboard → คีย์เวิร์ด แบรนด์ ช่องทาง: what customers talk about."""

import pandas as pd
import streamlit as st

st.set_page_config(page_title="SmartVoice — คีย์เวิร์ด แบรนด์ ช่องทาง", layout="wide")

from smartvoice.auth import PAGE_INSIGHTS
from smartvoice.dashboard_common import (
    SCALE_NAVY,
    SCALE_STEEL,
    SCALE_TEAL,
    count_list_field,
    hbar,
    inject_dashboard_css,
    load_filtered_calls,
)
from smartvoice.ui_helpers import init_page

init_page(PAGE_INSIGHTS)
inject_dashboard_css()

st.title("Dashboard — คีย์เวิร์ด แบรนด์ ช่องทาง")
st.caption("คำที่ลูกค้าพูดถึงบ่อย แบรนด์ที่ถูกเอ่ยถึง และช่องทางที่ลูกค้าซื้อ/ติดต่อ — นับจากผลวิเคราะห์ของแต่ละสาย")

df, _ = load_filtered_calls()
done_calls = df.to_dict("records")

_HOVER_TIMES = "พบ: %{x} ครั้ง"

kw_col, brand_col = st.columns(2)

with kw_col:
    st.subheader("หัวข้อปัญหา (Issue Keywords)")
    kw_counts = count_list_field(done_calls, "keywords")
    if kw_counts:
        kw_df = pd.DataFrame(kw_counts, columns=["Keyword", "Count"])
        st.plotly_chart(
            hbar(kw_df, "Keyword", SCALE_NAVY, hover_unit=_HOVER_TIMES, xaxis_title="จำนวนครั้ง",
                 height=max(260, 60 + 34 * len(kw_df))),
            width="stretch",
        )
    else:
        st.caption("ยังไม่มีข้อมูล keyword")

with brand_col:
    st.subheader("Brand Mentions")
    brand_counts = count_list_field(done_calls, "brand_mentions")
    if brand_counts:
        brand_df = pd.DataFrame(brand_counts, columns=["Brand", "Count"])
        st.plotly_chart(
            hbar(brand_df, "Brand", SCALE_TEAL, hover_unit=_HOVER_TIMES, xaxis_title="จำนวนครั้ง",
                 height=max(260, 60 + 34 * len(brand_df))),
            width="stretch",
        )
    else:
        st.caption("ยังไม่มีข้อมูล brand mentions")

st.divider()

st.subheader("Platform / Channel Mentions")
plat_counts = count_list_field(done_calls, "platform_mentions")
if plat_counts:
    plat_df = pd.DataFrame(plat_counts, columns=["Platform", "Count"])
    st.plotly_chart(
        hbar(plat_df, "Platform", SCALE_STEEL, hover_unit=_HOVER_TIMES, xaxis_title="จำนวนครั้ง",
             height=max(220, 60 + 38 * len(plat_df))),
        width="stretch",
    )
else:
    st.caption("ยังไม่มีข้อมูล platform mentions — re-process ไฟล์เสียงเพื่อดูผล")
