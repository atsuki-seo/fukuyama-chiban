# PWA 対応 設計書

福山市 地番マップをホーム画面／デスクトップにインストールできる PWA にする。
本書はタスク分割と、各タスクの機械的に検証可能なゴールを定義する。

## 1. 方針

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| 動作前提 | **オンライン前提**。オフライン閲覧（地図・検索）は対象外 | オフライン利用が必要ならデスクトップアプリの案件。PMTiles は約 155 MB、検索索引は約 21 MB あり、端末保存は割に合わない |
| インストール導線 | **Chromium 系の自動インストール案内を有効にする**。iOS は手順の案内文で補う | 自動案内があるほうが導線として強い。iOS Safari には自動案内の仕組みがない |
| Service Worker（SW） | **画面遷移（`mode: 'navigate'`）だけを扱う最小 SW** を入れる | 自動案内の条件に fetch handler が要る。空の handler は Chrome に無視される（§2） |
| SW の介入範囲 | 画面遷移以外は `respondWith` しない。PMTiles・地理院タイル・地理院の最適化ベクトルタイル・unpkg・検索 JSON は素通し | Cache API は 206 を保存できず、Range を横取りすると PMTiles が壊れる。地理院タイルは規約上のキャッシュ可否を確認できていない |
| キャッシュ | `offline.html` の 1 件だけ | `index.html` は常にネットワークから取るので、更新時の古い版の残留が起きない |
| 更新 | 新しい SW は `skipWaiting` と `clients.claim` で即時に有効化。更新案内のトーストは作らない | SW がアプリ本体をキャッシュしないため、即時の切り替えでも版の食い違いが起きない |
| 緊急停止 | 自分自身を登録解除してキャッシュを消す SW を用意する | 一度配信した SW は利用者の端末に残り続ける |
| テスト基盤 | Node と Playwright（Chromium）を `tools/pwa-test/` に置く | CDP の `Page.getInstallabilityErrors` / `Page.getAppManifest` を合否判定に使える。Lighthouse の PWA カテゴリは廃止済み |

### 対象外

- 地図タイル・検索索引のオフライン対応、見た範囲のキャッシュ
- 地理院タイルの SW キャッシュ
- プッシュ通知、バックグラウンド同期
- GitHub Actions などの CI 化（必要になったら別途）

## 2. 前提となる事実

| 事実 | 根拠 |
| --- | --- |
| Chrome はメニューからのインストールについて、fetch handler 付き SW の要件を撤廃した（モバイル 108、デスクトップ 112 以降） | [Revisiting Chrome's installability criteria](https://developer.chrome.com/blog/update-install-criteria)（最終更新 2023-12-05） |
| 同記事の時点で、自動のインストール案内は fetch handler を条件にしている。空の handler は Chrome が無視する | 同上 |
| インストール条件：HTTPS、manifest（`name` か `short_name`、192px と 512px のアイコン、`start_url`、`display`、`prefer_related_applications` が無いか `false`）、エンゲージメント（クリックと 30 秒以上の閲覧） | [web.dev: install criteria](https://web.dev/articles/install-criteria) |
| Cache API は 206 応答を保存できない | [web.dev: Handle range requests in a service worker](https://web.dev/articles/sw-range-requests) |
| Lighthouse の PWA カテゴリは廃止済み | [tessl.io: lighthouse pwa audit](https://tessl.io/registry/testland/lighthouse-pwa-audit)（二次情報） |
| 地番データは PMTiles を HTTP Range で読む。道路は地理院の PMTiles を別オリジンから直接読む | `index.html` の `buildStyle()` |
| unpkg の 3 ファイルは SRI 付き・`crossorigin="anonymous"` で読む | `index.html` の `<head>` |
| `BASE` は `location.href` から求めている。配信先は GitHub Pages のサブパス | `index.html` の `const BASE`、`.nojekyll` |
| バージョンの一元管理先は `APP.version` | `index.html` の `APP` 定数 |
| `.claude/launch.json` は別セッションの scratchpad にある `rangeserver.py` を参照している | `.claude/launch.json` |
| safe-area を考慮しているのは 768px 未満のレイアウトだけ | `index.html` の `@media (max-width: 767.98px)` |

## 3. 全体構成

```
index.html             <link rel="manifest">、theme-color、apple-touch-icon などを追加
                       SW の登録、インストールボタン、iOS 向け案内、共有ボタン
manifest.webmanifest   start_url / scope = "./"（id は書かない。§7）
icons/                 icon-192.png, icon-512.png, icon-maskable-512.png, apple-touch-icon.png
sw.js                  画面遷移だけを扱う SW（VERSION は APP.version と一致させる）
offline.html           外部依存のない単体ページ。「オンラインで使ってください」
tools/serve.py         Range に 206 で応答する静的サーバー（テスト用の上書き機能つき）
tools/pwa-test/        Playwright 一式（node_modules は .gitignore）
tools/sw-killswitch.js 緊急停止版の sw.js
```

GitHub Pages は `.github/workflows/pages.yml` が列挙したパスだけを公開する。
`manifest.webmanifest`、`icons/`、`sw.js`、`offline.html` は、追加するタスク（T1・T3）でこのワークフローの公開対象にも加える。

### sw.js の振る舞い

```text
install  : offline.html を caches(`fukuyama-chiban-${VERSION}`) に保存 → skipWaiting()
activate : navigationPreload.enable()
           名前が現在の版と違うキャッシュを削除
           clients.claim()
fetch    : request.mode === 'navigate' のときだけ
             respondWith(preloadResponse ?? fetch(request))
             失敗したら offline.html を返す
           それ以外は何もしない（respondWith を呼ばない）
```

### インストール導線の振る舞い

| 状況 | 表示 |
| --- | --- |
| `beforeinstallprompt` を受け取った（Chromium 系） | パネルに「アプリとしてインストール」ボタン。押すと `prompt()` を呼ぶ |
| `appinstalled` を受け取った | ボタンを隠す |
| iOS Safari で、スタンドアロン表示でない | ボタンの代わりに「共有 → ホーム画面に追加」の手順を表示 |
| スタンドアロン表示中（`display-mode: standalone` または `navigator.standalone`） | どちらも出さない |

## 4. タスクと検証可能なゴール

ゴールはすべて `tools/pwa-test` のテスト（`npm test`）か node スクリプトで合否が出る形にする。
例外は「手動」と明記したものだけ。

### T0. 検証基盤

内容

- `tools/serve.py`：Range に 206 で応答する静的サーバー。テスト用に、指定したパスの応答内容を差し替えられるようにする（`sw.js` の v2 や緊急停止版を返すため）。
- `.claude/launch.json` を `tools/serve.py` を指すように直す。
- `tools/pwa-test/`：`package.json`、Playwright（Chromium）、テスト一式。`.gitignore` に `node_modules/` を追加。
- 起動フラグ `--bypass-app-banner-engagement-checks` が現行の Chromium でも効くか確かめる（フラグ名は記憶ベースで未確認）。効かなければ G4-1 を格下げする（T4 を参照）。

ゴール

- **G0-1** `#map=17/34.490/133.362` を開くと `map.querySourceFeatures('city-1', {sourceLayer: 'chiban'}).length > 0` になる。
  - 当初は `city-0` としていたが、34.490°N は中央の帯（`chiban_fukuyama_2026_1.pmtiles`、PMTiles ヘッダーの範囲 34.456〜34.538°N）に入り、`city-0` は 34.525°N 以北なので 0 件になる。§7 を参照。
- **G0-2** 検索で「青葉台一丁目 4-1」を引くと結果が 1 件以上出る。
  - 完全一致は 1 件で、結果一覧を出さずにその地点へ移動する。テストでは「青葉台一丁目 4-1 に移動します」の表示とマーカー 1 個で判定する。
- **G0-3** `tools/serve.py` に `Range: bytes=0-15` を付けて `.pmtiles` を取得すると、206 で 16 バイトが返る。
- G0-1 と G0-2 は、変更前の main で通ることを確認してから以降のタスクに進む（回帰テストの基準）。

### T1. manifest・アイコン・meta タグ

内容

- `manifest.webmanifest`：`name`「福山市 地番マップ」、`short_name`、`start_url`・`scope` は `./`、`id` は書かない（`start_url` と同じになる。§7）、`display: standalone`、`lang: ja`、`theme_color`・`background_color`、アイコン 3 種。
- アイコンは今の SVG favicon から PNG を生成する（192、512、maskable 512、apple-touch-icon 180）。生成手順は README に書く。
- `index.html` に `<link rel="manifest">`、`<meta name="theme-color">`、`<link rel="apple-touch-icon">`、`<meta name="apple-mobile-web-app-title">` を追加する。

ゴール

- **G1-1** CDP の `Page.getInstallabilityErrors` が空配列を返す（localhost で確認）。
- **G1-2** CDP の `Page.getAppManifest` で解析エラーが 0 件。`start_url`・`scope`・`id` がページの `BASE` と一致し、`display === 'standalone'`、`lang === 'ja'`。
- **G1-3** manifest の `theme_color` が `<meta name="theme-color">` の値と一致する。
- **G1-4** manifest に書いたアイコンがすべて 200 で返り、PNG ヘッダー（IHDR）の実寸が `sizes` と一致する。192 と 512 があり、`purpose` に `maskable` を含むものが 1 つ以上ある。
- **G1-5** `apple-touch-icon` が 180×180 の PNG を指している。

### T2. 共有ボタン

スタンドアロン表示ではアドレスバーがなく、URL ハッシュで地点を共有できなくなるため。

内容

- 「この地点を共有」ボタンを追加する。`navigator.share` が使えれば使い、なければクリップボードに `location.href` をコピーしてトーストで知らせる。

ゴール

- **G2-1** `navigator.share` を無効にした状態でボタンを押すと、クリップボードに `#map=` を含む現在の URL が入る（クリップボード権限を許可して確認）。
- **G2-2** G0-1 と G0-2 が引き続き通る。

### T3. 画面遷移だけを扱う SW

内容

- `sw.js`、`offline.html`、`index.html` での SW 登録（`load` の後）。
- `sw.js` の `VERSION` は `APP.version` と同じ値にする。

ゴール

- **G3-1** リロード後に `navigator.serviceWorker.controller` が null でなく、登録の `scope` が `BASE` と一致する。
- **G3-2** ページ本体の読み込みが SW を経由している（`performance.getEntriesByType('navigation')[0].workerStart > 0`）。
- **G3-3** `.pmtiles`、`cyberjapandata.gsi.go.jp`、`unpkg.com`、`search*.json` の応答がすべて SW を経由しない（`response.fromServiceWorker() === false`）。PMTiles は 206 で返り、G0-1 が通る。
- **G3-4** `context.setOffline(true)` にしてリロードすると、`offline.html` の目印となる要素（例：`[data-offline-page]`）が表示される。
- **G3-5** `caches.keys()` が 1 件だけで、その中身は `offline.html` の 1 件だけ。
- **G3-6** 静的チェックスクリプトで、`sw.js` の `VERSION` と `index.html` の `APP.version` が一致する。
- **G3-7** v1 を入れた状態で、サーバーが v2 の `sw.js` を返すようにしてリロードすると、v2 が有効になり、`caches.keys()` に v1 のキャッシュ名が残らない。
- **G3-8** コンソールのエラーが、変更前の main と比べて増えていない。

### T4. インストール導線

内容

- §3「インストール導線の振る舞い」の表どおりに実装する。

ゴール

- **G4-1** エンゲージメント条件を飛ばした Chromium で `beforeinstallprompt` が発火し、インストールボタンが表示される。
  - T0 でフラグが効かないと分かった場合は、疑似イベント（`new Event('beforeinstallprompt')` に `prompt` を生やしたもの）を発火させて UI の動きだけを検証する。格下げしたことをテスト名とこの設計書に記録する。
- **G4-2** `appinstalled` を発火させるとボタンが消える。
- **G4-3** iPhone として振る舞う設定（Playwright の `devices['iPhone 15']` の UA を Chromium で使う）では、ボタンが出ずに手順の文言が出る。
- **G4-4** スタンドアロン表示中は、ボタンも手順の文言も出ない。
  - Playwright で `display-mode` を再現できるかは未確認。できなければ、表示を判定する関数を切り出して単体で検証する。

### T5. 緊急停止と README

内容

- `tools/sw-killswitch.js`：`install` で `skipWaiting`、`activate` で全キャッシュ削除・`registration.unregister()`・開いているページの再読み込み。
- README に追記する内容：
  - オンライン前提であること、SW が画面遷移しか扱わない理由
  - 緊急停止の手順（`tools/sw-killswitch.js` を `sw.js` として配信する）
  - アイコンの生成手順
  - テストの実行方法（`tools/serve.py` と `npm test`）

ゴール

- **G5-1** v1 を入れた状態で、サーバーが緊急停止版を `sw.js` として返すようにしてリロードすると、`navigator.serviceWorker.getRegistrations()` が 0 件、かつ `caches.keys()` が 0 件になる。
- **G5-2** 緊急停止の後も G0-1 と G0-2 が通る。

### T6. 公開と実機確認（手動・利用者が実施）

公開の影響

- main への push で、GitHub Pages の公開サイトに反映される。
- 公開した時点から SW が利用者の端末に残る。T5 が完了してから公開する。

確認項目

- **G6-1**（自動）本番 URL に対して G1-1 と G1-2 を実行し、通る。
- **G6-1b**（自動）本番 URL で `manifest.webmanifest`、`sw.js`、`offline.html`、manifest に書いたアイコンが 200、`plans/pwa.md` と `tools/serve.py` が 404 を返す。
- **G6-2**（手動）Android Chrome で自動インストール案内（ミニインフォバー）またはインストールボタンが出て、インストールできる。
- **G6-3**（手動）iOS Safari で手順の文言が出る。ホーム画面に追加したときのアイコンと名前が正しい。
- **G6-4**（手動）iPad 幅でスタンドアロン表示にしたとき、上部の UI がステータスバーと重ならない。重なる場合は、768px 以上のレイアウトにも `env(safe-area-inset-top)` を足す追加タスクを起こす。
- **G6-5**（手動）スタンドアロン表示で現在地ボタンが動き、位置情報の許可を求められる。

## 5. 依存関係

```
T0 ─┬─ T1 ── T3 ── T4 ── T5 ── T6
    └─ T2 ─────────────────────┘
```

T2 は T0 の後ならいつでも着手できる。T6 は他のすべてが終わってから行う。

## 6. 未確認事項・リスク

| 項目 | 状態 | 対応 |
| --- | --- | --- |
| 自動案内に fetch handler が要るという条件 | 2023-12 時点の記述。それ以降の変更は未確認 | 条件が撤廃されていても、画面遷移を扱う SW は害が小さいので方針は変えない |
| 起動フラグ `--bypass-app-banner-engagement-checks` | 未確認 | T0 で確認。効かなければ G4-1 を格下げ |
| Playwright での `display-mode` の再現 | 未確認 | G4-4 で代替手段を用意 |
| iOS / iPadOS の挙動 | 自動化できない | T6 の手動確認 |
| 地理院タイルの規約上のキャッシュ可否 | 規約ページから判断できなかった | SW では扱わない方針で回避 |
| SW が端末に残ること | 構造上のリスク | T5 の緊急停止を公開前に用意 |
| 新しいサイト用ファイルの公開漏れ | Pages は `.github/workflows/pages.yml` の allowlist だけを公開する | T1・T3 で allowlist に追加し、G6-1b で確認する |
| リポジトリ自体は公開 | `plans/` は Pages には出ないが github.com では見える | 設計書に秘密情報は含めない |

## 7. 実施記録（2026-10-07）

### 計画からの変更

| 項目 | 変更 | 理由 |
| --- | --- | --- |
| G0-1 の判定ソース | `city-0` → `city-1` | 地点 34.490°N は `city-1` の範囲。アプリ内ブラウザで `city-0` 0 件、`city-1` 2058 件を確認 |
| G0-2 の判定 | 「移動します」の表示とマーカー 1 個 | 完全一致は結果一覧を出さずに移動する実装のため |
| SW の古いキャッシュ削除・緊急停止のキャッシュ削除 | `fukuyama-chiban-` で始まるキャッシュだけを消す | `<user>.github.io` のオリジンは同じユーザーの他のサイトと共有のため |
| テストのブラウザコンテキスト | 毎回、使い捨ての通常プロファイル（`launchPersistentContext`）で起動 | Chrome はシークレット扱いのコンテキストをインストール不可と判定し、`beforeinstallprompt` も出さない |
| アイコンの生成 | `icons/*.svg` から `tools/make_icons.sh`（`rsvg-convert`）で生成 | 追加の依存なしで再現できる |
| G4-4 | 3 本に分割：`navigator.standalone`（G4-4a）、CDP の `display-mode` 疑似（G4-4b、非対応なら skip）、判定関数 `installMode()` の表（G4-4c） | `display-mode` を再現できるかが未確認のため |
| G4-1 | 実イベント版（G4-1）と疑似イベント版（G4-1b）の両方を置く | フラグが効くかを T0 で確認できなかったため（下記） |
| 版番号 | `APP.version` と `sw.js` の `VERSION` を 1.1.0 に上げた | PWA 対応のリリースとして |
| manifest の `id` | `"./"` → 書かない | 仕様では `id` は `start_url` の**オリジン**を基準に解決し、省略時は `start_url` になる（[W3C Web App Manifest](https://w3c.github.io/manifest/) の「process the `id` member」）。`"./"` は本番で `https://atsuki-seo.github.io/` になり、同じオリジンの他サイトの PWA と ID が重なりうる。ローカル（オリジン直下）では一致してしまうため、初回公開後の `npm run test:prod` の G1-2 で判明した |

### 検証状況

テスト一式は `tools/pwa-test`（26 件）。2026-10-07 に利用者の端末で `npm test` を実行した結果：22 件合格、2 件失敗、2 件 skip。

| ゴール | 状況 |
| --- | --- |
| G0-1〜G0-3、G1-1〜G1-5、G2-1、G3-1〜G3-8、G4-1、G4-2、G4-4a、G4-4c、G5-1・G5-2 | 合格 |
| G4-1b、G4-3 | 初回は失敗 → テストを修正（下記）。再実行で合格（`t4-install.spec.js`：6 件合格、G4-4b は skip） |
| G4-4b | skip：この Chromium は CDP で `display-mode` を疑似できない。G4-4a と G4-4c で代替 |
| G6-1b | skip：ローカル実行では対象外（`npm run test:prod` で実行） |
| G6-* | 未実施（公開は利用者が行う） |

G4-1b・G4-3 の失敗の原因：Chromium 153（Chrome for Testing、headless）は、起動フラグがなくても、また iPhone の UA でも、本物の `beforeinstallprompt` を出した。そのため疑似イベントを送る前からボタンが表示され、iPhone の設定でも判定が `button` になった（実機の iPhone はこのイベントを出さない）。アプリの判定は正しく、テストの前提が誤っていた。修正：疑似イベントを使うテストでは、`isTrusted` の `beforeinstallprompt` をページより先に止める（`blockRealInstallPrompt`）。

Claude Code の Bash サンドボックスでは Chromium が起動しない（macOS の Mach ポート登録が禁止され `bootstrap_check_in ... Permission denied`）。ブラウザを使うテストは利用者の端末で実行する。

### 確定した事項

- 起動フラグ `--bypass-app-banner-engagement-checks`：この Chromium ではフラグがなくても `beforeinstallprompt` が出るので、G4-1 は格下げせず実イベントで判定できる。フラグが効いているかどうかは判別できない。
- `context.setOffline(true)` は SW の画面遷移にも効き、G3-4 で `offline.html` が出た。
- 本番 URL は `https://atsuki-seo.github.io/fukuyama-chiban/`（2026-10-07 にトップが 200、`plans/pwa.md`・`tools/serve.py` が 404 であることを確認）。
