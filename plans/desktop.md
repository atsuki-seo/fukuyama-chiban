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
| 取得の作法 | 取得の速さに上限を設ける（既定 8 件/秒）。再開できるようにする。403・429 を受けたら即座に止める。User-Agent で用途を名乗る | [地理院地図の利用規約](https://maps.gsi.go.jp/help/termsofuse.html)に、過剰な負荷を与える通信は遮断することがあるとある |
| ライブラリ | `maplibre-gl@5.24.0` と `pmtiles@4.5.0` を npm から入れ、`index.html` の unpkg URL への要求にそのファイルを返す | npm と unpkg のファイルは同じで、`index.html` の SRI ハッシュがそのまま一致する（§2） |
| 取得したデータの置き場所 | `work/offline/`（`.gitignore` 済み）。**コミットも公開もしない** | リポジトリは公開されている。地理院タイルの再配布にあたる |
| 置き場所（コード） | リポジトリ直下に `desktop/` を作る | Pages の公開対象は `.github/workflows/pages.yml` の allowlist だけなので、`desktop/` は公開されない |

### 対象外

- Windows・Linux 版、自動更新、コード署名・公証（Developer ID）
- 他者への配布（必要になったら、地理院への申請要否の確認から別案件として扱う）
- 市域外の背景、z19 以上の背景（z18 のタイルを拡大表示する。Web 版と同じ）
- Web 版（`index.html`）の変更。デスクトップ版でだけ出る差異は §3「Web 版との差異」で受け入れる

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
| 福山駅周辺の約 800 m 四方（背景 93 枚、道路 17 枚）を取得したときの 1 枚あたりの平均：写真 22 KB、淡色地図 17.5 KB、標準地図 22.7 KB、道路 21 KB | 試作で取得した結果 |
| 上の平均を全体に掛けた推定：写真 約 1.1 GB、淡色地図 約 0.9 GB、標準地図 約 1.2 GB、道路 約 0.1 GB、**合計 約 3.3 GB**。市街地の平均なので、郊外・海が多い分だけ実際は小さくなる見込み | 推論（ソースは前行のサンプル） |
| 取得時間の目安：8 件/秒で約 5.6 時間 | 160,623 ÷ 8 |
| npm の `maplibre-gl@5.24.0`（css・js）と `pmtiles@4.5.0`（`dist/pmtiles.js`）の sha384 は、`index.html` の `integrity` と一致する | 試作で `openssl dgst -sha384` により確認 |
| Electron の最新版は 44.6.0（2026-10-07 時点の npm） | 試作で `npm install` |
| `maplibre-gl@5.24.0` に critical の advisory がある（GHSA-jrc7-96c5-q579、`DOM.sanitize()` の XSS。修正版なし）。Web 版も同じ版を使っている | `npm audit` |
| Claude Code の Bash サンドボックスでは Chromium が起動しない。Electron の起動も試作では終わらなかった | `plans/pwa.md` §7、試作 |
| 地番 PMTiles・検索索引・マスク・フォントはすでにリポジトリ内にある（約 176 MB） | README「Files」 |

## 3. 全体構成

```
tools/offline_tiles.py   地理院タイルを取得して PMTiles にまとめる（plan / fetch / pack）
work/offline/            取得結果（.gitignore 済み、コミットしない）
  {photo,pale,std,road}.sqlite    取得途中の保存先。再開に使う
  {photo,pale,std,road}.pmtiles   アプリに同梱するファイル
desktop/
  package.json           electron・electron-builder・maplibre-gl・pmtiles（ライブラリは版を固定）
  main.js                app:// の配信、https の横取り、ウィンドウ
  smoke.js               main.js をそのまま読み込み、数か所の表示を確認して終了する検証スクリプト
  dist/                  ビルド結果（.gitignore に追加する）
```

### リクエストの振り分け（`main.js`）

| ページからの要求 | 応答 |
| --- | --- |
| `app://fukuyama-chiban/<path>` | サイトのファイル。許可リスト（`index.html`、`*.pmtiles`、`search.json`、`search/<n>.json`、`fukuyama_mask.geojson`、`fonts/**`、`icons/**`、`manifest.webmanifest`）に一致するものだけを返す。Range に 206 で応答する |
| `https://unpkg.com/{maplibre-gl,pmtiles}@<版>/dist/<file>` | `node_modules` の同じファイル。`<版>` は `node_modules` の `package.json` から求める |
| `https://cyberjapandata.gsi.go.jp/xyz/{seamlessphoto,pale,std}/{z}/{x}/{y}.{jpg,png}` | `offline/{photo,pale,std}.pmtiles` から 1 枚取り出す。範囲外なら 404 |
| `https://cyberjapandata.gsi.go.jp/xyz/optimal_bvmap-v1/optimal_bvmap-v1.pmtiles` | `offline/road.pmtiles` を Range つきで返す。ページの PMTiles ライブラリはヘッダーから読み直すので、全国版と同じ URL のまま市域版を読ませられる |
| その他の http(s) | 503（拒否）。ホストごとに 1 回だけログに出す |
| リンクのクリック（`target="_blank"`・画面遷移） | アプリ内では開かず、既定のブラウザで開く |

https で返す応答には `Access-Control-Allow-Origin: *` などの CORS ヘッダーを付ける。ページの origin は `app://` で、unpkg のファイルは `crossorigin="anonymous"` と SRI 付きで読み込まれるため。

### パッケージの中身（electron-builder、`--mac dir`）

```
福山市 地番マップ.app/Contents/Resources/
  app.asar        main.js と node_modules（maplibre-gl・pmtiles）
  site/           index.html ほか、上の許可リストのファイル
  offline/        {photo,pale,std,road}.pmtiles
```

開発時（`npm start`）は、`site/` の代わりにリポジトリ直下を、`offline/` の代わりに `work/offline/` を読む。

### Web 版との差異（受け入れる）

| 項目 | デスクトップ版での挙動 |
| --- | --- |
| Service Worker | `app://` では登録できず、コンソールに警告が 1 件出る。機能への影響はない |
| インストールボタン | `beforeinstallprompt` が来ないので出ない |
| 共有ボタン | URL が `app://fukuyama-chiban/#map=...` になり、他の人には使えない |
| 現在地 | オフラインで位置を取れるかは未確認（§6） |
| 背景の鮮度 | 取得した日の時点で固定。取得日は PMTiles の metadata の `fetched` に残す |

## 4. タスクと検証可能なゴール

ゴールは、`tools/offline_tiles.py`、`desktop/smoke.js`、またはシェルコマンドで合否が出る形にする。例外は「手動」と明記したものだけ。
Electron を起動するゴール（G2・G3・G4）は、サンドボックスでは動かないため、利用者の端末で実行する。

### T0. タイル取得ツール

内容

- `tools/offline_tiles.py` を作る。
  - `plan`：層ごとの対象枚数と取得済みの枚数を表示する。
  - `fetch`：`work/offline/<layer>.sqlite` に保存する。取得済みと 404 の記録は飛ばす。`--rate`・`--workers` で速さを調整する。`--sample` で福山駅周辺だけを取る。
  - `pack`：タイル ID の順に並べて PMTiles を書く。metadata に出典・取得日・取得元 URL・「個人利用、再配布しない」の注記を入れる。道路は元の metadata（`vector_layers`）と圧縮方式を引き継ぐ。
- 依存として `pmtiles`（Python）を `tools/requirements.txt` に加える。
- 範囲の定数（`BOUNDS`、`MIN_ZOOM`）は `index.html` の `APP.bounds`・`APP.minZoom` と同じ値にし、コメントで対応を示す。

ゴール

- **G0-1** `plan` が §2 の枚数（背景 51,815、道路 5,178）を表示する。
- **G0-2** `fetch --sample` の後に `pack` すると、4 つの PMTiles ができる。ヘッダーの `tile_type` は写真が JPEG、地図 2 種が PNG、道路が MVT。道路の `tile_compression` は gzip。
- **G0-3** 同じ `fetch --sample` をもう一度実行すると、取得対象が 0 件になる（再開できる）。
- **G0-4** 応答を差し替えた単体テストで、403 と 429 は即座に停止し、5xx と途中切断（`IncompleteRead`）は再試行し、404 は missing として記録する。
- **G0-5** `pack` した道路の PMTiles から取り出したタイルが、元の全国版の同じ z/x/y のタイルとバイト単位で一致する（サンプルで 5 枚）。

### T1. 全量取得（利用者の確認後に実施）

実行前に利用者に示すこと：地理院のサーバーに約 16 万リクエスト、8 件/秒で約 5.6 時間かかること。`work/` に PMTiles と sqlite をあわせて約 7 GB の空きが要ること（推定）。

ゴール

- **G1-1** `plan` で、4 層とも「取得済み（404 を含む）＝対象枚数」になる。
- **G1-2** `pack` の警告（`only N of M tiles fetched`）が出ない。
- **G1-3** 層ごとの 404 の件数と PMTiles のサイズを本書 §7 に記録する。

### T2. Electron シェル

内容

- `desktop/package.json`（`"type": "module"`。`maplibre-gl`・`pmtiles` は `index.html` と同じ版に固定）、`main.js`、`smoke.js`。
- `.gitignore` に `desktop/dist/`、`desktop/smoke-out/` を足す（`node_modules/` は既にある）。
- `index.html` と `desktop/package.json` のライブラリの版が一致しているかを確かめるスクリプト（`npm run check-versions`）。

ゴール

- **G2-1** `npx electron smoke.js` が `SMOKE OK` で終わる。判定の内容：
  - 写真 z17・淡色 z18・標準 z16（福山駅周辺）の各表示で、背景タイルが 1 枚以上 `loaded`、`errored` が 0 件
  - 地番の地物が 1 件以上描画されている。道路を表示した状態では `RdCL` が 1 件以上ある
  - `fetch('search.json')` が 200、`https://example.com/` が 503、範囲外の地理院タイルが 404
- **G2-2** 検索で「青葉台一丁目 4-1」に移動できる（`plans/pwa.md` の G0-2 と同じ判定）。
- **G2-3** `git diff --exit-code -- index.html` が 0（ページを変更していない）。
- **G2-4** `npm run check-versions` が通る。版がずれると unpkg の要求が拒否されてページが動かなくなるため。
- **G2-5** コンソールのエラーが、Web 版を `tools/serve.py` で開いたときと比べて増えていない。Service Worker の登録失敗の警告 1 件は除く。

### T3. オフライン保証

ゴール

- **G3-1** smoke の実行中に拒否したホストの一覧が空（ページは表にある外部 URL しか使わない）。拒否の一覧を `smoke-out/result.json` に出力して判定する。
- **G3-2**（手動）Wi-Fi を切った状態でアプリを起動し、背景 3 種・道路・地番・検索・ラベルが表示される。

### T4. パッケージ化

内容

- `desktop/package.json` の `build` に、`extraResources`（`site/`・`offline/`）、`mac.target: dir`、アイコン（`icons/icon-512.png`）を書く。
- 署名はしない。Apple Silicon で起動するのに必要な ad-hoc 署名がされるかを確認する（§6）。

ゴール

- **G4-1** `npm run dist` で `.app` ができ、`Contents/Resources/site/index.html` と `Contents/Resources/offline/{photo,pale,std,road}.pmtiles` がある。
- **G4-2** `.app` を別のフォルダ（例：`~/Desktop/`）にコピーし、そこから smoke 相当の確認が通る（リポジトリへのパスに依存していない）。
- **G4-3** `.app` の合計サイズを §7 に記録する。

### T5. README

内容

- 「Desktop app」の節を追加する：個人の検証用で再配布しないこと、地理院の規約上の位置づけ（§2 の推論であること）、取得手順（T0・T1）、ビルド手順（T4）、データの更新手順（地番データの年次更新、背景の取り直し、ライブラリの版を上げるときは `desktop/package.json` もそろえること）。
- 別の Mac にコピーしたとき、Gatekeeper にブロックされた場合の対処を書く（右クリック →「開く」など）。手順の実行は利用者自身が判断する前提で書く。

ゴール

- **G5-1** README の「Files」の表に `desktop/`、`tools/offline_tiles.py`、`plans/desktop.md` が載っている。

### T6. 実機での確認（手動・利用者が実施）

- **G6-1** Wi-Fi を切った状態で、地番をクリックして所在・地番が表示され、道路との関係（道路レイヤーを表示しているとき）が表示される。
- **G6-2** 出典などのリンクが既定のブラウザで開き、アプリ内では開かない。
- **G6-3** 現在地ボタンの挙動を確認し、オフラインで動かない場合はその旨を README に書く。

## 5. 依存関係

```
T0 ── T1 ──┐
  └── T2 ── T3 ── T4 ── T5 ── T6
```

T2 と T3 は `--sample` のデータで進められる。T4 の G4-3 と T6 は T1 の後に行う。

## 6. 未確認事項・リスク

| 項目 | 状態 | 対応 |
| --- | --- | --- |
| 地理院タイルの複製・同梱の扱い | 規約に直接の記述なし。本人の検証用は内部利用と推論 | 利用範囲を本人に限定する。配布するなら地理院に確認する |
| PMTiles への詰め替えが「編集・加工」にあたるか | 未確認。推論では、内容に手を加えないので加工にはあたらない | ページの出典表示（「国土地理院」）はそのまま。README にも書く |
| 一括取得が負荷とみなされるか | 基準は公開されていない | 8 件/秒を上限にし、403・429 で止める。止まったら時間を空けて、より遅くして再開 |
| 最適化ベクトルタイルの変更 | 試験公開 | 取得日を metadata に残す。取り直しで URL やレイヤー名が変わっていたら `index.html` 側も要確認 |
| `protocol.handle('https')` が MapLibre の Web Worker からの要求も横取りするか | 未確認（試作の smoke が完了しなかった） | T2 の G2-1 で確認。だめなら、`index.html` の URL を差し替える方式に切り替える（その場合は G2-3 を見直す） |
| `app://` での CORS と SRI | 未確認 | 同上 |
| Electron の位置情報がオフラインで動くか | 未確認 | T6 の G6-3 |
| Apple Silicon で未署名ビルドが起動するか | 未確認 | T4 で確認。必要なら ad-hoc 署名（`identity: "-"` など。electron-builder の設定名は要確認） |
| `maplibre-gl@5.24.0` の advisory | 修正版なし | Web 版と共通の問題として別途追う。デスクトップ版はページの内容がローカルのファイルだけなので、外部から入力が入る経路は検索欄だけ |
| ディスク容量 | `.app` は推定 3.5〜4 GB、取得中の `work/` は推定約 7 GB | T1 の前に空きを確認する |
| Electron を起動するテストをサンドボックスで実行できない | 確認済み | G2〜G4 は利用者の端末で実行する |

## 7. 試作の記録（2026-10-07）

計画を立てる前に、取得から PMTiles 化までと Electron の骨組みを試作した。試作したファイル（`tools/offline_tiles.py`、`desktop/`、`work/`）はコミットせずに削除した。実装は本書から改めて行う。

| 確認したこと | 結果 |
| --- | --- |
| `tools/offline_tiles.py plan` の枚数 | §2 のとおり |
| `fetch --sample` → `pack` | 4 層とも取得できた（404 は 0 件）。PMTiles のサイズ：写真 2.07 MB、淡色 1.63 MB、標準 2.11 MB、道路 0.36 MB |
| 地理院の応答 | 初回の取得で `IncompleteRead`（応答の途中切断）が出た。再試行の対象に加えて解消（G0-4 に反映） |
| 取得の速さ | `--rate 8 --workers 4` で 6.3〜7.9 件/秒、道路は 4.1 件/秒（ディレクトリの読み込みを含む） |
| SRI の一致 | 3 ファイルとも一致 |
| Electron の起動（`smoke.js`） | サンドボックス内では終わらず、停止した。表示できるかは未確認 |
| 作業環境 | `npm` はキャッシュを `$TMPDIR` に向ける必要があった。Electron 本体の取得には `NODE_USE_ENV_PROXY=1` が必要だった（サンドボックスのプロキシ経由のため）。`pip` はサンドボックスの外で実行した |
