"""使用實際密碼表單登入後進行既有製片回歸；這個密碼只存在測試中。"""
from pathlib import Path
from streamlit.testing.v1 import AppTest

TEST_PASSWORD = "test-only-access-password-測試"


def authenticated_app():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90)
    app.secrets["APP_PASSWORD"] = TEST_PASSWORD
    app.run()
    app.text_input(key="_access_password").input(TEST_PASSWORD)
    next(b for b in app.button if b.label == "進入工作室").click().run()
    return app
