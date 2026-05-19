from pathlib import Path


def test_streamlit_entrypoint_is_named_home_for_sidebar_label():
    assert Path("Home.py").exists()

    run_bat = Path("run.bat").read_text(encoding="utf-8")
    run_sh = Path("run.sh").read_text(encoding="utf-8")
    cli = Path("smartvoice/cli.py").read_text(encoding="utf-8")

    assert "streamlit run Home.py" in run_bat
    assert "streamlit run Home.py" in run_sh
    assert '/ "Home.py"' in cli
    assert "streamlit run app.py" not in run_bat
    assert "streamlit run app.py" not in run_sh
    assert '/ "app.py"' not in cli


def test_home_page_branding_describes_call_analytics():
    home = Path("Home.py").read_text(encoding="utf-8")

    assert 'page_title="Thai Call Analytics"' in home
    assert 'st.title("🎙️ Thai Call Analytics")' in home
    assert "AI-powered Call Center Analytics for Thai Customer Calls" in home
    assert 'st.title("🎙️ SmartVoice")' not in home
