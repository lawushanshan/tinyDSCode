import re
from unittest.mock import patch, MagicMock

from deepseek_code.web_search import web_search, _parse_bing_html, _strip_tags

# Bing 搜索结果页面的简化 HTML 样例
SAMPLE_BING_HTML = """
<ol id="b_results">
<li class="b_algo" data-id iid=SERP.5001>
  <h2><a href="https://docs.python.org/3/tutorial/" target="_blank">The <strong>Python</strong> Tutorial</a></h2>
  <div class="b_caption"><p class="b_lineclamp2">Python tutorial for beginners, covering basic concepts and features of the language.</p></div>
</li>
<li class="b_algo" data-id iid=SERP.5002>
  <h2><a href="https://www.w3schools.com/python/" target="_blank">Python Tutorial - W3Schools</a></h2>
  <div class="b_caption"><p class="b_lineclamp3">Learn Python with W3Schools comprehensive tutorial.</p></div>
</li>
<li class="b_algo" data-id iid=SERP.5003>
  <h2><a href="https://www.runoob.com/python" target="_blank">Python 教程 | 菜鸟教程</a></h2>
  <div class="b_caption"><p class="b_lineclamp4">全面的 Python 入门教程，适合初学者。</p></div>
</li>
</ol>
"""


def test_strip_tags() -> None:
    assert _strip_tags("<b>hello</b>") == "hello"
    assert _strip_tags("<a href='x'>link <em>text</em></a>") == "link text"


def test_parse_bing_html() -> None:
    results = _parse_bing_html(SAMPLE_BING_HTML, 10)
    assert len(results) == 3
    assert "Python Tutorial" in results[0]["title"]
    assert "python" in results[0]["title"].lower()
    assert results[0]["url"] == "https://docs.python.org/3/tutorial/"
    assert "beginners" in results[0]["snippet"]
    assert "W3Schools" in results[1]["title"]
    assert results[1]["url"] == "https://www.w3schools.com/python/"


def test_parse_bing_html_max_count() -> None:
    results = _parse_bing_html(SAMPLE_BING_HTML, 2)
    assert len(results) == 2


def test_parse_bing_html_empty() -> None:
    results = _parse_bing_html("<html><body>no results</body></html>", 5)
    assert results == []


def test_web_search_success() -> None:
    with patch("deepseek_code.web_search.httpx.Client") as mock_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = SAMPLE_BING_HTML
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_cls.return_value = mock_client

        result = web_search("Python", count=3)
        assert "搜索: Python" in result
        assert "3 条结果" in result
        assert "Python Tutorial" in result
        assert "W3Schools" in result


def test_web_search_no_results() -> None:
    with patch("deepseek_code.web_search.httpx.Client") as mock_cls:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body></body></html>"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_cls.return_value = mock_client

        result = web_search("xyznonexistent123")
        assert "未找到" in result


def test_web_search_network_error() -> None:
    with patch("deepseek_code.web_search.httpx.Client") as mock_cls:
        from httpx import ConnectError
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = ConnectError("connection refused")
        mock_cls.return_value = mock_client

        result = web_search("test")
        assert "搜索失败" in result
        assert "网络" in result
