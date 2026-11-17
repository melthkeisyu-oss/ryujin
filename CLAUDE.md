# ryujin（Claude Codeの運用ルール）

返答・途中報告はすべて日本語で、短く結論から書く。

## Obsidianへの記録（必須）

このリポジトリで作業したセッション（スケジュールタスクの自動実行も含む）は、終わるときに会話と作業の内容をObsidianに送る。
中継は非公開リポジトリ `melthkeisyu-oss/obsidian-claude`。同期タスク「Obsidian同期」が、毎日12:43と21:43にObsidianの保管庫「KEISHU TANAKA」へ移す。

1. `git clone --depth 1 https://github.com/melthkeisyu-oss/obsidian-claude /tmp/obsidian-claude`
2. `inbox/会話ログ/YYYY-MM-DD_題名.md` を新しく作る。書く内容は、きっかけ・決まったこと・使った数字・作ったもの（リンク）・残りの作業。
3. `inbox/作業ログ.md` の末尾に `- YYYY-MM-DD HH:MM（Code・ryujin）内容` の形で1行追記する。
4. `git add inbox && git commit -m "Code: 題名" && git push origin main`
5. `mirror/` には書かない。パスワード・APIキー・トークン・口座番号・マイナンバーは書かない。

定時の自動投稿のように毎回同じ作業をする場合は、会話ログは作らなくてよい。作業ログへの1行の追記だけにする。
