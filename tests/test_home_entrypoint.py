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
    assert 'st.title("Thai Call Analytics")' in home
    assert "AI-powered Call Center Analytics for Thai Customer Calls" in home
    assert 'st.title("SmartVoice")' not in home


def test_ui_labels_are_words_not_decorative_icons():
    """Labels have to say what they mean — the emoji that used to stand in for
    a word are gone from every page and shared helper."""
    import re

    emoji = re.compile(
        "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
    )
    sources = [Path("Home.py"), Path("smartvoice/ui_helpers.py"), Path("smartvoice/audit.py")]
    sources += sorted(Path("pages").glob("*.py"))

    offenders = []
    for path in sources:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # `pages/1_📤_Admin.py` and friends are file paths on disk, not labels.
            if "pages/" in line:
                continue
            if emoji.search(line):
                offenders.append(f"{path.name}:{number}: {line.strip()[:60]}")

    assert not offenders, "decorative icons left in the UI:\n" + "\n".join(offenders)


def test_router_uses_st_navigation_so_pages_dir_menu_is_disabled():
    home = Path("Home.py").read_text(encoding="utf-8")

    # st.navigation switches Streamlit off the automatic pages/ menu, which is
    # what keeps role-restricted pages out of the sidebar entirely.
    assert "st.navigation(" in home
    assert "visible_pages(" in home


def test_every_declared_page_has_a_route_and_a_file():
    from smartvoice import auth

    home = Path("Home.py").read_text(encoding="utf-8")
    for page_key in auth.PAGE_ORDER:
        assert f"PAGE_{page_key.upper()}: dict(" in home, f"no route for {page_key}"

    for path in Path("pages").glob("*.py"):
        assert path.name in home, f"{path.name} is not routed from Home.py"


def test_every_page_file_enforces_its_role_permission():
    from smartvoice import auth

    guarded = {
        "1_📤_Admin.py": auth.PAGE_ADMIN,
        "2_📊_Dashboard.py": auth.PAGE_DASHBOARD,
        "3_👥_Customers.py": auth.PAGE_CUSTOMERS,
        "4_Settings.py": auth.PAGE_SETTINGS,
        "5_👤_Users.py": auth.PAGE_USERS,
        "6_➕_Data_Entry.py": auth.PAGE_DATA_ENTRY,
        "7_📜_Audit_Log.py": auth.PAGE_AUDIT,
    }
    for filename, page_key in guarded.items():
        source = Path("pages") / filename
        assert source.exists(), f"missing page file {filename}"
        text = source.read_text(encoding="utf-8")
        assert f"init_page(PAGE_{page_key.upper()})" in text, f"{filename} is unguarded"


def test_change_password_lives_in_the_sidebar_account_box_not_on_the_home_page():
    home = Path("Home.py").read_text(encoding="utf-8")
    ui_helpers = Path("smartvoice/ui_helpers.py").read_text(encoding="utf-8")

    # The home page is the call dashboard; account actions belong next to the
    # signed-in user in the sidebar, where every page can reach them.
    assert "_change_password_form" not in home
    assert "_render_my_account" not in home

    assert "def render_change_password()" in ui_helpers
    assert "render_change_password()" in ui_helpers.split("def render_sidebar_account()")[1]
    assert "_change_password_form" in ui_helpers
    # The stale-default-password warning must point at the box that now owns it.
    assert "กรุณาเปลี่ยนที่หน้าแรก" not in ui_helpers


def test_login_no_longer_lets_a_visitor_pick_their_own_role():
    ui_helpers = Path("smartvoice/ui_helpers.py").read_text(encoding="utf-8")

    assert "STAFF_ROLES" not in ui_helpers
    assert 'st.selectbox("บทบาท"' not in ui_helpers
