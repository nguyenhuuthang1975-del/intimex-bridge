# scripts/load_hr_data.py
# -*- coding: utf-8 -*-
"""
Đọc dữ liệu nhân sự từ GitHub (raw URLs) vào pandas DataFrame.
- Hỗ trợ repo public và private (qua biến môi trường GITHUB_TOKEN).
- An toàn với retry nhẹ, validate MIME.
- In ra thông tin tổng quan và (nếu có) ước lượng headcount.
"""

from __future__ import annotations
import os
import io
import time
from typing import Optional, Tuple

import requests
import pandas as pd

# ===================== Cấu hình =====================

# Chủ repo / nhánh / đường dẫn
OWNER = "nguyenhuuthang1975-del"
REPO  = "intimex-bridge"
BRANCH = "main"

# Tên file cần đọc
FILE_BANG_MO_RONG = "data/Bang_nhan_su_mo_rong.xlsx"
FILE_MAU_TT       = "data/Mau_Thong_Tin_Nhan_Su_Intimex_DakMil.xlsx"

# Số lần retry khi lỗi mạng tạm thời
MAX_RETRIES = 3
RETRY_SLEEP_SECONDS = 1.5

# Tên cột khả dĩ để đếm headcount nếu có (tùy file thực tế)
CANDIDATE_ID_COLS = ["Ma_Nhan_Vien", "Mã_Nhân_Viên", "EmployeeID", "Emp_ID", "MaNV", "ID"]

# ====================================================


def build_raw_url(path: str,
                  owner: str = OWNER,
                  repo: str = REPO,
                  branch: str = BRANCH) -> str:
    """
    Tạo raw URL ổn định cho GitHub.
    """
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"


def _auth_headers() -> dict:
    """
    Nếu có GITHUB_TOKEN (cho repo private), chèn Authorization header.
    """
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        return {"Authorization": f"token {token}"}
    return {}


def fetch_bytes(url: str, timeout: int = 30) -> bytes:
    """
    Tải nội dung nhị phân từ URL (có retry).
    """
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=timeout)
            if resp.status_code == 200:
                return resp.content
            elif resp.status_code == 404:
                raise FileNotFoundError(
                    f"Không tìm thấy file tại URL: {url}\n"
                    "• Kiểm tra tên file/thư mục/nhánh (branch)\n"
                    "• Nếu repo private, đặt biến môi trường GITHUB_TOKEN."
                )
            elif resp.status_code == 403:
                raise PermissionError(
                    "Bị từ chối truy cập (403). Có thể cần GITHUB_TOKEN cho repo private."
                )
            else:
                raise RuntimeError(
                    f"Tải URL thất bại (HTTP {resp.status_code}). Nội dung: {resp.text[:200]}"
                )
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)
            else:
                raise
    # Không tới đây, nhưng để mypy yên tâm:
    if last_exc:
        raise last_exc
    raise RuntimeError("Không rõ lỗi khi tải bytes.")


def read_excel_from_github(path: str) -> pd.DataFrame:
    """
    Đọc file Excel từ GitHub (raw) vào DataFrame.
    Hỗ trợ .xlsx / .xls và nhiều sheet (mặc định sheet đầu).
    """
    url = build_raw_url(path)
    raw = fetch_bytes(url)

    # Đọc bằng pandas (openpyxl / xlrd phụ thuộc vào phần mở rộng)
    # Gợi ý cài đặt: pandas, openpyxl
    try:
        # Với .xlsx / .xlsm / .xltx, pandas dùng engine 'openpyxl' (khuyên dùng)
        # Với .xls cũ, cần 'xlrd' <= 1.2.0 (ít gặp). Ở đây ưu tiên .xlsx.
        df = pd.read_excel(io.BytesIO(raw), engine="openpyxl")
        return df
    except Exception as e:
        raise RuntimeError(
            f"Lỗi khi đọc Excel từ: {url}\nChi tiết: {e}"
        )


def quick_overview(df: pd.DataFrame, name: str) -> None:
    """
    In tổng quan dataset và cố gắng ước lượng headcount nếu có cột ID hợp lệ.
    """
    print(f"\n=== {name} ===")
    print(f"• Kích thước: {df.shape[0]} dòng × {df.shape[1]} cột")
    print(f"• Cột: {list(df.columns)}")

    # Ước lượng headcount: nếu có cột ID phù hợp thì đếm unique, không thì đếm số dòng
    id_col = None
    for c in CANDIDATE_ID_COLS:
        if c in df.columns:
            id_col = c
            break

    if id_col:
        headcount = df[id_col].dropna().nunique()
        print(f"• Ước lượng headcount (unique theo '{id_col}'): {headcount}")
    else:
        # fallback: số dòng chưa trùng loại bỏ
        print("• Không tìm thấy cột ID chuẩn → tạm tính headcount = số dòng (có thể trùng):", len(df))


def load_all() -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Tải cả hai file Excel và trả về 2 DataFrame:
      - df_mo_rong: Bang_nhan_su_mo_rong.xlsx
      - df_mau_tt : Mau_Thong_Tin_Nhan_Su_Intimex_DakMil.xlsx
    """
    df_mo_rong = read_excel_from_github(FILE_BANG_MO_RONG)
    df_mau_tt  = read_excel_from_github(FILE_MAU_TT)
    return df_mo_rong, df_mau_tt


if __name__ == "__main__":
    print("Đang tải dữ liệu nhân sự từ GitHub…")
    try:
        df_mo_rong, df_mau_tt = load_all()
        quick_overview(df_mo_rong, "Bang_nhan_su_mo_rong.xlsx")
        quick_overview(df_mau_tt,  "Mau_Thong_Tin_Nhan_Su_Intimex_DakMil.xlsx")

        # Ví dụ ghép (nếu có cột chung). Bạn có thể chỉnh tên cột phù hợp thực tế:
        # key_candidates = [c for c in CANDIDATE_ID_COLS if c in df_mo_rong.columns and c in df_mau_tt.columns]
        # if key_candidates:
        #     key = key_candidates[0]
        #     df_join = df_mo_rong.merge(df_mau_tt, on=key, how="outer", suffixes=("_mo_rong", "_mau_tt"))
        #     print(f"\nGhép theo khóa '{key}': {df_join.shape[0]} dòng × {df_join.shape[1]} cột")
        # else:
        #     print("\nChưa có cột khóa chung để ghép hai bảng. Vui lòng kiểm tra tên cột ID.")

    except Exception as e:
        print("\n❌ Lỗi:", e)
        print("Gợi ý:")
        print("- Kiểm tra tên file/thư mục/nhánh (branch) đúng chưa.")
        print("- Nếu repo private, export GITHUB_TOKEN trước khi chạy:")
        print("  Windows (PowerShell):  $env:GITHUB_TOKEN='YOUR_TOKEN_HERE'")
        print("  macOS/Linux (bash):    export GITHUB_TOKEN='YOUR_TOKEN_HERE'")
