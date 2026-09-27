# SNS自動投稿 セットアップ手順（Facebookページ / Threads）

毎朝8:00 JSTにGmailへ届く下書きメールの「【Threads投稿】」部分を、8:52 JSTに自動で投稿する仕組みです。

| 下書きメール | 投稿先 |
|---|---|
| 【本日のSNS下書き】 | Threads（本人アカウント）＋ Facebookページ |
| 【BISTARGO本日のnote+Threads下書き】 | Threads（BISTARGOアカウント・任意）＋ Facebookページ |

note には公式APIが無いため、note記事は今まで通り手動投稿です。

## 0. ルーティン「SNS自動投稿」を作る（1回だけ・claude.ai の画面で）

Claude 側の制限で、Gmail連携付きのルーティンは本人がルーティン画面から作る必要があります（エージェントからは Gmail 連携を付けられません）。

1. https://claude.ai/code/routines を開く
2. **新しいルーティン（New routine）** を押す
3. 次のとおり設定する
   - 名前: `SNS自動投稿(Threads+Facebook 朝8:52)`
   - スケジュール: 毎日 **8:52**（タイムゾーン Asia/Tokyo）
   - 環境: 今使っているクラウド環境（既存の「AI秘書」「note作成」と同じもの）
   - **コネクタ（Connectors）: Gmail をオン** ← これが無いと下書きメールを読めません
   - プロンプト: このフォルダの `ROUTINE_PROMPT.md` の中身を**全文そのまま**貼り付ける
4. 保存する

同じ環境なので、環境変数（下記）はこのルーティンからも読めます。

## 必要なもの（環境変数）

| 変数名 | 内容 | 必須 |
|---|---|---|
| `THREADS_ACCESS_TOKEN` | Threads API の長期アクセストークン（本人アカウント） | Threadsに出すなら必須 |
| `THREADS_ACCESS_TOKEN_BISTARGO` | 同上（BISTARGO用アカウント） | 任意 |
| `FB_PAGE_ACCESS_TOKEN` | Facebookページのアクセストークン | Facebookに出すなら必須 |
| `FB_PAGE_ID` | FacebookページのID | 任意（トークンから自動取得） |

登録場所: Claude Code の画面上部にある **クラウド環境メニュー → Edit（編集）→ Environment variables（環境変数）**。
トークンをチャットに貼らないでください。登録後に開いた新しいセッションから自動で読み込まれます。

## 1. Metaアプリを作る（共通・1回だけ）

1. https://developers.facebook.com/apps/ を開く（Meta for Developers の登録は 2026-09-21 に済んでいます）
2. **Create App（アプリを作成）** を押す
3. 用途（Use cases）で次の2つにチェック
   - **Access the Threads API**（Threads APIにアクセス）
   - **Manage everything on your Page**（ページのすべてを管理）※Facebookページ投稿用
4. アプリ名は「Ryujin SNS Autopost」など自由。作成する

## 2. Threads のトークンを取る

1. 作ったアプリの左メニュー **Use cases → Access the Threads API → Customize（カスタマイズ）**
2. **Permissions（アクセス許可）** で `threads_basic` と `threads_content_publish` を **Add（追加）**
3. **Settings → Threads tester（Threadsテスター）**、または **Roles → Roles** で、投稿したいThreadsアカウントを **Add Threads Testers** で追加
4. スマホの Threads アプリを開く → **設定 → アカウント → ウェブサイトのアクセス許可 → 招待** で承認
5. Threads の Use case 画面に戻り、**Generate access token（アクセストークンを生成）** → 対象アカウントでログインし承認
6. 表示されたトークンは短期（1時間）なので、次のURLをブラウザで開いて **長期トークン（60日）** に交換する
   ```
   https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=（アプリのシークレット）&access_token=（短期トークン）
   ```
   アプリのシークレットは **App settings → Basic → App secret（Show）** にあります。
7. 返ってきた `access_token` を `THREADS_ACCESS_TOKEN` として環境に登録
8. BISTARGO用のアカウントでも同じことをして、`THREADS_ACCESS_TOKEN_BISTARGO` に登録（任意）

長期トークンは60日で切れます。期限前に次のURLで更新できます（更新もいずれ自動化できます）。
```
https://graph.threads.net/refresh_access_token?grant_type=th_refresh_token&access_token=（今の長期トークン）
```

## 3. Facebookページのトークンを取る

1. https://developers.facebook.com/tools/explorer/ （Graph API Explorer）を開く
2. 右上 **Meta App** で手順1のアプリを選ぶ
3. **User or Page** で **Get Page Access Token** → 「Ryujin Welfare Organization」のページを選ぶ
4. **Permissions** に `pages_manage_posts` と `pages_read_engagement` を追加 → **Generate Access Token** → 承認
5. 表示されたページトークンをコピーし、`FB_PAGE_ACCESS_TOKEN` として登録
   - このページトークンは、ユーザートークンが短期のままだと約1時間で切れます。
   - 切れないようにするには、先に **Access Token Debugger（https://developers.facebook.com/tools/debug/accesstoken/）→ Extend Access Token** でユーザートークンを長期化してから、手順3で **Get Page Access Token** をやり直します。こうして取ったページトークンは無期限になります。
6. ページIDは自動取得されるので `FB_PAGE_ID` は省略可

## 4. 動作確認

環境変数を登録した後に新しいセッションを開き、次を実行します。

```bash
python3 sns-autopost/sns_autopost.py whoami
```

`OK  Threads @xxxx` `OK  Facebookページ「Ryujin Welfare Organization」` と出れば準備完了です。
翌朝8:52 JSTのルーティン「SNS自動投稿」が投稿し、結果を件名「【SNS自動投稿 完了】YYYY-MM-DD」でGmailに送ります。

## 注意

- トークンが未設定の間は投稿せず、週1回だけ「【SNS自動投稿 未設定】」メールでお知らせします。
- Threadsは500字制限です。下書きが超えている日は投稿せずエラー報告します（勝手に削りません）。
- 同じ日に2回投稿しないよう、完了メールの有無で重複チェックしています。
