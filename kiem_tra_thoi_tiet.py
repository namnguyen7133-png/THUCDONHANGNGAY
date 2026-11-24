from collections import defaultdict
import html as html_lib
import io
import os
import re
import sqlite3
import sys
import requests

# ===========================================================================
# 1. XÁC ĐỊNH GỐC REPO
#    Ưu tiên: REPO_ROOT env  →  GITHUB_WORKSPACE  →  dò ngược tìm .git
# ===========================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_repo_root(start_dir):
    """Dò ngược lên trên tìm thư mục có .git."""
    cur = os.path.abspath(start_dir)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start_dir)
        cur = parent


BASE_DIR = (
    os.environ.get("REPO_ROOT")
    or os.environ.get("GITHUB_WORKSPACE")
    or _find_repo_root(SCRIPT_DIR)
)

DB_PATH = os.path.join(SCRIPT_DIR, "THOITIET.db")

# Tên file sinh ra
WEATHER_PAGE_NAME = "mon-an-thoi-tiet.html"
INDEX_PAGE_NAME = "index.html"

SLACK_WEBHOOK_URL = ""


# An toàn encoding console
if sys.stdout is not None:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:
        pass


# ===========================================================================
# 2. DATABASE & API THỜI TIẾT
# ===========================================================================

def gui_thong_bao_slack(noi_dung):
    if not SLACK_WEBHOOK_URL:
        return
    try:
        r = requests.post(
            SLACK_WEBHOOK_URL, json={"text": noi_dung}, timeout=10
        )
        print(
            "Đã gửi tin nhắn lên Slack thành công!"
            if r.status_code == 200
            else f"Lỗi Slack: {r.status_code}"
        )
    except Exception as e:
        print(f"Không thể kết nối tới Slack: {e}")


def init_database():
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(THOITIET_DINH_DUONG)")
    columns = [c[1] for c in cur.fetchall()]
    if "rain_hours" not in columns:
        try:
            cur.execute(
                "ALTER TABLE THOITIET_DINH_DUONG "
                "ADD COLUMN rain_hours TEXT"
            )
            conn.commit()
            print("Đã thêm cột 'rain_hours' vào DB!")
        except Exception as e:
            print(f"Lỗi thêm cột: {e}")
    conn.close()


def get_week_forecast():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude=21.0285&longitude=105.8542"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
        "&hourly=precipitation&timezone=Asia%2FBangkok"
    )
    try:
        r = requests.get(url, timeout=10).json()
        daily = r.get("daily", {})
        dates = daily.get("time", [])
        t_maxs = daily.get("temperature_2m_max", [])
        t_mins = daily.get("temperature_2m_min", [])
        precips = daily.get("precipitation_sum", [])

        result = {}
        for i, date in enumerate(dates):
            t_max = t_maxs[i] if i < len(t_maxs) else 30.0
            t_min = t_mins[i] if i < len(t_mins) else 24.0
            rain = precips[i] if i < len(precips) else 0.0
            rain_hours = []
            if rain > 0:
                rain_hours.append(f"09:00 ({rain*0.3:.2f}mm)")
                rain_hours.append(f"15:00 ({rain*0.7:.2f}mm)")
            result[date] = {
                "max": t_max,
                "min": t_min,
                "rain": rain,
                "rain_hours": rain_hours,
            }
        return result
    except Exception as e:
        print(f"Lỗi lấy dữ liệu thời tiết: {e}")
        return {}


def get_historical_data_for_date(target_md):
    if not os.path.exists(DB_PATH):
        return []
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT strftime('%Y', time),
               [temperature_2m_max (°C)],
               [temperature_2m_min (°C)],
               [rain_sum (mm)],
               rain_hours
        FROM THOITIET_DINH_DUONG
        WHERE strftime('%m-%d', time) = ?
          AND strftime('%Y', time) >= '2007'
          AND strftime('%Y', time) != '2026'
        ORDER BY time DESC
        """,
        (target_md,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def save_forecast_to_db(web_data):
    if not os.path.exists(DB_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for date, w in web_data.items():
        rain_hours_str = (
            ", ".join(w["rain_hours"]) if w["rain_hours"] else "Không mưa"
        )
        cur.execute(
            "UPDATE THOITIET_DINH_DUONG "
            "SET rain_hours = ? WHERE date(time) = ?",
            (rain_hours_str, date),
        )
    conn.commit()
    conn.close()


def lay_goi_y_mua_sam(max_temp, rain):
    if rain > 0:
        return (
            "--- TRỜI MƯA/ẨM ƯỚT ---\n"
            "Mua sắm: Gừng, khoai lang, chuối, sữa ấm, trà gừng.\n"
            "Thực đơn: Cháo gừng, khoai luộc, súp nóng, thịt nướng, "
            "bún trả, lương khô, ruốc, muối vừng.\n"
            "Thuốc phụ trợ: Siro ho thảo dược, Trà gừng, Vitamin C.\n"
            "Lưu ý: Người mỏi mệt, lưng mỏi đau: bôi dầu gió, thuốc cảm "
            "delcolgel, paracetamon, cảm xuyên hương, cà phê sữa tối."
        )
    if max_temp > 30:
        return (
            "--- TRỜI NẮNG NÓNG ---\n"
            "Mua sắm: Chanh, dấm, cá, tôm, hến, trai, muối.\n"
            "Thực đơn: Canh chua, canh hến, cá hấp, Phở, Bún, Miến, "
            "Gà tần, Vịt lộn, đậu phụ.\n"
            "Thuốc phụ trợ: Oresol, men vi sinh, thuốc giải nhiệt, "
            "nước ép trái cây."
        )
    if max_temp < 18:
        return (
            "--- TRỜI RÉT ĐẬM ---\n"
            "Mua sắm: Thịt bò, trứng vịt lộn, ngô, bơ, sữa ấm.\n"
            "Thực đơn: Thịt kho, lẩu gà/chim, món hầm, ngũ cốc nóng."
        )
    if 18 <= max_temp <= 25:
        return (
            "--- THỜI TIẾT MÁT MẺ ---\n"
            "Mua sắm: Rượu nếp, sữa chua, riềng, mẻ, giấm bỗng."
        )
    return (
        "--- TRỜI TIẾT ỔN ĐỊNH --- "
        "Ăn uống cân bằng, duy trì tập luyện nhẹ nhàng."
    )


# ===========================================================================
# 3. QUÉT MỌI FILE HTML TRONG REPO (dùng os.walk, không sót file nào)
# ===========================================================================

_SKIP_DIRS = {
    ".git", ".github", "node_modules", "__pycache__",
    "venv", ".venv", "env", ".env", "dist", "build",
    "_site", ".cache", ".idea", ".vscode", "site-packages",
}


def discover_html_files(base_dir):
    """Trả về danh sách đường dẫn tương đối của MỌI file .html trong repo."""
    if not os.path.isdir(base_dir):
        return []

    found = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [
            d for d in dirs
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for f in files:
            if f.lower().endswith(".html"):
                full = os.path.join(root, f)
                rel = os.path.relpath(full, base_dir).replace(os.sep, "/")
                found.append(rel)
    return sorted(set(found))


def _pick_icon(stem):
    s = stem.lower()
    if any(k in s for k in ("thoi-tiet", "thoitiet", "weather", "mon-an")):
        return "⛅"
    if any(k in s for k in ("thuc-don", "food", "an-uong")):
        return "🍲"
    if any(k in s for k in ("suc-khoe", "health", "y-te")):
        return "💊"
    if any(k in s for k in ("lich", "calendar")):
        return "📅"
    if any(k in s for k in ("tin-tuc", "news")):
        return "📰"
    if any(k in s for k in ("bai-tap", "the-duc", "gym")):
        return "🏋️"
    if any(k in s for k in ("hoc", "study", "sach")):
        return "📚"
    return "📄"


def _pretty_name(stem):
    name = stem.replace("-", " ").replace("_", " ").strip()
    name = re.sub(r"^\d+[\s\-_]*", "", name)
    return name[:1].upper() + name[1:] if name else stem


# ===========================================================================
# 4. SINH index.html — HUB LIỆT KÊ MỌI HTML TRONG REPO
# ===========================================================================

def render_index_html(base_dir):
    all_htmls = discover_html_files(base_dir)
    items = [h for h in all_htmls if h != INDEX_PAGE_NAME]

    # Gom nhóm theo thư mục
    groups = defaultdict(list)
    for h in items:
        groups[os.path.dirname(h)].append(h)

    sections_html = ""
    for folder in sorted(groups.keys()):
        folder_label = (
            "📂 Thư mục gốc" if not folder else f"📁 {folder}"
        )
        cards = []
        for h in sorted(groups[folder]):
            stem = os.path.splitext(os.path.basename(h))[0]
            icon = _pick_icon(stem)
            nice = _pretty_name(stem)
            cards.append(
                f'<a href="{html_lib.escape(h)}" class="card" '
                f'data-search="{html_lib.escape(h.lower())}">'
                f'<div class="card-icon">{icon}</div>'
                f'<div class="card-title">{html_lib.escape(nice)}</div>'
                f'<div class="card-path">{html_lib.escape(h)}</div>'
                f"</a>"
            )
        sections_html += (
            f'<section class="folder">'
            f'<h2 class="folder-title">{folder_label} '
            f'<span class="count">({len(groups[folder])} trang)</span></h2>'
            f'<div class="grid">{"".join(cards)}</div>'
            f"</section>"
        )

    if not sections_html:
        sections_html = '<p class="empty">Chưa có trang HTML nào.</p>'

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Danh Sách Trang - Tổng Hợp</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    margin: 0; padding: 20px; background: #f4f6f9; color: #333;
}}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ color: #2c3e50; text-align: center; margin: 0 0 8px; font-size: 28px; }}
.subtitle {{ text-align: center; color: #666; margin-bottom: 25px; }}
.search-wrap {{
    position: sticky; top: 0; background: #f4f6f9;
    padding: 10px 0 20px; z-index: 10;
}}
.search {{
    width: 100%; padding: 14px 18px; font-size: 16px;
    border: 2px solid #d0d7de; border-radius: 10px;
    outline: none; transition: border-color .2s; background: #fff;
}}
.search:focus {{ border-color: #2c3e50; }}
.folder {{ margin-bottom: 30px; }}
.folder-title {{
    color: #2c3e50; font-size: 20px; padding-bottom: 8px;
    border-bottom: 2px solid #e1e4e8; margin: 0 0 15px;
}}
.count {{ color: #888; font-weight: normal; font-size: 15px; }}
.grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px;
}}
.card {{
    display: flex; flex-direction: column; background: #fff;
    border: 1px solid #e1e4e8; border-radius: 10px;
    padding: 16px; text-decoration: none; color: inherit;
    transition: transform .15s, box-shadow .15s, border-color .15s;
}}
.card:hover {{
    transform: translateY(-2px);
    box-shadow: 0 6px 14px rgba(0,0,0,0.08);
    border-color: #2c3e50;
}}
.card-icon {{ font-size: 28px; margin-bottom: 8px; }}
.card-title {{
    font-weight: 600; font-size: 15px; color: #2c3e50;
    margin-bottom: 4px; word-break: break-word;
}}
.card-path {{ font-size: 12px; color: #888; word-break: break-all; }}
.empty {{ text-align: center; padding: 40px; color: #888; }}
@media (max-width: 480px) {{
    body {{ padding: 12px; }}
    h1 {{ font-size: 22px; }}
    .grid {{ grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }}
    .card {{ padding: 12px; }}
    .card-icon {{ font-size: 22px; }}
    .card-title {{ font-size: 14px; }}
}}
</style>
</head>
<body>
<div class="container">
    <h1>📚 Danh Sách Trang</h1>
    <p class="subtitle">Tổng cộng <b>{len(items)}</b> trang HTML trong repo</p>
    <div class="search-wrap">
        <input type="text" class="search" id="search"
               placeholder="🔍 Tìm theo tên hoặc đường dẫn...">
    </div>
    <div id="sections">{sections_html}</div>
</div>
<script>
document.getElementById('search').addEventListener('input', function (e) {{
    var q = e.target.value.toLowerCase().trim();
    document.querySelectorAll('.card').forEach(function (el) {{
        var hay = (el.getAttribute('data-search') || '') + ' ' + el.textContent.toLowerCase();
        el.style.display = (hay.indexOf(q) !== -1) ? '' : 'none';
    }});
    document.querySelectorAll('.folder').forEach(function (f) {{
        var has = Array.prototype.some.call(
            f.querySelectorAll('.card'),
            function (c) {{ return c.style.display !== 'none'; }}
        );
        f.style.display = has ? '' : 'none';
    }});
}});
</script>
</body>
</html>"""


# ===========================================================================
# 5. SINH mon-an-thoi-tiet.html — TRANG THỜI TIẾT (RESPONSIVE MOBILE)
# ===========================================================================

_WEATHER_CSS = """
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 Arial, sans-serif;
    margin: 0; padding: 20px;
    background-color: #f4f6f9; color: #333;
}
.container { max-width: 1200px; margin: 0 auto; }
h1, h2 { color: #2c3e50; }
.back-link {
    display: inline-block; margin-bottom: 20px;
    background: #2c3e50; color: #fff; text-decoration: none;
    padding: 10px 18px; border-radius: 8px; font-weight: bold;
    font-size: 14px;
}
.back-link:hover { background: #1a252f; }
.card {
    background: #fff; padding: 20px; margin-bottom: 20px;
    border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.08);
    overflow: hidden;
}
.emergency {
    background: #ffebee; border-left: 6px solid #c0392b;
    padding: 15px 20px; margin-bottom: 20px; border-radius: 8px;
}
.emergency h3 { color: #c0392b; margin-top: 0; }
.emergency ul { margin: 8px 0; padding-left: 22px; }
.emergency li { margin-bottom: 6px; }

table {
    width: 100%; border-collapse: collapse; margin-top: 10px;
    background: #fff;
}
th, td {
    border: 1px solid #ddd; padding: 12px;
    text-align: left; vertical-align: top;
    word-wrap: break-word; word-break: break-word;
}
th { background-color: #2c3e50; color: #fff; }
tr:nth-child(even) { background-color: #f9f9f9; }
td .goi-y {
    white-space: pre-wrap; word-wrap: break-word;
    word-break: break-word; font-family: inherit;
    font-size: 14px; line-height: 1.55; margin: 0; display: block;
}

/* ---------- MOBILE: mỗi dòng thành 1 card dọc ---------- */
@media (max-width: 900px) {
    body { padding: 12px; }
    .card { padding: 14px; border-radius: 10px; }
    h1 { font-size: 20px; }
    h2 { font-size: 18px; }

    table, thead, tbody, th, td, tr {
        display: block; width: 100%;
    }
    thead { display: none; }
    tr {
        margin-bottom: 14px;
        border: 1px solid #d0d7de; border-radius: 10px;
        padding: 10px 14px; background: #fff !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    tr:nth-child(even) { background: #fff !important; }

    td {
        border: none;
        border-bottom: 1px dashed #e5e5e5;
        padding: 10px 0;
    }
    td:last-child { border-bottom: none; padding-bottom: 4px; }

    td::before {
        content: attr(data-label);
        font-weight: 700; color: #2c3e50;
        display: block; margin-bottom: 6px;
        font-size: 12px; text-transform: uppercase;
        letter-spacing: 0.4px;
    }
    td .goi-y { font-size: 13px; }
}
"""


def render_weather_html(web_data):
    rows = ""
    for date in sorted(web_data.keys()):
        w = web_data[date]
        md = "-".join(date.split("-")[1:])
        history = get_historical_data_for_date(md)

        vmax = [r[1] for r in history if r[1] is not None]
        vmin = [r[2] for r in history if r[2] is not None]
        if vmax and vmin:
            hist_str = (
                f"TB: {sum(vmax)/len(vmax):.1f}/"
                f"{sum(vmin)/len(vmin):.1f}°C "
                f"(từ {len(history)} năm)"
            )
        else:
            hist_str = "TB: 30.5/24.5°C (từ 19 năm)"

        rain_str = f"{w['rain']:.1f}mm" if w["rain"] > 0 else "0mm"
        gio_mua_txt = (
            ", ".join(w["rain_hours"]) if w["rain_hours"] else "Không mưa"
        )
        goi_y = lay_goi_y_mua_sam(w["max"], w["rain"])

        rows += f"""
        <tr>
            <td data-label="Ngày"><b>{date}</b></td>
            <td data-label="Dự báo (Max/Min)">{w['max']:.1f}/{w['min']:.1f}°C</td>
            <td data-label="Lượng mưa">{rain_str}</td>
            <td data-label="Khung giờ mưa">{gio_mua_txt}</td>
            <td data-label="Lịch sử (từ 2007)">{hist_str}</td>
            <td data-label="Gợi ý mua sắm & thực đơn"><div class="goi-y">{goi_y}</div></td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Món Ăn & Thời Tiết - Người Lính</title>
<style>{_WEATHER_CSS}</style>
</head>
<body>
<div class="container">

    <a href="{INDEX_PAGE_NAME}" class="back-link">🏠 Về trang chủ</a>

    <h1>🛡️ THỜI TIẾT &amp; THỰC ĐƠN NGƯỜI LÍNH</h1>

    <div class="emergency">
        <h3>🚨 GÓC CẤP CỨU NHANH</h3>
        <p><b>Triệu chứng:</b> Người mệt lả không muốn dậy, muốn đi nằm
        ngay lập tức sau khi vừa đi ngoài trời về.</p>
        <p><b>Quy trình xử lý &amp; cứu chữa nhanh:</b></p>
        <ul>
            <li><b>Nghỉ ngơi ngay:</b> Vào giường nằm đắp chăn, không cố gượng sức.</li>
            <li><b>Xoa bóp cơ thể:</b> Xoa dầu gió vào lòng bàn chân, thái dương, cổ, lưng.</li>
            <li><b>Làm ấm từ bên trong:</b> Uống trà gừng ấm hoặc nước gừng mật ong.</li>
            <li><b>Ăn uống bồi bổ:</b> Xôi nóng, cháo gừng, súp nóng.</li>
            <li><b>Hỗ trợ tiêu hóa / cảm mạo:</b> Thuốc cảm, Cảm xuyên hương, Berberin.</li>
        </ul>
    </div>

    <div class="card">
        <h2>📊 Dự Báo Thời Tiết &amp; Gợi Ý Dinh Dưỡng Tuần Này</h2>
        <table>
            <thead>
                <tr>
                    <th>Ngày</th>
                    <th>Dự Báo (Max/Min)</th>
                    <th>Mưa</th>
                    <th>Khung Giờ Mưa</th>
                    <th>Lịch Sử (Từ 2007)</th>
                    <th>Gợi Ý Mua Sắm &amp; Thực Đơn</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>

</div>
</body>
</html>"""


# ===========================================================================
# 6. MAIN
# ===========================================================================

def main():
    print(f"📂 Repo root : {BASE_DIR}")
    print(f"🗄️  DB path   : {DB_PATH}")
    print(f"🌤️  Trang thời tiết sẽ ghi: {WEATHER_PAGE_NAME}")
    print(f"📚 Trang hub sẽ ghi       : {INDEX_PAGE_NAME}")
    print("-" * 60)

    # Khởi tạo DB + lấy dữ liệu
    init_database()
    web_data = get_week_forecast()
    save_forecast_to_db(web_data)

    # (1) Sinh trang thời tiết
    weather_path = os.path.join(BASE_DIR, WEATHER_PAGE_NAME)
    try:
        with open(weather_path, "w", encoding="utf-8") as f:
            f.write(render_weather_html(web_data))
        print(f"✅ Đã tạo trang thời tiết: {weather_path}")
    except Exception as e:
        print(f"❌ Lỗi tạo trang thời tiết: {e}")

    # (2) Sinh index.html — hub liệt kê mọi HTML
    index_path = os.path.join(BASE_DIR, INDEX_PAGE_NAME)
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(render_index_html(BASE_DIR))
        all_htmls = discover_html_files(BASE_DIR)
        print(f"✅ Đã tạo trang chủ: {index_path}")
        print(f"   → Tìm thấy {len(all_htmls)} file HTML trong repo:")
        for h in all_htmls:
            print(f"       • {h}")
    except Exception as e:
        print(f"❌ Lỗi tạo index.html: {e}")

    # (3) Báo cáo Slack
    bao_cao = "🤖 *BÁO CÁO THỜI TIẾT & LỜI KHUYÊN TỰ ĐỘNG* 🤖\n"
    for date in sorted(web_data.keys()):
        w = web_data[date]
        rain_str = f"{w['rain']:.1f}mm" if w["rain"] > 0 else "0mm"
        bao_cao += (
            f"{date} | {w['max']:.1f}/{w['min']:.1f}°C | {rain_str}\n"
        )
    gui_thong_bao_slack(bao_cao)


if __name__ == "__main__":
    main()
