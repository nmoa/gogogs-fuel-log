#!/usr/bin/env python

import argparse
import io
import os
import re
import requests

import numpy as np
import pandas as pd
import gspread


def fetchRefuelHistory(page_number: int) -> pd.DataFrame:
    html = fetchGogoGsMyCarPageAsHtml(page_number)
    df = extractRefuelHistory(html)
    df["総走行距離"] = df["総走行距離"].astype(dtype=int)
    df.sort_values(by="給油日", ascending=True, inplace=True)
    return df


def fetchGogoGsMyCarPageAsHtml(page_number):
    """
    gogo.gsの燃費・給油履歴のページをhtmlとして取得する
    """
    if page_number == 1:
        page_string = ""
    else:
        page_string = "&page={}".format(page_number)

    url = f"https://my.gogo.gs/refuel/log/?mycar_id={os.environ['GOGOGS_MYCAR_ID']}{page_string}"

    headers = {"User-Agent": "Magic Browser", "Accept-encoding": "gzip"}
    cookie = {
        "u_id": os.environ["GOGOGS_U_ID"],
        "u_id_key": os.environ["GOGOGS_U_ID_KEY"],
    }
    request = requests.get(url=url, headers=headers, cookies=cookie)
    return request.content


def extractRefuelHistory(html_binary) -> pd.DataFrame:
    """
    燃費・給油履歴ページのhtmlから給油履歴のテーブルをDataFrameとして取得する
    """
    html_str = html_binary.decode("utf-8")
    # テーブル中の単位を削除するregex
    html_unit_dropped = re.sub(r"(Km \/ L|Km|L)", "", html_str)
    dfs = pd.read_html(io.StringIO(html_unit_dropped), flavor="bs4", header=0)
    return dfs[0]


def formatDataFrameForPaste(df):
    """
    DataFrameをスプレッドシートに貼り付けるために整形する
    """
    df["総走行距離"] = df["総走行距離"].astype(dtype=int)
    df = df.drop("単価", axis=1).drop("利用金額", axis=1)
    return df.sort_values(by="給油日", ascending=True)


def sendToWorksheet(df, wks, row_origin, col_origin):
    arr = np.asarray(df)
    row_cnt = arr.shape[0]
    col_cnt = arr.shape[1]
    flatted_arr = (
        arr.flatten()
    )  # cell_listが1次元のため貼り付けデータも1次元にする必要がある
    cell_list = wks.range(
        row_origin, col_origin, row_origin + row_cnt - 1, col_origin + col_cnt - 1
    )
    for i, cell in enumerate(cell_list):
        cell.value = flatted_arr[i]
    wks.update_cells(cell_list, "USER_ENTERED")
    return


def main(page_number: int):
    df = fetchRefuelHistory(page_number)
    df = df.drop("単価", axis=1).drop("利用金額", axis=1)

    gc = gspread.service_account()
    ss = gc.open("走行距離")
    wks = ss.sheet1

    date_list = wks.col_values(1)
    last_refuel_date = date_list[-1]
    df_extracted = df[df["給油日"] > last_refuel_date]
    if len(df_extracted) > 0:
        last_row = len(date_list)
        # gspreadのcellのインデックスは1から始まることに注意
        sendToWorksheet(df_extracted, wks, last_row + 1, 1)
    print("{} data written.".format(df_extracted.shape[0]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--page", type=int, default=1)
    args = parser.parse_args()
    main(args.page)
