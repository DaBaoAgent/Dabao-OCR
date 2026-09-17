# -*- coding: utf-8 -*-
"""HTTP API 测试：兼容协议（Umi-OCR）、扩展端点、错误码、CORS。"""

import base64
import json
import threading
import urllib.error
import urllib.request

import pytest

from dabao_ocr.server import DabaoOcrServer, find_free_port
from tests.conftest import IMG_ZH, IMG_ZH2, PDF_SAMPLE


@pytest.fixture(scope="module")
def base_url():
    port = find_free_port(start=18824)
    srv = DabaoOcrServer("127.0.0.1", port)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()
    srv.server_close()


def _req(url, data=None, method=None, raw_body=None, headers=None):
    body = None
    hdrs = dict(headers or {})
    if raw_body is not None:
        body = raw_body
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    use_post = body is not None and (raw_body is not None or data is not None)
    req = urllib.request.Request(url, data=body, method=method or ("POST" if use_post else "GET"), headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, dict(r.headers), json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), json.loads(e.read().decode("utf-8"))


def _b64(img):
    return base64.b64encode(open(img, "rb").read()).decode()


class TestCompatibility:
    def test_get_options(self, base_url):
        st, _, opts = _req(base_url + "/api/ocr/get_options")
        assert st == 200
        assert set(opts.keys()) == {
            "ocr.language", "ocr.angle", "ocr.maxSideLen",
            "tbpu.parser", "tbpu.ignoreArea", "data.format",
        }
        assert opts["ocr.language"]["default"] == "简体中文"
        assert opts["tbpu.parser"]["default"] == "multi_para"
        assert opts["data.format"]["default"] == "dict"
        langs = [x[0] for x in opts["ocr.language"]["optionsList"]]
        assert "English" in langs and "日本語" in langs

    def test_ocr_base64_text(self, base_url):
        payload = {
            "base64": _b64(IMG_ZH),
            "options": {
                "ocr.language": "简体中文",
                "ocr.angle": False,
                "ocr.maxSideLen": 1024,
                "tbpu.parser": "multi_para",
                "data.format": "text",
            },
        }
        st, _, res = _req(base_url + "/api/ocr", payload)
        assert st == 200 and res["code"] == 100
        assert isinstance(res["data"], str)
        assert "系统" in res["data"]

    def test_ocr_base64_dict(self, base_url):
        payload = {"base64": _b64(IMG_ZH)}
        st, _, res = _req(base_url + "/api/ocr", payload)
        assert res["code"] == 100
        assert isinstance(res["data"], list)
        assert all({"box", "score", "text", "end"} <= set(b.keys()) for b in res["data"])

    def test_ocr_path_extension(self, base_url):
        """Dabao-OCR 扩展：path 代替 base64。"""
        payload = {"path": IMG_ZH, "options": {"data.format": "text"}}
        st, _, res = _req(base_url + "/api/ocr", payload)
        assert res["code"] == 100 and "系统" in res["data"]

    def test_cors_headers(self, base_url):
        st, hdrs, _ = _req(base_url + "/api/ocr/get_options")
        assert hdrs.get("Access-Control-Allow-Origin") == "*"


class TestErrorCodes:
    def test_801_empty(self, base_url):
        st, _, res = _req(base_url + "/api/ocr", raw_body=b"")
        assert res["code"] == 801

    def test_800_bad_json(self, base_url):
        st, _, res = _req(base_url + "/api/ocr", raw_body=b"this is not json")
        assert res["code"] == 800

    def test_802_missing_base64(self, base_url):
        st, _, res = _req(base_url + "/api/ocr", {"options": {}})
        assert res["code"] == 802

    def test_803_options_not_dict(self, base_url):
        st, _, res = _req(base_url + "/api/ocr", {"base64": _b64(IMG_ZH), "options": "x"})
        assert res["code"] == 803

    def test_804_bad_ignore_area(self, base_url):
        payload = {"base64": _b64(IMG_ZH), "options": {"tbpu.ignoreArea": "bad"}}
        st, _, res = _req(base_url + "/api/ocr", payload)
        assert res["code"] == 804

    def test_804_bad_language(self, base_url):
        payload = {"base64": _b64(IMG_ZH), "options": {"ocr.language": "火星文"}}
        st, _, res = _req(base_url + "/api/ocr", payload)
        assert res["code"] == 804

    def test_404(self, base_url):
        st, _, res = _req(base_url + "/api/nope")
        assert st == 404


class TestEnhanced:
    def test_status(self, base_url):
        st, _, res = _req(base_url + "/api/status")
        assert res["name"] == "DabaoOCR"
        assert "version" in res and "languages" in res

    def test_batch(self, base_url):
        payload = {
            "images": [{"path": IMG_ZH}, {"path": IMG_ZH2}],
            "options": {"data.format": "text"},
        }
        st, _, res = _req(base_url + "/api/ocr/batch", payload)
        assert res["code"] == 100
        assert len(res["data"]) == 2
        assert "系统" in res["data"][0]["data"] or res["data"][0]["code"] in (100, 101)

    def test_batch_missing_images(self, base_url):
        st, _, res = _req(base_url + "/api/ocr/batch", {"options": {}})
        assert res["code"] == 802

    def test_pdf_text(self, base_url):
        payload = {"path": PDF_SAMPLE, "options": {"dpi": 150}}
        st, _, res = _req(base_url + "/api/pdf", payload)
        assert res["code"] == 100
        assert len(res["data"]) == 2
        assert "Dabao-OCR" in res["data"][0]["text"]

    def test_pdf_base64(self, base_url):
        payload = {"base64": base64.b64encode(open(PDF_SAMPLE, "rb").read()).decode(),
                   "options": {"dpi": 150, "pages": "1"}}
        st, _, res = _req(base_url + "/api/pdf", payload)
        assert res["code"] == 100 and len(res["data"]) == 1

    def test_pdf_missing_input(self, base_url):
        st, _, res = _req(base_url + "/api/pdf", {"options": {}})
        assert res["code"] == 802


class TestPortUtil:
    def test_find_free_port(self):
        p = find_free_port(start=19900)
        assert 19900 <= p < 19920
