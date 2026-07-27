"""UST-branded Streamlit theme and layout helpers.

Brand colors (UST Global / UST):
  - Dark Teal:  #006E74
  - Light Teal: #0097AC
  - Soft Black: #231F20
  - White:      #FFFFFF
"""

from __future__ import annotations

import html
import textwrap

import streamlit as st

# UST primary palette — https://www.ust.com/brand/color
UST_DARK_TEAL = "#006E74"
UST_LIGHT_TEAL = "#0097AC"
UST_SOFT_BLACK = "#231F20"
UST_WHITE = "#FFFFFF"
UST_TEAL_50 = "#E6F4F6"
UST_TEAL_100 = "#CCE9EC"
UST_GRAY_100 = "#F5F5F5"
UST_GRAY_200 = "#E8E8E8"
UST_GRAY_500 = "#6B7280"
UST_SUCCESS = "#0D7C66"
UST_WARNING = "#B45309"
UST_ERROR = "#B42318"


def _css() -> str:
    return f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

      html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        color: {UST_SOFT_BLACK};
      }}

      /* Main container */
      .block-container {{
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
        max-width: 1200px;
      }}

      /* Sidebar */
      section[data-testid="stSidebar"] {{
        background: linear-gradient(175deg, {UST_DARK_TEAL} 0%, #004B50 55%, {UST_SOFT_BLACK} 100%);
        border-right: none;
      }}
      section[data-testid="stSidebar"] * {{
        color: {UST_WHITE} !important;
      }}
      section[data-testid="stSidebar"] .stRadio label,
      section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{
        color: rgba(255,255,255,0.92) !important;
      }}
      section[data-testid="stSidebar"] hr {{
        border-color: rgba(255,255,255,0.15);
      }}

      /* Page hero */
      .ust-hero {{
        background: linear-gradient(135deg, {UST_DARK_TEAL} 0%, {UST_LIGHT_TEAL} 100%);
        border-radius: 12px;
        padding: 1.75rem 2rem;
        margin-bottom: 1.5rem;
        color: {UST_WHITE};
        box-shadow: 0 4px 24px rgba(0, 110, 116, 0.18);
      }}
      .ust-hero h1 {{
        color: {UST_WHITE} !important;
        font-size: 1.85rem !important;
        font-weight: 700 !important;
        margin: 0 0 0.35rem 0 !important;
        letter-spacing: -0.02em;
      }}
      .ust-hero p {{
        color: rgba(255,255,255,0.9) !important;
        font-size: 1rem;
        margin: 0;
        line-height: 1.5;
      }}
      .ust-hero .ust-badge {{
        display: inline-block;
        background: rgba(255,255,255,0.18);
        border: 1px solid rgba(255,255,255,0.25);
        border-radius: 999px;
        padding: 0.2rem 0.75rem;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.75rem;
      }}

      /* Sidebar brand block */
      .ust-sidebar-brand {{
        padding: 0.5rem 0 1.25rem 0;
        margin-bottom: 0.5rem;
        border-bottom: 1px solid rgba(255,255,255,0.15);
      }}
      .ust-sidebar-brand .ust-logo {{
        font-size: 1.75rem;
        font-weight: 800;
        letter-spacing: 0.12em;
        line-height: 1.1;
      }}
      .ust-sidebar-brand .ust-product {{
        font-size: 0.95rem;
        font-weight: 600;
        opacity: 0.95;
        margin-top: 0.15rem;
      }}
      .ust-sidebar-brand .ust-tagline {{
        font-size: 0.78rem;
        opacity: 0.75;
        margin-top: 0.35rem;
      }}

      /* Cards */
      .ust-card {{
        background: {UST_WHITE};
        border: 1px solid {UST_GRAY_200};
        border-left: 4px solid {UST_LIGHT_TEAL};
        border-radius: 10px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(35, 31, 32, 0.06);
      }}
      .ust-card h3 {{
        color: {UST_DARK_TEAL};
        font-size: 1rem;
        font-weight: 600;
        margin: 0 0 0.5rem 0;
      }}

      /* Section title */
      .ust-section-title {{
        color: {UST_DARK_TEAL};
        font-size: 1.1rem;
        font-weight: 600;
        margin: 1.5rem 0 0.75rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid {UST_TEAL_100};
      }}

      /* Metrics */
      div[data-testid="stMetric"] {{
        background: {UST_TEAL_50};
        border: 1px solid {UST_TEAL_100};
        border-radius: 10px;
        padding: 0.75rem 1rem;
      }}
      div[data-testid="stMetric"] label {{
        color: {UST_GRAY_500} !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        letter-spacing: 0.03em;
      }}
      div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
        color: {UST_DARK_TEAL} !important;
        font-weight: 700 !important;
      }}

      /* Primary button */
      .stButton > button[kind="primary"] {{
        background: {UST_DARK_TEAL} !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.25rem !important;
        transition: background 0.2s ease;
      }}
      .stButton > button[kind="primary"]:hover {{
        background: {UST_LIGHT_TEAL} !important;
      }}

      /* Secondary buttons */
      .stButton > button[kind="secondary"] {{
        border-radius: 8px !important;
        border-color: {UST_LIGHT_TEAL} !important;
        color: {UST_DARK_TEAL} !important;
        font-weight: 500 !important;
      }}

      /* Tabs */
      .stTabs [data-baseweb="tab-list"] {{
        gap: 0.5rem;
      }}
      .stTabs [data-baseweb="tab"] {{
        border-radius: 8px 8px 0 0;
        font-weight: 500;
      }}

      /* Dataframes & expanders */
      .stDataFrame, [data-testid="stExpander"] {{
        border-radius: 8px;
      }}

      /* Hide default Streamlit header/footer clutter */
      #MainMenu {{visibility: hidden;}}
      footer {{visibility: hidden;}}
    </style>
    """


def inject_theme() -> None:
    """Inject UST brand CSS."""
    st.html(_css().strip())


def sidebar_brand() -> None:
    """Render UST branding in the sidebar."""
    st.sidebar.html(
        textwrap.dedent(
            """
            <div class="ust-sidebar-brand">
                <div class="ust-logo">UST</div>
                <div class="ust-product">AI-SDLC Platform</div>
                <div class="ust-tagline">AWS Glue → Azure Synapse</div>
            </div>
            """
        ).strip()
    )


def configure_page(title: str, icon: str = "🔄") -> None:
    """Set page config and apply UST theme. Must be the first Streamlit call."""
    st.set_page_config(
        page_title=f"{title} | UST AI-SDLC",
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    sidebar_brand()


def page_header(title: str, subtitle: str = "", badge: str = "") -> None:
    """Render a branded page hero header."""
    badge_html = (
        f'<div class="ust-badge">{html.escape(badge)}</div>' if badge else ""
    )
    subtitle_html = (
        f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    )
    st.html(
        textwrap.dedent(
            f"""
            <div class="ust-hero">
                {badge_html}
                <h1>{html.escape(title)}</h1>
                {subtitle_html}
            </div>
            """
        ).strip()
    )


def section_title(text: str) -> None:
    """Render a styled section heading."""
    st.html(f'<div class="ust-section-title">{html.escape(text)}</div>')


def info_card(title: str, body: str) -> None:
    """Render a content card."""
    st.html(
        textwrap.dedent(
            f"""
            <div class="ust-card">
                <h3>{html.escape(title)}</h3>
                <p style="margin:0;color:{UST_SOFT_BLACK};line-height:1.55;">
                    {html.escape(body)}
                </p>
            </div>
            """
        ).strip()
    )


def workflow_steps(current: int = 0) -> None:
    """Show migration workflow progress steps."""
    steps = ["Repository", "Plan", "Execute", "Output", "Code", "History"]
    cols = st.columns(len(steps))
    for i, (col, step) in enumerate(zip(cols, steps)):
        with col:
            if i < current:
                st.success(f"✓ {step}")
            elif i == current:
                st.info(f"→ {step}")
            else:
                st.caption(step)
