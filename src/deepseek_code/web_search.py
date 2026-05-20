from __future__ import annotations

import re

import httpx

BING_SEARCH_URL = "https://www.bing.com/search"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def web_search(query: str, count: int = 5) -> str:
    count = max(1, min(count, 10))

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(
                BING_SEARCH_URL,
                params={"q": query, "count": count},
                headers=_HEADERS,
            )
    except httpx.ConnectError:
        return "[搜索失败] 无法连接到 Bing，请检查网络。"
    except httpx.TimeoutException:
        return "[搜索失败] 请求超时。"

    if resp.status_code != 200:
        return f"[搜索失败] HTTP {resp.status_code}"

    results = _parse_bing_html(resp.text, count)
    if not results:
        return f"未找到与 '{query}' 相关的结果。"

    lines = [f"搜索: {query}（共 {len(results)} 条结果）\n"]
    for i, item in enumerate(results, 1):
        lines.append(f"{i}. {item['title']}\n   {item['url']}\n   {item['snippet']}\n")
    return "\n".join(lines)


def _parse_bing_html(html: str, max_count: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    blocks = re.findall(
        r'<li[^>]*class="b_algo[^"]*"[^>]*>.*?</li>',
        html, re.DOTALL,
    )

    for block in blocks:
        if len(results) >= max_count:
            break

        # 提取标题和 URL
        h2m = re.search(
            r'<h2[^>]*><a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>',
            block, re.DOTALL,
        )
        if not h2m:
            continue

        url = h2m.group(1)
        title = _strip_tags(h2m.group(2)).strip()
        if not title:
            continue

        # 提取摘要（b_lineclamp 或 b_caption 中的文本）
        snippet = ""
        for pattern in [
            r'<p[^>]*class="b_lineclamp[^"]*"[^>]*>(.*?)</p>',
            r'<div[^>]*class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>',
        ]:
            m = re.search(pattern, block, re.DOTALL)
            if m:
                snippet = _strip_tags(m.group(1)).strip()
                break

        results.append({
            "title": title,
            "url": url,
            "snippet": snippet or "无摘要",
        })

    return results


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub("", html)
