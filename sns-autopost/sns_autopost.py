#!/usr/bin/env python3
"""SNS自動投稿スクリプト（Facebookページ / Threads）

毎朝Gmailに届く下書きメール（【本日のSNS下書き】【BISTARGO本日のnote+Threads下書き】）の
本文から「【Threads投稿】」セクションを取り出し、Meta Graph API で投稿する。

使い方:
  # 下書きメール本文（プレーンテキスト）を渡して抽出だけ確認する
  python3 sns_autopost.py extract --in draft.txt

  # 抽出した本文を Threads と Facebook ページに投稿する
  python3 sns_autopost.py post --in draft.txt --threads --facebook

  # 実際には投稿せず、送る内容だけ表示する
  python3 sns_autopost.py post --in draft.txt --threads --facebook --dry-run

  # 本文そのものを渡す（抽出しない）
  python3 sns_autopost.py post --text-file post.txt --facebook

  # トークンが正しいか確認する
  python3 sns_autopost.py whoami

環境変数（環境設定の「環境変数 / API credentials」に登録する。チャットには貼らない）:
  THREADS_ACCESS_TOKEN            Threads API のアクセストークン（個人アカウント用）
  THREADS_ACCESS_TOKEN_BISTARGO   Threads API のアクセストークン（BISTARGO用・任意）
  FB_PAGE_ACCESS_TOKEN            Facebookページのアクセストークン（pages_manage_posts 権限）
  FB_PAGE_ID                      Facebookページの ID（省略時はトークンから自動取得）

終了コード: 0=成功 / 2=トークン未設定 / 1=その他の失敗
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse

import requests

GRAPH_FB = "https://graph.facebook.com/v21.0"
GRAPH_THREADS = "https://graph.threads.net/v1.0"
THREADS_MAX_LEN = 500
EXIT_NO_TOKEN = 2


# ---------------------------------------------------------------------------
# 抽出
# ---------------------------------------------------------------------------
_GOOGLE_REDIRECT = re.compile(r"https://www\.google\.com/url\?q=([^&\s]+)[^\s]*")
_RULE_CHARS = "=＝\\-－_─━"
# 見出しの書式は日によって変わる:
#   【Threads投稿】 / 【Threads投稿 全文】 / Threads投稿 / ==== Threads投稿 ====
_SECTION_HEAD = re.compile(r"^[" + _RULE_CHARS + r"\s]*【?Threads投稿[^】\n" + _RULE_CHARS + r"]*】?[" + _RULE_CHARS + r"\s]*$")
# セクションの終わり: 罫線だけの行 / 【…】見出し / ==== 見出し ==== 形式の行
_RULE = re.compile(r"^[" + _RULE_CHARS + r"]{5,}\s*$")
_ANY_HEAD = re.compile(r"^[" + _RULE_CHARS + r"\s]*【[^】]+】[" + _RULE_CHARS + r"\s]*$")
_WRAPPED_HEAD = re.compile(r"^[" + _RULE_CHARS + r"]{3,}\s*\S.*?\s*[" + _RULE_CHARS + r"]{3,}\s*$")


def unwrap_google_links(text: str) -> str:
    """Gmailのプレーンテキストで https://www.google.com/url?q=... に包まれたURLを元に戻す。"""

    def _repl(m: re.Match) -> str:
        return urllib.parse.unquote(m.group(1))

    return _GOOGLE_REDIRECT.sub(_repl, text)


def _is_boundary(line: str) -> bool:
    s = line.strip()
    return bool(_RULE.match(s) or _ANY_HEAD.match(s) or _WRAPPED_HEAD.match(s))


def extract_threads_section(body: str) -> str:
    """下書きメール本文から Threads投稿 セクションの本文だけを返す。無ければ空文字。"""
    lines = body.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _SECTION_HEAD.match(line.strip()):
            start = i + 1
            break
    if start is None:
        return ""
    # 見出し直後の罫線・空行をスキップ
    while start < len(lines) and (_RULE.match(lines[start].strip()) or not lines[start].strip()):
        start += 1
    out: list[str] = []
    for line in lines[start:]:
        if _is_boundary(line):
            break
        out.append(line.rstrip())
    text = "\n".join(out).strip()
    return unwrap_google_links(text)


class ApiError(RuntimeError):
    pass


def _check(resp: requests.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        data = {"raw": resp.text}
    if resp.status_code >= 400 or "error" in data:
        raise ApiError(f"HTTP {resp.status_code}: {json.dumps(data, ensure_ascii=False)}")
    return data


def threads_me(token: str) -> dict:
    r = requests.get(f"{GRAPH_THREADS}/me", params={"fields": "id,username", "access_token": token}, timeout=30)
    return _check(r)


def threads_post(token: str, text: str, dry_run: bool = False) -> dict:
    if len(text) > THREADS_MAX_LEN:
        raise ApiError(f"Threads本文が{THREADS_MAX_LEN}字を超えています（{len(text)}字）")
    me = threads_me(token)
    user_id = me["id"]
    if dry_run:
        return {"dry_run": True, "account": me.get("username"), "text": text}
    r = requests.post(
        f"{GRAPH_THREADS}/{user_id}/threads",
        data={"media_type": "TEXT", "text": text, "access_token": token},
        timeout=60,
    )
    container = _check(r)["id"]
    # コンテナが処理されるまで少し待つ（公式推奨は約30秒だが、テキストは通常すぐ終わる）
    for _ in range(10):
        s = requests.get(
            f"{GRAPH_THREADS}/{container}",
            params={"fields": "status,error_message", "access_token": token},
            timeout=30,
        )
        status = _check(s).get("status")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise ApiError(f"Threadsコンテナ処理失敗: {_check(s)}")
        time.sleep(3)
    r = requests.post(
        f"{GRAPH_THREADS}/{user_id}/threads_publish",
        data={"creation_id": container, "access_token": token},
        timeout=60,
    )
    media_id = _check(r)["id"]
    p = requests.get(
        f"{GRAPH_THREADS}/{media_id}",
        params={"fields": "id,permalink", "access_token": token},
        timeout=30,
    )
    info = _check(p)
    return {"account": me.get("username"), "id": media_id, "permalink": info.get("permalink")}


def fb_page_info(token: str, page_id: str | None) -> dict:
    target = page_id or "me"
    r = requests.get(f"{GRAPH_FB}/{target}", params={"fields": "id,name", "access_token": token}, timeout=30)
    return _check(r)


def fb_page_post(token: str, page_id: str | None, text: str, dry_run: bool = False) -> dict:
    page = fb_page_info(token, page_id)
    if dry_run:
        return {"dry_run": True, "page": page.get("name"), "page_id": page["id"], "text": text}
    r = requests.post(
        f"{GRAPH_FB}/{page['id']}/feed",
        data={"message": text, "access_token": token},
        timeout=60,
    )
    post_id = _check(r)["id"]
    return {"page": page.get("name"), "id": post_id, "permalink": f"https://www.facebook.com/{post_id}"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _read_text(args: argparse.Namespace) -> str:
    if args.text_file:
        with open(args.text_file, encoding="utf-8") as f:
            return unwrap_google_links(f.read().strip())
    src = sys.stdin.read() if args.infile == "-" else open(args.infile, encoding="utf-8").read()
    text = extract_threads_section(src)
    if not text:
        print("ERROR: 【Threads投稿】セクションが見つかりません", file=sys.stderr)
        sys.exit(1)
    return text


def cmd_extract(args: argparse.Namespace) -> int:
    text = _read_text(args)
    print(text)
    print(f"\n--- {len(text)}字 ---", file=sys.stderr)
    return 0


def cmd_whoami(_: argparse.Namespace) -> int:
    ok = True
    for env in ("THREADS_ACCESS_TOKEN", "THREADS_ACCESS_TOKEN_BISTARGO"):
        tok = os.environ.get(env)
        if not tok:
            print(f"{env}: 未設定")
            continue
        try:
            me = threads_me(tok)
            print(f"{env}: OK  Threads @{me.get('username')} (id {me['id']})")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"{env}: NG  {e}")
    tok = os.environ.get("FB_PAGE_ACCESS_TOKEN")
    if not tok:
        print("FB_PAGE_ACCESS_TOKEN: 未設定")
    else:
        try:
            page = fb_page_info(tok, os.environ.get("FB_PAGE_ID"))
            print(f"FB_PAGE_ACCESS_TOKEN: OK  Facebookページ「{page.get('name')}」(id {page['id']})")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"FB_PAGE_ACCESS_TOKEN: NG  {e}")
    return 0 if ok else 1


def cmd_post(args: argparse.Namespace) -> int:
    text = _read_text(args)
    results: dict[str, object] = {}
    missing: list[str] = []
    failed = False

    if args.threads:
        env = "THREADS_ACCESS_TOKEN_BISTARGO" if args.account == "bistargo" else "THREADS_ACCESS_TOKEN"
        tok = os.environ.get(env)
        if not tok:
            missing.append(env)
        else:
            try:
                results["threads"] = threads_post(tok, text, dry_run=args.dry_run)
            except Exception as e:  # noqa: BLE001
                failed = True
                results["threads"] = {"error": str(e)}

    if args.facebook:
        tok = os.environ.get("FB_PAGE_ACCESS_TOKEN")
        if not tok:
            missing.append("FB_PAGE_ACCESS_TOKEN")
        else:
            try:
                results["facebook"] = fb_page_post(tok, os.environ.get("FB_PAGE_ID"), text, dry_run=args.dry_run)
            except Exception as e:  # noqa: BLE001
                failed = True
                results["facebook"] = {"error": str(e)}

    if missing:
        results["missing_env"] = missing
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if failed:
        return 1
    if missing and len(missing) == int(args.threads) + int(args.facebook):
        return EXIT_NO_TOKEN
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SNS自動投稿（Facebookページ / Threads）")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_input(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--in", dest="infile", default="-", help="下書きメール本文のファイル（- で標準入力）")
        sp.add_argument("--text-file", help="抽出せず、このファイルの内容をそのまま投稿する")

    sp = sub.add_parser("extract", help="【Threads投稿】セクションを抽出して表示")
    add_input(sp)
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("post", help="投稿する")
    add_input(sp)
    sp.add_argument("--threads", action="store_true", help="Threads に投稿")
    sp.add_argument("--facebook", action="store_true", help="Facebookページに投稿")
    sp.add_argument("--account", choices=["personal", "bistargo"], default="personal", help="Threads のアカウント")
    sp.add_argument("--dry-run", action="store_true", help="投稿せず内容だけ表示")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("whoami", help="トークンの確認")
    sp.set_defaults(func=cmd_whoami)

    args = p.parse_args(argv)
    if args.cmd == "post" and not (args.threads or args.facebook):
        p.error("--threads か --facebook の少なくとも一方を指定してください")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
