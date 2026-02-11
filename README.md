# gogogs-fuel-log

gogo.gs (ゴーゴージーエス) のマイカー給油履歴をスクレイピングし、Google スプレッドシートに自動で転記・同期する Python スクリプトです。

## 機能

- gogo.gs の「燃費・給油履歴」ページからデータを取得します。
- 取得したデータのうち、**既存の Google スプレッドシートに存在しない新しい記録のみ**を追記します。
- 注: スクリプトの仕様により、「単価」と「利用金額」のカラムは除外して保存されます。

## 事前準備

このツールを使用するには、以下の準備が必要です。

1. **Python 3.x** の環境
2. **gogo.gs のアカウント**（給油記録があること）
3. **Google Cloud Platform (GCP) サービスアカウント**（スプレッドシート書き込み用）

## セットアップ

### 1. ライブラリのインストール

必要な Python ライブラリをインストールします。

```bash
pip install requests pandas numpy gspread beautifulsoup4 html5lib
```

### 2. 環境変数の設定 (.env)

`.env.example` をコピーして `.env` ファイルを作成します。

```bash
cp .env.example .env
```

`.env` ファイルを開き、以下の手順で値を埋めてください。

#### `GOGOGS_MYCAR_ID` の取得
1. gogo.gs にログインし、自分の車種の「給油履歴」ページを開きます。
2. URL を確認し、`mycar_id=` の後ろにある数字をコピーします。
   - URL例: `https://my.gogo.gs/refuel/log/?mycar_id=12345` → `12345`

#### `GOGOGS_U_ID` および `GOGOGS_U_ID_KEY` の取得 (Cookie)
gogo.gs は API を公開していないため、ブラウザの Cookie を使用して認証します。

1. PC ブラウザ（Chromeなど）で gogo.gs にログインします。
2. 開発者ツールを開きます（F12 キー または 右クリック > 「検証」）。
3. **「アプリケーション」** (Application) タブを開きます。
   - ※ Firefox の場合は「ストレージ」タブ
4. 左側のメニューから **「Cookie」** > `https://gogo.gs` (または `my.gogo.gs`) を選択します。
5. リストの中から以下の名前を探し、その「値 (Value)」をコピーして `.env` に貼り付けます。
   - `u_id`
   - `u_id_key`

### 3. Google スプレッドシートの設定

1. 新規スプレッドシートを作成し、シート名を **`走行距離`** に変更します。
   - **重要**: スクリプトは `走行距離` という名前のシートを探します。
2. GCP コンソールでサービスアカウントを作成し、JSON キーファイルを発行します。
3. そのサービスアカウントのメールアドレス（`xxx@xxx.iam.gserviceaccount.com`）に対して、作成したスプレッドシートの「編集権限」を付与（共有）します。
4. サービスアカウントの JSON キーの設定は `gspread` の標準的な方法に従ってください。
   - 最も簡単な方法は、JSONファイルを `service_account.json` という名前でこのスクリプトと同じディレクトリに置くことなどは、`gspread` のドキュメントを参照してください。

## 使い方

スクリプトを実行すると、デフォルトでは Google スプレッドシートへの同期を行います。

```bash
# デフォルト実行（スプレッドシートへの同期）
python gogogs.py
```

### オプション

| 引数 | 説明 |
| :--- | :--- |
| `-m`, `--mode` | 出力モードを指定します (`gspread` または `csv`)。デフォルトは `gspread`。 |
| `-p`, `--page` | 取得するページ番号を指定します。デフォルトは `1`。 |
| `--csv-header` | CSVモード時、ヘッダー行を含めて出力します。 |
| `--gspread-auth` | Google サービスアカウントの JSON キーファイルのパスを指定します。 |

### 実行例

#### CSV として出力する場合
標準出力に CSV 形式で結果を表示します。リダイレクトしてファイルに保存することも可能です。

```bash
# 最新1ページ分をヘッダー付きでCSV出力
python gogogs.py --mode csv --csv-header > fuel_log.csv

# 過去のデータをCSV出力（ヘッダーなし）
python gogogs.py --mode csv --page 2
```

#### Google スプレッドシートの認証ファイルを指定する場合
デフォルトの場所（`~/.config/gspread/service_account.json` など）以外にある JSON ファイルを使用する場合に指定します。

```bash
python gogogs.py --gspread-auth /path/to/your-service-account.json
```