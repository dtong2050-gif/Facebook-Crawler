"""Export dữ liệu posts/comments ra file Excel với openpyxl."""

from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from scrapers.base import PostData
from utils.helpers import url_to_page_name
from utils.logger import setup_logger

logger = setup_logger(__name__)

MAX_ROWS_PER_SHEET = 50_000

# Header styling (màu xanh Facebook)
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_HEADER_FILL = PatternFill(start_color="1877F2", end_color="1877F2", fill_type="solid")
_HEADER_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
_DATA_ALIGN = Alignment(vertical="top", wrap_text=True)


class ExcelExporter:
    """Tạo file .xlsx với sheet Posts và Comments từ list PostData."""

    def __init__(self, output_dir: Path) -> None:
        """Khởi tạo exporter.

        Args:
            output_dir: Thư mục lưu file output
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, posts: list[PostData], page_name: str) -> Path:
        """Export toàn bộ posts (và comments của chúng) ra file Excel.

        Args:
            posts: List PostData đã cào
            page_name: Tên page ngắn gọn (dùng trong tên file)

        Returns:
            Path tuyệt đối đến file .xlsx đã tạo
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        safe_name = page_name[:40].replace("/", "_")
        filename = f"crawl_{timestamp}_{safe_name}.xlsx"
        filepath = self.output_dir / filename

        wb = openpyxl.Workbook()
        # Xóa sheet mặc định "Sheet"
        if wb.active:
            wb.remove(wb.active)

        self._write_posts_sheets(wb, posts)
        self._write_comments_sheets(wb, posts)

        wb.save(filepath)
        logger.info(f"Đã export: {filepath} ({len(posts)} posts)")
        return filepath

    def _write_posts_sheets(self, wb: openpyxl.Workbook, posts: list[PostData]) -> None:
        """Ghi dữ liệu bài viết vào sheet(s) Posts.

        Tự động tạo Posts_2, Posts_3, ... nếu vượt MAX_ROWS_PER_SHEET.
        Cột "Nguồn" chỉ xuất hiện khi crawl theo từ khóa tìm kiếm (post.source có giá trị).

        Args:
            wb: Workbook đang ghi
            posts: List PostData
        """
        has_source = any(p.source for p in posts)
        if has_source:
            headers = ["STT", "Post_ID", "Author", "Nguồn", "Content", "URL"]
        else:
            headers = ["STT", "Post_ID", "Author", "Content", "URL"]

        sheet_idx = 1
        row_count = 0
        ws: Optional[Worksheet] = None
        stt = 1

        for post in posts:
            if ws is None or row_count >= MAX_ROWS_PER_SHEET:
                sheet_name = "Posts" if sheet_idx == 1 else f"Posts_{sheet_idx}"
                ws = wb.create_sheet(sheet_name)
                self._write_header(ws, headers)
                row_count = 0
                sheet_idx += 1

            if has_source:
                row = [stt, post.post_id, post.author, post.source, post.content, post.url]
            else:
                row = [stt, post.post_id, post.author, post.content, post.url]
            ws.append(row)
            self._style_data_row(ws, ws.max_row, len(headers))
            row_count += 1
            stt += 1

        if ws is None:
            # Luôn tạo sheet Posts dù không có dữ liệu
            ws = wb.create_sheet("Posts")
            self._write_header(ws, headers)
        self._auto_adjust_columns(ws)

    def _write_comments_sheets(self, wb: openpyxl.Workbook, posts: list[PostData]) -> None:
        """Ghi dữ liệu comments vào sheet(s) Comments.

        Tự động tạo Comments_2, ... nếu vượt MAX_ROWS_PER_SHEET.

        Args:
            wb: Workbook đang ghi
            posts: List PostData (lấy comments từ đây)
        """
        headers = ["STT", "Post_ID", "Author", "Content"]

        sheet_idx = 1
        row_count = 0
        ws: Optional[Worksheet] = None
        stt = 1

        for post in posts:
            for comment in post.comments:
                if ws is None or row_count >= MAX_ROWS_PER_SHEET:
                    sheet_name = "Comments" if sheet_idx == 1 else f"Comments_{sheet_idx}"
                    ws = wb.create_sheet(sheet_name)
                    self._write_header(ws, headers)
                    row_count = 0
                    sheet_idx += 1

                ws.append([stt, comment.post_id, comment.author, comment.content])
                self._style_data_row(ws, ws.max_row, len(headers))
                row_count += 1
                stt += 1

        if ws is None:
            # Luôn tạo sheet Comments dù không có dữ liệu
            ws = wb.create_sheet("Comments")
            self._write_header(ws, headers)
        self._auto_adjust_columns(ws)

    def _write_header(self, ws: Worksheet, headers: list[str]) -> None:
        """Ghi header row với style màu xanh, freeze và auto-filter.

        Args:
            ws: Worksheet
            headers: List tên cột
        """
        ws.append(headers)
        ws.row_dimensions[1].height = 28

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.alignment = _HEADER_ALIGN

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    def _style_data_row(self, ws: Worksheet, row_num: int, num_cols: int) -> None:
        """Áp dụng style căn lề cho data row.

        Args:
            ws: Worksheet
            row_num: Số hàng cần style
            num_cols: Số cột
        """
        for col_idx in range(1, num_cols + 1):
            ws.cell(row=row_num, column=col_idx).alignment = _DATA_ALIGN

    def _auto_adjust_columns(self, ws: Worksheet, max_width: int = 60) -> None:
        """Tự động điều chỉnh độ rộng cột dựa theo content.

        Args:
            ws: Worksheet
            max_width: Độ rộng tối đa (characters)
        """
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                try:
                    cell_len = len(str(cell.value)) if cell.value is not None else 0
                    # Tính theo dòng đầu tiên nếu có nhiều dòng
                    first_line = str(cell.value).split("\n")[0] if cell.value else ""
                    max_len = max(max_len, len(first_line))
                except Exception:
                    pass
            ws.column_dimensions[col_letter].width = max(min(max_len + 4, max_width), 10)
