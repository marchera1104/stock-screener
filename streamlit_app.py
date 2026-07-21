"""
=====================================================================
A股选股筛选 —— 网页版（Streamlit）
=====================================================================
这是脚本的"网页界面版"，部署到云端后，可以用手机浏览器打开操作，
在页面上直接调整筛选条件、点击按钮查看结果，无需再用终端敲命令。

本地测试运行方法：
    pip3 install streamlit akshare pandas --upgrade
    streamlit run streamlit_app.py

部署到手机可用的公网地址：见文末部署说明。
=====================================================================
"""

import time
import akshare as ak
import pandas as pd
import streamlit as st

st.set_page_config(page_title="A股选股筛选", layout="wide")


# =====================================================================
# 数据获取（带自动重试 + 备用数据源，和终端版逻辑一致）
# =====================================================================

@st.cache_data(ttl=300, show_spinner=False)  # 缓存5分钟，避免频繁重复请求
def fetch_market_snapshot(max_retries: int = 3) -> pd.DataFrame:
    for attempt in range(1, max_retries + 1):
        try:
            df = ak.stock_zh_a_spot_em()
            return df
        except Exception:
            if attempt < max_retries:
                time.sleep(2)

    # 备用：新浪财经接口
    try:
        df = ak.stock_zh_a_spot()
        rename_map = {
            "trade": "最新价", "changepercent": "涨跌幅", "turnoverratio": "换手率",
            "per": "市盈率-动态", "pb": "市净率", "mktcap": "总市值",
            "code": "代码", "name": "名称",
        }
        df = df.rename(columns=rename_map)
        if "总市值" in df.columns:
            df["总市值"] = df["总市值"].astype(float) * 1e4
        if "量比" not in df.columns:
            df["量比"] = None
        return df
    except Exception as e:
        st.error(f"数据获取失败，两个数据源都无法连接：{e}")
        return pd.DataFrame()


def apply_filters(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    result = df.copy()

    def has_col(col_name):
        return col_name in result.columns

    if cfg.get("exclude_st") and has_col("名称"):
        result = result[~result["名称"].str.contains("ST", na=False)]
    if cfg.get("exclude_new") and has_col("名称"):
        result = result[~result["名称"].str.startswith("N", na=False)]
    if cfg.get("exclude_bj") and has_col("代码"):
        result = result[~result["代码"].astype(str).str.startswith(("8", "4"))]

    if has_col("市盈率-动态"):
        result = result[result["市盈率-动态"] >= cfg["pe_min"]]
        result = result[result["市盈率-动态"] <= cfg["pe_max"]]

    if has_col("市净率"):
        result = result[result["市净率"] >= cfg["pb_min"]]
        result = result[result["市净率"] <= cfg["pb_max"]]

    if has_col("总市值"):
        result = result[result["总市值"].astype(float) / 1e8 >= cfg["market_cap_min"]]
        if cfg.get("market_cap_max"):
            result = result[result["总市值"].astype(float) / 1e8 <= cfg["market_cap_max"]]

    if has_col("涨跌幅"):
        result = result[result["涨跌幅"] >= cfg["change_pct_min"]]
        result = result[result["涨跌幅"] <= cfg["change_pct_max"]]

    if has_col("换手率"):
        result = result[result["换手率"] >= cfg["turnover_min"]]
        result = result[result["换手率"] <= cfg["turnover_max"]]

    return result


# =====================================================================
# 页面界面
# =====================================================================

st.title("📈 A股选股筛选工具")
st.caption("在下方调整筛选条件，点击「开始筛选」查看结果")

with st.sidebar:
    st.header("筛选条件")

    st.subheader("基本面")
    pe_min, pe_max = st.slider("市盈率(动态)范围", 0, 200, (0, 30))
    pb_min, pb_max = st.slider("市净率范围", 0.0, 20.0, (0.0, 5.0))
    market_cap_min = st.number_input("总市值下限（亿元）", value=50, step=10)
    market_cap_max = st.number_input("总市值上限（亿元，0表示不限）", value=0, step=10)

    st.subheader("交易情况")
    change_min, change_max = st.slider("当日涨跌幅范围（%）", -20, 20, (-3, 9))
    turnover_min, turnover_max = st.slider("换手率范围（%）", 0.0, 50.0, (1.0, 20.0))

    st.subheader("通用过滤")
    exclude_st = st.checkbox("排除 ST 股票", value=True)
    exclude_new = st.checkbox("排除次新股", value=True)
    exclude_bj = st.checkbox("排除北交所", value=True)

    run_button = st.button("🔍 开始筛选", type="primary", use_container_width=True)

if run_button:
    cfg = {
        "pe_min": pe_min, "pe_max": pe_max,
        "pb_min": pb_min, "pb_max": pb_max,
        "market_cap_min": market_cap_min,
        "market_cap_max": market_cap_max if market_cap_max > 0 else None,
        "change_pct_min": change_min, "change_pct_max": change_max,
        "turnover_min": turnover_min, "turnover_max": turnover_max,
        "exclude_st": exclude_st, "exclude_new": exclude_new, "exclude_bj": exclude_bj,
    }

    with st.spinner("正在获取全市场行情快照..."):
        df = fetch_market_snapshot()

    if df.empty:
        st.warning("没有获取到数据，请稍后重试。")
    else:
        filtered = apply_filters(df, cfg)
        show_cols = [c for c in ["代码", "名称", "最新价", "涨跌幅", "换手率",
                                   "市盈率-动态", "市净率", "总市值"] if c in filtered.columns]

        st.success(f"筛选完成，共找到 {len(filtered)} 只股票")
        st.dataframe(
            filtered[show_cols].sort_values("涨跌幅", ascending=False) if "涨跌幅" in filtered.columns else filtered[show_cols],
            use_container_width=True, height=500,
        )

        csv = filtered[show_cols].to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ 下载结果CSV", csv, "result.csv", "text/csv")
else:
    st.info("👈 在左侧设置好条件后，点击「开始筛选」")


# =====================================================================
# 部署说明（让手机能打开这个页面）
# =====================================================================
"""
本地在Mac上跑起来只有你自己电脑能打开，手机要访问，需要把它部署到云端，
免费且对新手最友好的方式是 Streamlit Community Cloud：

第一步：注册 GitHub 账号（如果还没有）
    访问 https://github.com 免费注册

第二步：把代码传到 GitHub
    1. 新建一个仓库（Repository），比如叫 stock-screener
    2. 把这个 streamlit_app.py 文件上传进去（GitHub网页里就有"上传文件"按钮，
       不需要用命令行）
    3. 再新建一个文件叫 requirements.txt，内容写：
           streamlit
           akshare
           pandas

第三步：部署到 Streamlit Cloud
    1. 访问 https://share.streamlit.io，用 GitHub 账号登录
    2. 点 "New app"，选择刚才建的仓库和 streamlit_app.py 文件
    3. 点 Deploy，等1-2分钟部署完成
    4. 会生成一个网址，形如 https://你的项目名.streamlit.app

第四步：手机上访问
    1. iPhone上用Safari打开那个网址
    2. 点击分享按钮 → "添加到主屏幕"，就能像App一样从主屏幕图标打开了

⚠️ 注意：云端服务器在国外，访问东财/新浪接口可能会遇到和你之前一样的
网络不稳定问题，脚本里已经内置了重试和备用数据源逻辑，多数情况能自动处理。
"""
