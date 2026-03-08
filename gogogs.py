#!/usr/bin/env python

import argparse
import io
import os
import re
import sys
import time
import requests

from dotenv import load_dotenv
import pandas as pd
import gspread

load_dotenv()


def fetchRefuelHistory(page_number: int) -> pd.DataFrame:
    html = fetchGogoGsMyCarPageAsHtml(page_number)
    df = extractRefuelHistory(html)
    df["総走行距離"] = df["総走行距離"].astype(dtype=int)
    df.sort_values(by="総走行距離", ascending=True, inplace=True)
    return df


def _create_session() -> requests.Session:
    """
    gogo.gsへの認証済みセッションを作成する
    """
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-encoding": "gzip",
    })
    session.cookies.set("u_id", os.environ["GOGOGS_U_ID"], domain="my.gogo.gs")
    session.cookies.set("u_id_key", os.environ["GOGOGS_U_ID_KEY"], domain="my.gogo.gs")
    # Laravelのログイン永続化Cookie (remember_web_*)
    if os.environ.get("GOGOGS_REMEMBER_TOKEN"):
        session.cookies.set(
            "remember_web_59ba36addc2b2f9401580f014c7f58ea4e30989d",
            os.environ["GOGOGS_REMEMBER_TOKEN"],
            domain="my.gogo.gs",
        )
    return session


# モジュールレベルでセッションを保持（複数ページ取得時にCookieを維持）
_session = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _create_session()
    return _session


def fetchGogoGsMyCarPageAsHtml(page_number):
    """
    gogo.gsの燃費・給油履歴のページをhtmlとして取得する
    """
    mycar_id = os.environ["GOGOGS_MYCAR_ID"]
    url = f"https://my.gogo.gs/refuel/log/{mycar_id}"
    if page_number > 1:
        url += f"?page={page_number}"

    session = _get_session()
    response = session.get(url=url)
    return response.content


def extractRefuelHistory(html_binary) -> pd.DataFrame:
    """
    燃費・給油履歴ページのhtmlから給油履歴のテーブルをDataFrameとして取得する
    """
    html_str = html_binary.decode("utf-8")
    # テーブル中の単位を削除するregex
    html_unit_dropped = re.sub(r"(Km \/ L|Km|L)", "", html_str)
    dfs = pd.read_html(io.StringIO(html_unit_dropped), flavor="bs4", header=0)
    return dfs[0]


def detectTotalPages() -> int:
    """
    1ページ目のHTMLからページネーションを解析し、最終ページ番号を返す
    """
    html = fetchGogoGsMyCarPageAsHtml(1)
    html_str = html.decode("utf-8")
    # ページネーションのリンクから最大ページ番号を検出
    page_numbers = re.findall(r'[?&]page=(\d+)', html_str)
    if page_numbers:
        return max(int(p) for p in page_numbers)
    return 1


def formatDataFrameForPaste(df):
    """
    DataFrameをスプレッドシートに貼り付けるために整形する
    """
    df["総走行距離"] = df["総走行距離"].astype(dtype=int)
    df = df.drop("単価", axis=1).drop("利用金額", axis=1)
    return df.sort_values(by="総走行距離", ascending=True)


def sendToWorksheet(df, wks, row_origin, col_origin):
    row_cnt = len(df)
    col_cnt = len(df.columns)
    # cell_listが1次元のため貼り付けデータも1次元にする必要がある
    flatted_arr = [item for row in df.values.tolist() for item in row]
    cell_list = wks.range(
        row_origin, col_origin, row_origin + row_cnt - 1, col_origin + col_cnt - 1
    )
    for i, cell in enumerate(cell_list):
        cell.value = flatted_arr[i]
    wks.update_cells(cell_list, "USER_ENTERED")
    return


def main(args):
    start_page = args.page
    if args.all:
        print("全ページ数を検出中...", file=sys.stderr)
        end_page = detectTotalPages()
        print(f"全 {end_page} ページを取得します", file=sys.stderr)
    elif args.end_page:
        end_page = args.end_page
    else:
        end_page = start_page

    dfs = []
    for p in range(start_page, end_page + 1):
        print(f"ページ {p}/{end_page} を取得中...", file=sys.stderr)
        df = fetchRefuelHistory(p)
        dfs.append(df)
        if p < end_page:
            time.sleep(1)  # サイト側への負荷軽減

    df = pd.concat(dfs, ignore_index=True)
    df.sort_values(by="総走行距離", ascending=True, inplace=True)
    df = df.drop("単価", axis=1).drop("利用金額", axis=1)

    if args.mode == "csv":
        # CSV出力モード
        output_path = args.output
        if args.append and os.path.isfile(output_path):
            # 既存CSVを読み込み、新規データとマージ
            df_existing = pd.read_csv(output_path)
            new_count_before = len(df)
            df = pd.concat([df_existing, df], ignore_index=True)
            df.drop_duplicates(subset=["総走行距離"], keep="last", inplace=True)
            df.sort_values(by="総走行距離", ascending=True, inplace=True)
            added = len(df) - len(df_existing)
            print(f"既存 {len(df_existing)} 件 + 新規 {added} 件 → 合計 {len(df)} 件")
            # appendモードではヘッダーを常に付与（既存ファイルとの整合性のため）
            df.to_csv(output_path, header=True, index=False)
        else:
            df.to_csv(output_path, header=not args.no_csv_header, index=False)
        print(f"CSV written to {output_path}")
        return

    elif args.mode == "gspread":
        # Google Spreadsheet書き込みモード
        if args.gspread_auth:
            gc = gspread.service_account(filename=args.gspread_auth)
        else:
            gc = gspread.service_account()

        ss = gc.open("走行距離")
        wks = ss.sheet1

        date_list = wks.col_values(1)
        if not date_list:
             # シートが空の場合は全データを書き込むために、比較用の日付をありえない古い日付にする
             last_refuel_date = "1900/01/01"
        else:
             last_refuel_date = date_list[-1]

        df_extracted = df[df["給油日"] > last_refuel_date]
        if len(df_extracted) > 0:
            last_row = len(date_list)
            # gspreadのcellのインデックスは1から始まることに注意
            sendToWorksheet(df_extracted, wks, last_row + 1, 1)
        print("{} data written.".format(df_extracted.shape[0]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--page", type=int, default=1, help="取得開始ページ番号 (default: 1)")
    parser.add_argument(
        "--end-page",
        type=int,
        default=None,
        help="取得終了ページ番号 (指定しない場合は --page のみ)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="全ページを取得",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["csv", "gspread"],
        default="csv",
        help="Output mode: csv or gspread (default: csv)",
    )
    parser.add_argument(
        "--no-csv-header",
        action="store_true",
        help="CSVモード時、ヘッダー行を除外して出力します",
    )
    parser.add_argument(
        "--gspread-auth",
        type=str,
        default=None,
        help="Path to Google service account JSON file",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="fuel_log.csv",
        help="Output CSV file path (default: fuel_log.csv)",
    )
    parser.add_argument(
        "-a",
        "--append",
        action="store_true",
        help="既存CSVにデータを追記（総走行距離で重複排除）",
    )
    args = parser.parse_args()
    main(args)
