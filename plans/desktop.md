# オフライン デスクトップ版 設計書

福山市 地番マップを、ネットワークなしで動く macOS 向けデスクトップアプリ（Electron）にする。
本書はタスク分割と、各タスクの機械的に検証可能なゴールを定義する。

## 1. 方針

| 項目 | 決定 | 理由 |
| --- | --- | --- |
| 利用範囲 | **利用者本人の検証用のみ**。他者には配布しない | 地理院タイルを同梱するため（§2「規約」）。配布する場合は本書の前提が変わる |
| 形態 | Electron。`.app` にデータをすべて同梱し、フォルダごとコピーすれば別の場所・別の Mac でも動く | 利用者の要望 |
| 対象 OS | macOS（Apple Silicon） | 利用者の環境。Windows 版は対象外 |
| ページ本体 | **`index.html` を変更せずにそのまま読み込む** | Web 版と二重管理にしない。外部 URL の差し替えはすべて Electron 側で行う |
| 外部 URL の扱い | Electron の `protocol.handle('https')` で横取りし、ローカルのファイルから返す（§3 の表）。表にないものは**すべて拒否**する | ネットワークの有無で挙動が変わらないようにし、オフラインで検証できることを保証する |
| ページの配信元 | 独自スキーム `app://fukuyama-chiban/`（standard・secure・fetch 対応として登録） | `BASE` が `location.href` から求まるので、相対パスの読み込み（PMTiles、検索 JSON、フォント）がそのまま動く |
| 範囲 | **福山市域に限定**。z10〜15 は `APP.bounds` の矩形、z16 以上は市域ポリゴン（`fukuyama_mask.geojson` の穴）に 1 タイル分の余白を足した範囲 | `APP.minZoom` が 10、`maxBounds` が `APP.bounds` なので、それより外は表示されない。z16 以上は矩形にすると約 3 倍に増える（§2） |
| 背景 | シームレス空中写真・淡色地図・標準地図の 3 種、**z18 まで** | Web 版と同じ見え方にする（利用者の選択） |
| 道路 | 地理院の最適化ベクトルタイル（全国 1 ファイル 16.9 GB）から、市域の z10〜16 だけを切り出す | 全国版は大きすぎる。道路レイヤーが使うのは z11 以上（`RdCL`）と z16 以上（`RdEdg`）で、元データの最大ズームは 16 |
| 背景タイルの保存形式 | 種類ごとに **raster PMTiles 1 ファイル** | 約 5 万個の小さいファイルを `.app` に入れるとコピーが遅く壊れやすい。読み込みには Web 版と同じ `pmtiles` ライブラリを使える |
| 取得の作法 | 取得の速さに上限を設ける（既定かつ上限 8 件/秒）。再開できるようにする。403・429 を受けたら即座に止める。User-Agent で用途を名乗る | [地理院地図の利用規約](https://maps.gsi.go.jp/help/termsofuse.html)に、過剰な負荷を与える通信は遮断することがあるとある |
| ライブラリ | `maplibre-gl@5.24.0` と `pmtiles@4.5.0` を npm から入れ、`index.html` の unpkg URL への要求にそのファイルを返す | npm と unpkg のファイルは同じで、`index.html` の SRI ハッシュがそのまま一致する（§2） |
| 取得したデータの置き場所 | `work/offline/`（`.gitignore` 済み）。**コミットも公開もしない** | リポジトリは公開されている。地理院タイルの再配布にあたる |
| 置き場所（コード） | リポジトリ直下に `desktop/` を作る | Pages の公開対象は `.github/workflows/pages.yml` の allowlist だけなので、`desktop/` は公開されない |
| 検証の層 | **Electron に依存しない部分（振り分け・Range・許可リスト・版の照合）を `desktop/routes.js` などに分け、Node だけで単体テストする**。Electron を起動する検証は smoke に集約する | Claude Code のサンドボックスでは Electron が起動しない（§2）。起動しない環境でも大半のゴールを判定できるようにする |
| smoke の置き場所 | `smoke.js` を `.app` にも同梱し、`--smoke` 引数で起動したときだけ読み込む | 開発時（`npm run smoke`）とパッケージ後（`.app` を直接起動）で同じ検証を使える。本人用なので、同梱しても害はない |

### 対象外

- Windows・Linux 版、自動更新、コード署名・公証（Developer ID）
- 他者への配布（必要になったら、地理院への申請要否の確認から別案件として扱う）
- 市域外の背景、z19 以上の背景（z18 のタイルを拡大表示する。Web 版と同じ）
- Web 版（`index.html`）の変更。デスクトップ版でだけ出る差異は §3「Web 版との差異」で受け入れる
- CI 化（GitHub Actions で Electron を動かすこと）

## 2. 前提となる事実

### 規約

| 事実 | 根拠 |
| --- | --- |
| 地理院タイルは、出典を明示すれば申請なしで使える場合がある。出典は「国土地理院」などと書き、タイル一覧ページへのリンクを付ける | [地理院タイル一覧](https://maps.gsi.go.jp/development/ichiran.html) |
| タイルのダウンロード、オフラインでの保存、アプリへの同梱を直接扱った記述は見つからなかった | 同上、[国土地理院コンテンツ利用規約](https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html)、[地理院地図 利用規約](https://maps.gsi.go.jp/help/termsofuse.html) |
| 内部利用は申請不要。測量成果を複製して単に背景として使う場合は複製申請の対象。写真などの「基本測量成果以外の地理院タイル」は申請の対象外 | [測量成果の複製・使用の申請要否](https://www.gsi.go.jp/LAW/2930-index.html) |
| 編集・加工して使う場合は、出典に加えて、編集・加工したことの記載が必要 | 国土地理院コンテンツ利用規約 |
| 最適化ベクトルタイルは試験公開。URL・データ構成・内容が変わる可能性がある。出典の例は「国土地理院最適化ベクトルタイル」 | [gsi-cyberjapan/optimal_bvmap](https://github.com/gsi-cyberjapan/optimal_bvmap) |

上の事実からの推論：**本人の検証用は「内部利用」にあたり、申請は不要**と考えられる。標準地図・淡色地図は基本測量成果にあたる可能性があり、他者に配る場合は複製申請が必要かどうか地理院に確認する。この推論は地理院に確認したものではない。

### 技術・データ量（2026-10-07 に実測）

| 事実 | 根拠 |
| --- | --- |
| 最適化ベクトルタイルの PMTiles は 16,900,763,181 バイト。Range に対応。v3、z4〜16、MVT、gzip 圧縮、clustered | `HEAD` と、ヘッダー 127 バイトを Range で取得 |
| 取得する枚数：背景は 1 種類あたり 51,815 枚（z10:6、z11:15、z12:40、z13:135、z14:476、z15:1,728、z16:2,778、z17:9,853、z18:36,784）。道路は 5,178 枚（z10〜16）。合計 160,623 リクエスト | 試作した `tools/offline_tiles.py plan` |
| 参考：z16 以上も矩形で取った場合、z14〜18 だけで約 14.2 万枚 | 同様の計算 |
| 福山駅周辺の約 800 m 四方（`--sample`）の枚数は、背景が 1 種類あたり 93 枚、道路が 17 枚 | 試作で取得した結果（「1 種類あたり」は、3 種の背景が同じタイル集合を使う実装からの読み取り） |
| 上の取得での 1 枚あたりの平均：写真 22 KB、淡色地図 17.5 KB、標準地図 22.7 KB、道路 21 KB | 同上 |
| 上の平均を全体に掛けた推定：写真 約 1.1 GB、淡色地図 約 0.9 GB、標準地図 約 1.2 GB、道路 約 0.1 GB、**合計 約 3.3 GB**。市街地の平均なので、郊外・海が多い分だけ実際は小さくなる見込み | 推論（ソースは前行のサンプル） |
| 取得時間の目安：8 件/秒で約 5.6 時間 | 160,623 ÷ 8 |
| npm の `maplibre-gl@5.24.0`（css・js）と `pmtiles@4.5.0`（`dist/pmtiles.js`）の sha384 は、`index.html` の `integrity` と一致する | 試作で `openssl dgst -sha384` により確認 |
| Electron の最新版は 44.6.0（2026-10-07 時点の npm） | 試作で `npm install` |
| `maplibre-gl@5.24.0` に critical の advisory がある（GHSA-jrc7-96c5-q579、`DOM.sanitize()` の XSS。修正版なし）。Web 版も同じ版を使っている | `npm audit` |
| Claude Code の Bash サンドボックスでは Chromium が起動しない。Electron の起動も試作では終わらなかった | `plans/pwa.md` §7、試作 |
| 地番 PMTiles・検索索引・マスク・フォントはすでにリポジトリ内にある（約 176 MB） | README「Files」 |
| この端末の Node は v25.5.0（`Request`・`Response`・`node --test` が標準で使える） | `node -v` |
| リポジトリのあるボリュームの空きは約 1,369 GB | `df -g .`（2026-10-07） |
| `index.html` は `sw.js` を `load` の後に登録し、失敗は `console.warn` に出す（`console.error` ではない） | `index.html` の `registerServiceWorker()` |
| `index.html` の `<head>` に `<link rel="preconnect" href="https://cyberjapandata.gsi.go.jp">` がある | `index.html` 14 行目 |
| 地番クリック時の情報は、デスクトップ幅では `.maplibregl-popup` の中に `<dt>地番</dt>`・`<dt>所在</dt>`・`<dt>国道・県道</dt>` として出る。道路を表示していないとき、国道・県道の行は「オンにすると表示します」という文言になる | `index.html` の `infoNode()`・`roadRow()` |

## 3. 全体構成

```
tools/offline_tiles.py              地理院タイルの取得・PMTiles 化・検証（plan / fetch / pack / verify / check-missing）
tools/tests/test_offline_tiles.py   上の単体テスト（ネットワーク不要。unittest）
tools/tests/make_fixture.py         desktop の単体テスト用に、合成データ（地理院のデータではない）の小さい PMTiles を作る
work/offline/                       取得結果（.gitignore 済み、コミットしない）
  {photo,pale,std,road}.sqlite        取得途中の保存先。再開に使う
  {photo,pale,std,road}.pmtiles       アプリに同梱するファイル
desktop/
  package.json           依存（すべて版を固定）、scripts、electron-builder の設定
  main.js                Electron 側：スキーム登録、ウィンドウ、リンク・画面遷移・権限の扱い、--smoke の切り替え
  routes.js              振り分け（Electron に依存しない。Request を受けて Response を返す）
  smoke.js               --smoke で読み込む検証。結果を smoke-out/result.json に書いて終了する
  check-versions.mjs     index.html の unpkg URL・SRI と node_modules の照合
  verify-dist.mjs        パッケージ後の .app の中身・署名の検証
  test/                  node --test の単体テストと、make_fixture.py が作るフィクスチャ
  dist/                  ビルド結果（.gitignore に追加する）
  smoke-out/             smoke の出力（.gitignore に追加する）
```

### `desktop/package.json` の scripts

| script | 内容 | 実行場所（§4 の記号） |
| --- | --- | --- |
| `start` | `electron .` | U |
| `test` | `node --test test/` | S |
| `check-versions` | `node check-versions.mjs` | S |
| `smoke` | `electron . --smoke` | U |
| `smoke:offline` | `electron . --smoke --host-resolver-rules="MAP * ~NOTFOUND"`（名前解決をすべて失敗させる） | U |
| `dist` | `electron-builder --mac dir --arm64` | U（サンドボックスで動くかは未確認） |
| `verify-dist` | `node verify-dist.mjs` | S |

### リクエストの振り分け（`routes.js`）

| ページからの要求 | 応答 |
| --- | --- |
| `app://fukuyama-chiban/<path>` | サイトのファイル。許可リスト `SITE_FILES`（`index.html`、`*.pmtiles`、`search.json`、`search/<n>.json`、`fukuyama_mask.geojson`、`fonts/<stack>/<a>-<b>.pbf`、`icons/<file>`、`manifest.webmanifest`）に一致するものだけを返す。`/` は `index.html`。それ以外は 404。Range に 206 で応答する |
| `https://unpkg.com/{maplibre-gl,pmtiles}@<版>/dist/<file>` | `node_modules` の同じファイル。`<版>` は `node_modules` の `package.json` から求める。版が違う要求は「その他」と同じく拒否する |
| `https://cyberjapandata.gsi.go.jp/xyz/{seamlessphoto,pale,std}/{z}/{x}/{y}.{jpg,png}` | `offline/{photo,pale,std}.pmtiles` から 1 枚取り出す。範囲外なら 404 |
| `https://cyberjapandata.gsi.go.jp/xyz/optimal_bvmap-v1/optimal_bvmap-v1.pmtiles` | `offline/road.pmtiles` を Range つきで返す。ページの PMTiles ライブラリはヘッダーから読み直すので、全国版と同じ URL のまま市域版を読ませられる |
| `OPTIONS`（https 全般） | 204 と CORS ヘッダー |
| その他の http(s) | 503（拒否）。ホストを `refusedHosts()` に記録し、ログにはホストごとに 1 回だけ出す |

https で返す応答には `Access-Control-Allow-Origin: *`、`Access-Control-Allow-Headers: Range, If-Match`、`Access-Control-Expose-Headers: ETag, Content-Range, Content-Length, Accept-Ranges` を付ける。ページの origin は `app://` で、unpkg のファイルは `crossorigin="anonymous"` と SRI 付きで読み込まれるため。

`routes.js` の公開インターフェース：

```js
export const SITE_FILES;                       // 許可リスト（正規表現の配列）。verify-dist.mjs も使う
export function createRouter({ siteDir, offlineDir, vendors, log });
//   -> { handleApp(request), handleRemote(request), refusedHosts() }
//   vendors: [[urlPrefix, dir], ...]（main.js が node_modules から作る）
export function navigationPolicy(url);         // 'internal' | 'external' | 'deny'
export function permissionPolicy(permission);  // true | false
```

### Electron 側の扱い（`main.js`）

| 項目 | 挙動 |
| --- | --- |
| `webPreferences` | `contextIsolation: true`、`sandbox: true`、`nodeIntegration: false`、preload なし |
| 新しいウィンドウ（`target="_blank"`） | `setWindowOpenHandler` で常に拒否し、`navigationPolicy(url) === 'external'` なら既定のブラウザで開く |
| 画面遷移（`will-navigate`） | `internal`（`app://fukuyama-chiban/`）だけ許可。`external` は既定のブラウザで開き、`deny`（`file:`・`javascript:` など）は何もしない |
| 権限（`setPermissionRequestHandler`） | `permissionPolicy` が true のもの（位置情報と、共有ボタンが使うクリップボードへの書き込み）だけ許可。Electron での権限名は実装時に確認する（§6） |
| 読み込み先 | 開発時：`site` = リポジトリ直下、`offline` = `work/offline/`。パッケージ後：`process.resourcesPath` の `site/`・`offline/` |
| `--smoke[=<out-dir>]` | `smoke.js` を読み込み、検証後に終了する。既定の出力先は開発時が `desktop/smoke-out/`、パッケージ後が `$TMPDIR/fukuyama-chiban-smoke/` |

### smoke の手順と `result.json`

手順（順序に意味がある。コンソールのエラーは手順 3 までを数える）：

1. 地図の `load` を待つ。
2. 3 つの表示で背景・地番・道路を確認する（福山駅周辺、`--sample` の範囲内）。
   - 写真 z17（道路あり）、淡色 z18（道路なし）、標準 z16（道路あり）。各表示で `idle` を待ち、スクリーンショットを保存する。
3. 地番のクリック：z17・写真・道路ありで、市の地番ポリゴンがある画面上の点を探し、`sendInputEvent` でクリックする。ポップアップの中身を読む。
4. この時点のコンソールのエラー数と、拒否したホストの一覧を記録する。
5. 検索：「青葉台一丁目 4-1」を入力して送信し、`#search-status` とマーカーの数を読む。
6. 直接の要求：`search.json`、`search/<最初の町>.json`、`https://example.com/`、範囲外の地理院タイル（`std/18/1/1.png`）を `fetch` する。
7. `--full` のときだけ：市域ポリゴンの中から固定の乱数種で 10 点を選び、各点で背景 3 種の z18 を表示して、エラーになったタイルの z/x/y を記録する。
8. `result.json` を書き、合否を最終行に `SMOKE OK` / `SMOKE FAILED` と出して、終了コード 0 / 1 で終わる。全体が 180 秒を超えたら `SMOKE TIMEOUT` を出して終了コード 2 で終わる（試作では smoke が終わらなかったため、必ず終わるようにする）。

`result.json` の形：

```json
{
  "ok": true,
  "paths": { "resources": "...", "site": "...", "offline": "..." },
  "views": {
    "photo-z17": { "bgLoaded": 12, "bgErrored": 0, "lots": 340, "roads": 25 },
    "pale-z18":  { "bgLoaded": 9,  "bgErrored": 0, "lots": 120, "roads": null },
    "std-z16":   { "bgLoaded": 6,  "bgErrored": 0, "lots": 900, "roads": 40 }
  },
  "click": { "popup": true, "chiban": "123-4", "shozai": "福山市…", "roadRow": "…" },
  "consoleErrors": [],
  "refusedByPage": [],
  "search": { "status": "青葉台一丁目 4-1 に移動します。", "markers": 1 },
  "probes": { "search": 200, "town": 200, "external": 503, "gsiOutside": 404 },
  "full": { "points": 10, "erroredTiles": [] },
  "failures": []
}
```

`failures` には、合否の判定に落ちた項目名を入れる（例：`"views.pale-z18.bgErrored"`）。数値は例。

### パッケージの中身（electron-builder、`--mac dir --arm64`）

```
desktop/dist/mac-arm64/福山市 地番マップ.app/Contents/
  MacOS/福山市 地番マップ
  Resources/
    app.asar        package.json、main.js、routes.js、smoke.js、node_modules（maplibre-gl・pmtiles のみ）
    site/           リポジトリ直下のうち SITE_FILES に一致するファイル
    offline/        {photo,pale,std,road}.pmtiles
```

- `site/` に入れるファイルの集合は、`verify-dist.mjs` が `SITE_FILES` をリポジトリに当てはめて求めた集合と一致させる（許可リストの二重管理による食い違いを検出するため）。
- `sw.js`・`offline.html` は入れない。`index.html` の SW 登録は 404 で失敗し、`console.warn` が 1 件出る。

### Web 版との差異（受け入れる）

| 項目 | デスクトップ版での挙動 |
| --- | --- |
| Service Worker | `app://` では登録できず、コンソールに警告が 1 件出る。機能への影響はない |
| インストールボタン | `beforeinstallprompt` が来ないので出ない |
| 共有ボタン | URL が `app://fukuyama-chiban/#map=...` になり、他の人には使えない。`navigator.share` が使えない場合はクリップボードへのコピーになる |
| 現在地 | オフラインで位置を取れるかは未確認（§6） |
| 背景の鮮度 | 取得した日の時点で固定。取得日は PMTiles の metadata の `fetched` に残す |
| 取得範囲の外 | 背景は 404 になり、MapLibre がコンソールにエラーを出しうる。範囲外は `maxBounds` で表示されないので、市域の縁と、z16 以上で市域から 1 タイルより外を見たときに限られる |

## 4. タスクと検証可能なゴール

### ゴールの書き方

- 各ゴールに、**判定**（実行するコマンド）と**合格条件**（終了コード・出力・ファイルの中身）を書く。例外は「手動」と明記したものだけ。
- 実行場所の記号：
  - **S**：Claude Code のサンドボックス内で実行できる（ネットワーク不要）
  - **N**：地理院（`cyberjapandata.gsi.go.jp`）への通信が要る。サンドボックスで実行するなら、そのホストへの通信を許可したうえで行う
  - **U**：Electron を起動するので、利用者の端末で実行する
  - **M**：手動。利用者が目で確認する
- コマンドはリポジトリ直下から実行する前提で書く。`desktop/` の npm scripts は `npm --prefix desktop run <script>` の形で書く。

### T0. タイル取得ツール

内容

- `tools/offline_tiles.py` を作る。サブコマンド：

  | サブコマンド | 振る舞い | 終了コード |
  | --- | --- | --- |
  | `plan [layers] [--sample] [--json]` | 層ごとの対象枚数（ズーム別）、取得済み、404 の件数を表示する。`--json` では `{"photo": {"total": 51815, "done": 0, "missing": 0, "per_zoom": {"10": 6, ...}}, ...}` を出す。`done` は 404 を含む | 0 |
  | `fetch [layers] [--sample] [--rate R] [--workers W]` | `work/offline/<layer>.sqlite` に保存する。取得済みと 404 の記録は飛ばす。層ごとに最初に `<layer>: N tiles to fetch` を出す。`R` の既定と上限は 8（超えたら引数エラー）。`W` の既定は 4 | 0：完了、3：403・429 で停止、130：中断、1：その他 |
  | `pack [layers] [--strict]` | タイル ID の順に並べて PMTiles を書く（`.tmp` に書いてから置き換える）。取得済みが対象に満たないと `warning: only N of M tiles fetched` を出す。`--strict` ではそのとき書かずに失敗する | 0、4：`--strict` で不足 |
  | `verify [layers] [--sample] [--remote N]` | §4 G0-7 の項目を確かめ、層ごとに `OK <layer>` か `FAIL <layer>: <理由>` を出す。`--remote N` は道路のタイルを N 枚選び、全国版の同じ z/x/y とバイト単位で比べる | 0：すべて OK、1：1 つでも FAIL |
  | `check-missing <result.json>` | smoke の `full.erroredTiles` のすべてが、sqlite の `missing`（地理院が 404 を返したもの）に記録されているかを確かめる | 0：すべて記録あり、1：記録なしがある |

- `pack` の metadata：`name`、`attribution`（`国土地理院`）、`source`（取得元 URL の型）、`fetched`（取得日）、`note`（「個人利用、再配布しない」）。道路は元の metadata（`vector_layers` など）と圧縮方式（gzip）を引き継ぐ。ヘッダーの範囲は `BOUNDS`、ズームは `MIN_ZOOM`〜層の最大ズーム。
- HTTP の扱い：User-Agent に `fukuyama-chiban-offline/1 (personal offline copy)` を付ける。404 は missing として記録、403・429 は即座に停止、5xx・接続エラー・`IncompleteRead` は待ち時間を伸ばしながら 5 回まで再試行。HTTP 部分と時計は差し替えられる形にし、単体テストから偽の応答を注入できるようにする。
- 依存として `pmtiles`（Python）を `tools/requirements.txt` に加える。
- 範囲の定数（`BOUNDS`、`MIN_ZOOM`）は `index.html` の `APP.bounds`・`APP.minZoom` と同じ値にし、コメントで対応を示す（一致は G0-2 で機械的に確かめる）。
- `tools/tests/make_fixture.py`：合成のタイル（1×1 の PNG、小さい MVT）で `desktop/test/fixtures/{photo,pale,std,road}.pmtiles` を作る。地理院のデータは含めないので、コミットしてよい。

ゴール

| ID | 判定 | 合格条件 | 場所 |
| --- | --- | --- | --- |
| G0-1 | `python3 tools/offline_tiles.py plan --json` | `photo`・`pale`・`std` の `total` が 51,815、`road` が 5,178。`per_zoom` が §2 の表と一致する | S |
| G0-2 | `python3 -m unittest tools.tests.test_offline_tiles`（定数のテスト） | `index.html` から読み取った `APP.bounds`・`APP.minZoom` が `BOUNDS`・`MIN_ZOOM` と一致する | S |
| G0-3 | 同上（範囲のテスト） | 市域ポリゴンの中から固定の乱数種で選んだ 1,000 点について、z16〜18 の各ズームで、その点を含むタイルが対象集合に入っている。`APP.bounds` の四隅を含むタイルが z10〜15 の対象集合に入っている | S |
| G0-4 | 同上（HTTP のテスト、偽の応答を注入） | 403・429：`Stop` で止まり、その後に要求を出さない。5xx・`URLError`・`IncompleteRead`：再試行して成功する。404：`missing` に記録される。要求に User-Agent が付いている | S |
| G0-5 | 同上（速さのテスト、偽の時計） | `rate=8` で 41 件の要求を出すと、偽の時計の経過が 5 秒以上。`fetch --rate 9` は終了コード 2（引数エラー） | S |
| G0-6 | 同上（PMTiles 化のテスト、合成データ） | 合成の sqlite から `pack` した PMTiles を `pmtiles` の Reader で読むと、全タイルが元のバイト列と一致し、ヘッダーの `tile_type` と metadata のキーが仕様どおり。不足がある sqlite に `pack --strict` を実行すると終了コード 4 で、PMTiles を書かない | S |
| G0-7 | `fetch --sample` → `pack` → `verify --sample` | `fetch` が終了コード 0。`verify` が終了コード 0 で `OK` を 4 行出す。`verify` の確認項目：ヘッダーの `tile_type` が写真 JPEG・地図 2 種 PNG・道路 MVT、`tile_compression` が道路 gzip・それ以外 none、`min_zoom` 10、`max_zoom` 18（道路 16）、範囲が `BOUNDS`、タイル数が sqlite の `tiles` の件数と一致、全タイルが sqlite とバイト単位で一致、道路の `vector_layers` に `RdCL` と `RdEdg` がある | N |
| G0-8 | `plan --sample --json`（G0-7 の後） | 背景 3 種の `total` が 93、道路が 17、4 層とも `done == total`。値が違えば原因を調べ、§2 を直す | S |
| G0-9 | `fetch --sample` をもう一度 | 4 層とも `0 tiles to fetch` と出て、終了コード 0（再開できる） | S（要求を出さないので通信は不要） |
| G0-10 | `verify road --sample --remote 5` | 終了コード 0（切り出した道路タイルが全国版とバイト単位で一致する） | N |
| G0-11 | `python3 tools/tests/make_fixture.py` | `desktop/test/fixtures/` に 4 つの PMTiles ができ、合計 100 KB 未満 | S |

### T1. 全量取得（利用者の確認後に実施）

実行前に利用者に示すこと

- 対象：地理院のサーバー（`cyberjapandata.gsi.go.jp`）
- 影響：約 16 万リクエスト。8 件/秒で約 5.6 時間。403・429 を受けたら止まる
- 実行内容：`python3 tools/offline_tiles.py fetch`（全層）、`pack --strict`、`verify`
- 容量：`work/` に PMTiles と sqlite をあわせて約 7 GB（推定）。空きは 10 GB 以上あること（2026-10-07 時点で約 1,369 GB あり）

止まった場合は、時間を空けてから `--rate` を下げて同じコマンドを実行する（取得済みは飛ばされる）。

ゴール

| ID | 判定 | 合格条件 | 場所 |
| --- | --- | --- | --- |
| G1-1 | `plan --json` | 4 層とも `done == total` | S |
| G1-2 | `pack --strict` | 終了コード 0（`only N of M tiles fetched` の警告が出ない） | S |
| G1-3 | `verify` | 終了コード 0（全タイルの照合を含む） | S |
| G1-4 | `verify road --remote 20` | 終了コード 0 | N |
| G1-5 | §7 の表 | 層ごとの 404 の件数（`plan --json` の `missing`）、PMTiles のサイズ、取得日が記録されている | 記録 |

### T2. Electron シェル

内容

- `desktop/package.json`：`"type": "module"`。`maplibre-gl`・`pmtiles` は `index.html` と同じ版に、`electron`・`electron-builder` も含めて**すべて `^` なしの版で固定**する。`package-lock.json` をコミットする。
- `desktop/routes.js`・`main.js`・`smoke.js`（§3 のとおり）。
- `desktop/check-versions.mjs`：`index.html` の unpkg URL（パッケージ名・版・ファイル）と `integrity` を読み、次をすべて確かめる。
  - `desktop/package.json` の版、`package-lock.json` で解決された版、`node_modules/<name>/package.json` の版が URL の版と一致する
  - `node_modules/<name>/dist/<file>` の sha384 が `integrity` と一致する
- `desktop/test/`：`routes.js` と `check-versions.mjs` の単体テスト。フィクスチャは T0 の `make_fixture.py` で作ったもの。
- `.gitignore` に `desktop/dist/`、`desktop/smoke-out/` を足す（`node_modules/` は既にある）。

ゴール（単体テスト。`npm --prefix desktop test` で判定し、終了コード 0 で合格）

| ID | テストの内容 | 場所 |
| --- | --- | --- |
| G2-1 | 許可リスト：`/` と `index.html` は 200。`work/offline/photo.pmtiles`、`.git/config`、`tools/serve.py`、`plans/desktop.md`、`sw.js`、`../etc/passwd`、`%2e%2e/README.md` は 404 | S |
| G2-2 | Range：`bytes=0-15` は 206・16 バイト・`Content-Range: bytes 0-15/<size>`。`bytes=-16` は末尾 16 バイト。範囲外は 416。Range なしは 200 で全体 | S |
| G2-3 | unpkg：`maplibre-gl@5.24.0/dist/maplibre-gl.js` は 200 で CORS ヘッダー付き、中身が `node_modules` のファイルと同じ。版違い（`@5.23.0`）は 503。`dist/../package.json` は 404 | S |
| G2-4 | 地理院：フィクスチャにある z/x/y の背景は 200 で `Content-Type` が層に合う（写真 `image/jpeg`、地図 `image/png`）。ない z/x/y は 404。道路 URL への Range は 206 で、フィクスチャの同じ範囲のバイト列 | S |
| G2-5 | 拒否：`https://example.com/` は 503 で、`refusedHosts()` に `example.com` が 1 件。同じホストに 2 回要求してもログは 1 行。`OPTIONS` は 204 で CORS ヘッダー付き | S |
| G2-6 | `navigationPolicy`：`app://fukuyama-chiban/index.html#map=1/2/3` は `internal`、`https://maps.gsi.go.jp/...` は `external`、`file:///etc/hosts`・`javascript:alert(1)`・`app://other/` は `deny` | S |
| G2-7 | `permissionPolicy`：位置情報とクリップボードへの書き込みだけ true。`media`・`notifications`・`midi` などは false | S |
| G2-8 | `check-versions`：一時ディレクトリにコピーした `index.html` の版か `integrity` を 1 文字変えると失敗する（照合が実際に効いている） | S |

ゴール（その他）

| ID | 判定 | 合格条件 | 場所 |
| --- | --- | --- | --- |
| G2-9 | `npm --prefix desktop run check-versions` | 終了コード 0。版が食い違うと unpkg の要求が拒否されてページが動かなくなるため | S |
| G2-10 | `git diff --exit-code -- index.html .github/workflows/pages.yml` と `grep -c desktop .github/workflows/pages.yml` | 前者は終了コード 0、後者は `0`（ページを変えていない。`desktop/` を公開していない） | S |
| G2-11 | `git check-ignore -q desktop/dist desktop/smoke-out desktop/node_modules work/offline` | 終了コード 0 | S |
| G2-12 | `npm --prefix desktop run smoke`（`work/offline/` は `--sample` のデータ） | 最終行が `SMOKE OK`、終了コード 0、180 秒以内に終わる。`result.json` が次をすべて満たす：`views` の 3 表示で `bgLoaded ≥ 1`・`bgErrored = 0`・`lots ≥ 1`、道路ありの表示で `roads ≥ 1`。`click.popup` が true、`chiban` が空でない、`shozai` が「福山市」で始まる、`roadRow` が「オンにすると表示します」を含まない。`consoleErrors` が空（SW 登録の失敗は `warn` なので含まれない）。`search.status` が「青葉台一丁目 4-1 に移動します」を含み、`markers` が 1。`probes` が `search` 200・`town` 200・`external` 503・`gsiOutside` 404。`paths.site` がリポジトリ直下、`paths.offline` が `work/offline` | U |
| G2-13 | `ls desktop/smoke-out/*.png` | 3 表示のスクリーンショットがあり、それぞれ 10 KB 以上（真っ白・真っ黒の画像でない目安） | S（G2-12 の後） |

G2-12 は §6 の「`protocol.handle('https')` が Web Worker からの要求も横取りするか」「`app://` での CORS と SRI」の確認を兼ねる。通らなければ T3 以降に進まず、方式を見直す（§6）。

### T3. オフライン保証

ゴール

| ID | 判定 | 合格条件 | 場所 |
| --- | --- | --- | --- |
| G3-1 | G2-12 の `result.json` | `refusedByPage` が空（ページは §3 の表にある外部 URL しか使わない。smoke 自身の `example.com` への要求は手順 6 なので含まれない） | U |
| G3-2 | `npm --prefix desktop run smoke:offline` | G2-12 と同じ条件で `SMOKE OK`（名前解決をすべて失敗させても動く）。`--host-resolver-rules` が Electron で効くかは未確認（§6）。効かない場合は G3-3 だけで判定し、その旨を §7 に記録する | U |
| G3-3 | 手動：Wi-Fi を切った状態で `npm --prefix desktop start` | 背景 3 種・道路・地番・検索・ラベルが表示される | M |

### T4. パッケージ化

内容

- `desktop/package.json` の `build`：
  - `appId`、`productName`（福山市 地番マップ）、`directories.output: dist`
  - `files`：`package.json`、`main.js`、`routes.js`、`smoke.js`（`test/`・`check-versions.mjs`・`verify-dist.mjs` は入れない）
  - `extraResources`：リポジトリ直下から `SITE_FILES` に当たるファイルを `site/` へ、`../work/offline/*.pmtiles` を `offline/` へ
  - `mac.target: dir`、`arch: arm64`、アイコン（`icons/icon-512.png`）
  - 署名：Developer ID ではしない。Apple Silicon で起動するのに要る ad-hoc 署名がされる設定にする（electron-builder の設定名は要確認。§6）
- `desktop/verify-dist.mjs`：G4-1〜G4-3 を判定し、項目ごとに `OK` / `FAIL` を出す。

ゴール

| ID | 判定 | 合格条件 | 場所 |
| --- | --- | --- | --- |
| G4-1 | `npm --prefix desktop run dist` → `npm --prefix desktop run verify-dist` | `.app` がある。`Resources/site/` のファイルの集合が、`SITE_FILES` をリポジトリに当てはめた集合と一致する（余分も不足もない）。`Resources/offline/` に 4 つの PMTiles があり、サイズが `work/offline/` と一致する | U（`dist`）、S（`verify-dist`） |
| G4-2 | 同上（`verify-dist` が `npx asar list` で確認） | `app.asar` に `main.js`・`routes.js`・`smoke.js`・`node_modules/maplibre-gl/dist/maplibre-gl.js`・`node_modules/pmtiles/dist/pmtiles.js` がある。`electron`・`electron-builder`・`test/` がない | S |
| G4-3 | 同上（`verify-dist` が `codesign`・`lipo` を実行） | `codesign --verify --deep --strict` が終了コード 0。`lipo -archs` が `arm64` | S（サンドボックスで `codesign` が動くかは未確認） |
| G4-4 | `.app` を `$TMPDIR/fukuyama-copy/` にコピーし、`"<コピー先>/福山市 地番マップ.app/Contents/MacOS/福山市 地番マップ" --smoke` | `SMOKE OK`。`result.json` の `paths.site`・`paths.offline` がコピー先の `Contents/Resources/` の下にある（リポジトリへのパスに依存していない） | U |
| G4-5 | T1 の後、G4-4 と同じ起動に `--full` を付ける → `python3 tools/offline_tiles.py check-missing <result.json>` | `SMOKE OK`、かつ `check-missing` が終了コード 0（市域内でエラーになった背景タイルは、地理院が 404 を返したものだけ） | U、S |
| G4-6 | `du -sh` | T1 の後の `.app` の合計サイズを §7 に記録する | 記録 |

### T5. README

内容

- 「Desktop app」の節を追加する：
  - 個人の検証用で再配布しないこと
  - 地理院の規約上の位置づけ（§2 の推論であること）
  - 取得手順（T0・T1）。地理院への負荷と、止まったときの再開方法
  - ビルド手順（T4）と検証手順（§5）
  - データの更新手順：地番データの年次更新（`site/` の作り直し）、背景の取り直し、ライブラリの版を上げるときは `desktop/package.json` もそろえて `check-versions` を通すこと
  - 別の Mac にコピーしたとき、Gatekeeper にブロックされた場合の対処（右クリック →「開く」など）。手順の実行は利用者自身が判断する前提で書く
- 「Files」の表に `desktop/` と `tools/offline_tiles.py` の行を足す。`tools/` の行に `tests/` を書き足す。

ゴール

| ID | 判定 | 合格条件 | 場所 |
| --- | --- | --- | --- |
| G5-1 | README の「Files」の表で、1 列目が `desktop/` の行と `tools/offline_tiles.py` の行を `grep` で探す | どちらも 1 行以上（`plans/` の行は既存） | S |
| G5-2 | `grep -n '^## Desktop app' README.md` と、その節の中の `offline_tiles.py fetch`・`npm --prefix desktop run dist`・`npm --prefix desktop run smoke` | 見出しが 1 つあり、3 つのコマンドがその節にある | S |
| G5-3 | README の節に書いた `npm --prefix desktop run <name>` の `<name>` を `desktop/package.json` の `scripts` と突き合わせる（一行のスクリプトで判定） | 書かれた script がすべて存在する（README の手順が古くならないように） | S |

### T6. 実機での確認（手動・利用者が実施）

| ID | 確認 | 自動化された部分 |
| --- | --- | --- |
| G6-1 | Wi-Fi を切った状態の `.app` で、地番をクリックして所在・地番が表示され、道路レイヤーを表示しているときは国道・県道との関係が表示される | G2-12 の `click` |
| G6-2 | 出典などのリンクが既定のブラウザで開き、アプリ内では開かない | G2-6（判定関数） |
| G6-3 | 現在地ボタンを押したときの挙動。オフラインで動かない場合はその旨を README に書く | なし |
| G6-4 | （別の Mac がある場合）`.app` をコピーして起動できる。Gatekeeper の表示と対処を README と照らし合わせる | G4-4（同じ Mac の別の場所） |

## 5. 依存関係と検証の実行順

```
T0（単体：G0-1〜G0-6、G0-11）
 ├─ T0（--sample：G0-7〜G0-10）── T2 ── T3 ── T4（G4-1〜G4-4）── T5
 └────────────── T1（全量：利用者の確認後）──────── T4（G4-5・G4-6）── T6
```

- T2〜T4 の G4-4 までは `--sample` のデータで進められる。T1 は時間がかかるので、T2 と並行して進めてよい。
- G4-5・G4-6・T6 は T1 の後に行う。

サンドボックス内でまとめて判定できるもの（S）：

```bash
python3 tools/offline_tiles.py plan --json
```

```bash
python3 -m unittest tools.tests.test_offline_tiles
```

```bash
npm --prefix desktop test
```

```bash
npm --prefix desktop run check-versions
```

利用者の端末で行うもの（U）：`npm --prefix desktop run smoke`、`smoke:offline`、`dist`、コピーした `.app` での `--smoke`。結果は `result.json` に残るので、合否の読み取りは Claude Code 側でもできる。

## 6. 未確認事項・リスク

| 項目 | 状態 | 対応 |
| --- | --- | --- |
| 地理院タイルの複製・同梱の扱い | 規約に直接の記述なし。本人の検証用は内部利用と推論 | 利用範囲を本人に限定する。配布するなら地理院に確認する |
| PMTiles への詰め替えが「編集・加工」にあたるか | 未確認。推論では、内容に手を加えないので加工にはあたらない | ページの出典表示（「国土地理院」）はそのまま。README にも書く |
| 一括取得が負荷とみなされるか | 基準は公開されていない | 8 件/秒を上限にし、403・429 で止める。止まったら時間を空けて、より遅くして再開 |
| 最適化ベクトルタイルの変更 | 試験公開 | 取得日を metadata に残す。取り直しで URL やレイヤー名が変わっていたら `index.html` 側も要確認。G0-7 の `vector_layers` の確認で検出できる |
| `protocol.handle('https')` が MapLibre の Web Worker からの要求も横取りするか | 未確認（試作の smoke が完了しなかった） | G2-12 で確認。だめなら、`index.html` の URL を差し替える方式に切り替える（その場合は G2-10 を見直す） |
| `app://` での CORS と SRI | 未確認 | 同上 |
| `<link rel="preconnect">` が `protocol.handle` を通らずに接続を試みるか | 未確認。推論では、接続の準備だけで内容の要求ではないため、オフラインでは失敗するだけで表示には影響しない | G3-2・G3-3 で表示に影響がないことを確かめる |
| `--host-resolver-rules` が Electron で効くか | 未確認（Chromium のフラグ名は記憶ベース） | G3-2 で確認。効かなければ G3-3 で判定する |
| 範囲外の 404 で MapLibre がコンソールにエラーを出すか | 未確認 | smoke は `--sample` の範囲の中だけでエラーを数える（§3 の手順）。`--full` の 404 は `check-missing` で地理院の 404 と突き合わせる |
| Electron の権限名（位置情報・クリップボード） | 未確認 | T2 の実装時に Electron のドキュメントで確認し、G2-7 の期待値を合わせる |
| Electron の位置情報がオフラインで動くか | 未確認 | T6 の G6-3 |
| Apple Silicon で ad-hoc 署名のビルドが起動するか、electron-builder の設定名 | 未確認 | T4 で確認し、G4-3・G4-4 で判定する |
| サンドボックスで `electron-builder`・`codesign` が動くか | 未確認 | 動かなければ U として利用者の端末で実行する |
| `smoke.js` を `.app` に同梱すること | 意図した設計 | 本人用なので害はない。配布するなら外す |
| `maplibre-gl@5.24.0` の advisory | 修正版なし | Web 版と共通の問題として別途追う。デスクトップ版はページの内容がローカルのファイルだけなので、外部から入力が入る経路は検索欄だけ |
| ディスク容量 | `.app` は推定 3.5〜4 GB、取得中の `work/` は推定約 7 GB | T1 の前に空きを確認する（2026-10-07 時点で約 1,369 GB） |
| Electron を起動するテストをサンドボックスで実行できない | 確認済み | U のゴールは利用者の端末で実行する。それ以外は S で判定できるように分けた |

## 7. 試作の記録（2026-10-07）

計画を立てる前に、取得から PMTiles 化までと Electron の骨組みを試作した。試作したファイル（`tools/offline_tiles.py`、`desktop/`、`work/`）はコミットせずに削除した。実装は本書から改めて行う。

| 確認したこと | 結果 |
| --- | --- |
| `tools/offline_tiles.py plan` の枚数 | §2 のとおり |
| `fetch --sample` → `pack` | 4 層とも取得できた（404 は 0 件）。PMTiles のサイズ：写真 2.07 MB、淡色 1.63 MB、標準 2.11 MB、道路 0.36 MB |
| 地理院の応答 | 初回の取得で `IncompleteRead`（応答の途中切断）が出た。再試行の対象に加えて解消（G0-4 に反映） |
| 取得の速さ | `--rate 8 --workers 4` で 6.3〜7.9 件/秒、道路は 4.1 件/秒（ディレクトリの読み込みを含む） |
| SRI の一致 | 3 ファイルとも一致 |
| Electron の起動（`smoke.js`） | サンドボックス内では終わらず、停止した。表示できるかは未確認。本書では smoke に全体の時間制限（G2-12）を設け、Electron に依存しない部分を単体テストに分けた |
| 作業環境 | `npm` はキャッシュを `$TMPDIR` に向ける必要があった。Electron 本体の取得には `NODE_USE_ENV_PROXY=1` が必要だった（サンドボックスのプロキシ経由のため）。`pip` はサンドボックスの外で実行した |

### 試作から変えた点

| 項目 | 試作 | 本書 |
| --- | --- | --- |
| 振り分けの置き場所 | `main.js` に Electron の処理と一緒に書いた | `routes.js` に分け、Node だけで単体テストする（G2-1〜G2-8） |
| smoke の起動 | `smoke.js` が `main.js` を読み込む別の入口 | `main.js` が `--smoke` で `smoke.js` を読み込む。パッケージ後も同じ検証を使える（G4-4） |
| smoke の終了 | 時間制限なし | 180 秒で `SMOKE TIMEOUT`・終了コード 2 |
| 拒否したホストの判定 | ログに出すだけ | `refusedHosts()` で取り出し、`result.json` に書く（G3-1） |
| 取得の速さの上限 | `--rate` に上限なし | 上限 8（G0-5） |
| 取得結果の検証 | `pack` の件数の警告だけ | `verify`（ヘッダー・件数・全タイルの照合・全国版との照合）と `pack --strict` |
| electron の版 | `^44.6.0` | `^` なしで固定 |

### 本番取得の記録（T1・T4 の後に記入）

| 層 | 対象 | 404 | PMTiles のサイズ | 取得日 |
| --- | --- | --- | --- | --- |
| photo | 51,815 | 未記録 | 未記録 | 未記録 |
| pale | 51,815 | 未記録 | 未記録 | 未記録 |
| std | 51,815 | 未記録 | 未記録 | 未記録 |
| road | 5,178 | 未記録 | 未記録 | 未記録 |

`.app` の合計サイズ：未記録
