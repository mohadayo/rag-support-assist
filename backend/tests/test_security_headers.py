"""SecurityHeadersMiddleware の回帰テスト。

FastAPI の全応答に付与される最小限のセキュリティヘッダを、
成功系 (200) / DB 未接続時 (503) / 未定義パス (404) の 3 経路で固定し、
「特定ルートだけ抜ける」リグレッションを検出する。
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _assert_security_headers(response):
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("referrer-policy") == "no-referrer"


def test_security_headers_are_set_on_200():
    """`/api/health` が 200 (vector_db 接続 OK) を返すとき、
    3 ヘッダがすべて付与されていること。"""
    with patch("app.main.get_chunk_count", return_value=0):
        resp = client.get("/api/health")
    assert resp.status_code == 200
    _assert_security_headers(resp)


def test_security_headers_are_set_on_503():
    """`/api/health` が DB 例外で 503 に落ちた場合でも、
    JSONResponse 経路にセキュリティヘッダが付与されていること。"""
    with patch("app.main.get_chunk_count", side_effect=Exception("boom")):
        resp = client.get("/api/health")
    assert resp.status_code == 503
    _assert_security_headers(resp)


def test_security_headers_are_set_on_404():
    """未定義パス (Starlette 既定 404 ハンドラ) でもヘッダが付くこと。"""
    resp = client.get("/definitely-not-a-real-endpoint-please")
    assert resp.status_code == 404
    _assert_security_headers(resp)


def test_security_headers_do_not_override_existing_values():
    """既に同名ヘッダが応答に載っている場合は上書きしないこと（`setdefault`
    相当の挙動）。将来 per-route オーバーライドを入れたときにも壊れないよう
    固定する。"""
    from fastapi.responses import Response

    @app.get("/__test_override_security_header__")
    async def override_header():
        r = Response(content="{}", media_type="application/json")
        r.headers["X-Content-Type-Options"] = "custom-value"
        return r

    try:
        resp = client.get("/__test_override_security_header__")
        assert resp.status_code == 200
        # 上書きしない: ルート側の "custom-value" が保持される
        assert resp.headers.get("x-content-type-options") == "custom-value"
        # 他 2 ヘッダはミドルウェアが付ける
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "no-referrer"
    finally:
        # 追加したテスト用ルートはグローバル `app` に残り続けるので、
        # 他テストへの副作用を避けるためルーティングテーブルから除去する。
        app.router.routes = [
            r for r in app.router.routes
            if getattr(r, "path", None) != "/__test_override_security_header__"
        ]
