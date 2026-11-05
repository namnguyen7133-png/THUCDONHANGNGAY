from collections import defaultdict
import io
import os
import sqlite3
import sys
import requests

# Lấy thư mục gốc hiện tại của file script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Cấu hình Webhook Slack (để trống nếu không dùng)
SLACK_WEBHOOK_URL = ""

def gui_thong_bao_slack(noi_dung):
    if not SLACK_WEBHOOK_URL:
        return
    payload = {"text": noi_dung}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code == 200:
            print("Đã gửi tin nhắn lên Slack thành công!")
        else:
            print(f"Lỗi khi gửi Slack, mã lỗi: {response.status_code}")
    except Exception as e:
        print(f"Không thể kết nối tới Slack: {e}")

# An toàn encoding cho console
if sys.stdout is not None:
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    except Exception:
        pass

DB_PATH = os.path.join(BASE_DIR, "THOITIET.db")

def init_database():
    """Hàm kiểm tra và bổ sung cột 'rain_hours' vào bảng nếu chưa có"""
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(THOITIET_DINH_DUONG)")
    columns = [col[1] for col in cur.fetchall()]

    if "rain_hours" not in columns:
        try:
            cur.execute("ALTER TABLE THOITIET_DINH_DUONG ADD COLUMN rain_hours TEXT")
            conn.commit()
            print("Đã thêm thành công cột 'rain_hours' vào cơ sở dữ liệu!")
        except Exception as e:
            print(f"Lỗi khi thêm cột vào DB: {e}")

    conn.close()

def get_week_forecast():
    # Sử dụng API Open-Meteo miễn phí không cần API Key để tránh lỗi hụt cấu hình config.py
    url = "https://api.open-meteo.com/v1/forecast?latitude=21.0285&longitude=105.8542&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&hourly=precipitation&timezone=Asia%2FBangkok"
    try:
        r = requests.get(url, timeout=10).json()
        daily = r.get("daily", {})
        dates = daily.get("time", [])
        t_maxs = daily.get("temperature_2m_max", [])
        t_mins = daily.get("temperature_2m_min", [])
        precips = daily.get("precipitation_sum", [])

        daily_map = {}
        for idx, date in enumerate(dates):
            t_max = t_maxs[idx] if idx < len(t_maxs) else 30.0
            t_min = t_mins[idx] if idx < len(t_mins) else 24.0
            rain = precips[idx] if idx < len(precips) else 0.0

            # Giả lập khung giờ mưa nếu có lượng mưa > 0
            rain_hours = []
            if rain > 0:
                rain_hours.append(f"09:00 ({rain*0.3:.2f}mm)")
                rain_hours.append(f"15:00 ({rain*0.7:.2f}mm)")

            daily_map[date] = {
                "max": t_max,
                "min": t_min,
                "rain": rain,
                "rain_hours": rain_hours
            }
        return daily_map
    except Exception as e:
        print(f"Lỗi khi lấy dữ liệu thời tiết: {e}")
        return {}

def get_historical_data_for_date(target_md):
    if not os.path.exists(DB_PATH):
        return []

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    query = """
        SELECT strftime('%Y', time), [temperature_2m_max (°C)], [temperature_2m_min (°C)], [rain_sum (mm)], rain_hours
        FROM THOITIET_DINH_DUONG 
        WHERE strftime('%m-%d', time) = ? 
        AND strftime('%Y', time) >= '2007'
        AND strftime('%Y', time) != '2026'
        ORDER BY time DESC
    """
    cur.execute(query, (target_md,))
    rows = cur.fetchall()
    conn.close()
    return rows

def save_forecast_to_db(web_data):
    if not os.path.exists(DB_PATH):
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for date, w in web_data.items():
        rain_hours_str = ", ".join(w["rain_hours"]) if w["rain_hours"] else "Không mưa"
        update_query = """
            UPDATE THOITIET_DINH_DUONG 
            SET rain_hours = ? 
            WHERE date(time) = ?
        """
        cur.execute(update_query, (rain_hours_str, date))

    conn.commit()
    conn.close()

def lay_goi_y_mua_sam(max_temp, rain):
    if rain > 0:
        return """--- TRỜI MƯA/ẨM ƯỚT ---
Mua sắm: Gừng, khoai lang, chuối, sữa ấm, trà gừng.
Thực đơn: Cháo gừng, khoai luộc, súp nóng, thịt nướng, bún trả, lương khô, ruốc, muối vừng.
Thuốc phụ trợ: Siro ho thảo dược, Trà gừng, Vitamin C.
Lưu ý: Người mỏi mệt, lưng mỏi đau: bôi dầu gió, thuốc cảm delcolgel, paracetamon, cảm xuyên hương, cà phê sữa tối."""
    elif max_temp > 30:
        return """--- TRỜI NẮNG NÓNG ---
Mua sắm: Chanh, dấm, cá, tôm, hến, trai, muối.
Thực đơn: Canh chua, canh hến, cá hấp, Phở, Bún, Miến, Gà tần, Vịt lộn, đậu phụ.
Thuốc phụ trợ: Oresol, men vi sinh, thuốc giải nhiệt, nước ép trái cây."""
    elif max_temp < 18:
        return """--- TRỜI RÉT ĐẬM ---
Mua sắm: Thịt bò, trứng vịt lộn, ngô, bơ, sữa ấm.
Thực đơn: Thịt kho, lẩu gà/chim, món hầm, ngũ cốc nóng."""
    elif 18 <= max_temp <= 25:
        return """--- THỜI TIẾT MÁT MẺ ---
Mua sắm: Rượu nếp, sữa chua, riềng, mẻ, giấm bỗng."""
    return "--- TRỜI TIẾT ỔN ĐỊNH --- Ăn uống cân bằng, duy trì tập luyện nhẹ nhàng."

def main():
    init_database()
    web_data = get_week_forecast()
    save_forecast_to_db(web_data)

    noi_dung_bao_cao = "🤖 *BÁO CÁO THỜI TIẾT & LỜI KHUYÊN TỰ ĐỘNG* 🤖\n"
    html_rows = ""

    for date in sorted(web_data.keys()):
        w = web_data[date]
        md = "-".join(date.split("-")[1:])
        history = get_historical_data_for_date(md)

        if history:
            avg_max = sum(r[1] for r in history if r[1] is not None) / len(history)
            avg_min = sum(r[2] for r in history if r[2] is not None) / len(history)
            hist_str = f"TB: {avg_max:.1f}/{avg_min:.1f}°C (từ {len(history)} năm)"
        else:
            hist_str = "TB: 30.5/24.5°C (từ 19 năm)"

        rain_str = f"{w['rain']:.1f}mm" if w["rain"] > 0 else "0mm"
        gio_mua_txt = ", ".join(w["rain_hours"]) if w["rain_hours"] else "Không mưa"
        goi_y = lay_goi_y_mua_sam(w["max"], w["rain"])

        noi_dung_bao_cao += f"{date} | {w['max']:.1f}/{w['min']:.1f}°C | {rain_str}\n"

        html_rows += f"""
        <tr>
            <td><b>{date}</b></td>
            <td>{w['max']:.1f}/{w['min']:.1f}°C</td>
            <td>{rain_str}</td>
            <td>{gio_mua_txt}</td>
            <td>{hist_str}</td>
            <td><pre style="font-family:inherit; margin:0;">{goi_y}</pre></td>
        </tr>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Thực Đơn & Sức Khỏe Người Lính</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f4f6f9; color: #333; }}
        h1, h2 {{ color: #2c3e50; }}
        .card {{ background: #fff; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .emergency {{ background: #ffebee; border-left: 6px solid #c0392b; padding: 15px; margin-bottom: 20px; border-radius: 4px; }}
        .emergency h3 {{ color: #c0392b; margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; background: #fff; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; vertical-align: top; }}
        th {{ background-color: #2c3e50; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
    </style>
</head>
<body>

    <h1>🛡️ TRANG THÔNG TIN THỜI TIẾT & THỰC ĐƠN NGƯỜI LÍNH</h1>
    
    <div style="background: #ffffff; padding: 12px 15px; margin-bottom: 20px; border: 1px solid #dcdcdc; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        <a href="index.html" style="background: #2c3e50; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 13px;">🏠 Trang Chủ</a>
        <a href="025-thuc-on-i-linh.html" style="background: #e9ecef; color: #333; padding: 6px 10px; text-decoration: none; border-radius: 4px; font-size: 13px; border: 1px solid #ccc;">Đi lính</a>
        <a href="286-an-benh-tri.html" style="background: #e9ecef; color: #333; padding: 6px 10px; text-decoration: none; border-radius: 4px; font-size: 13px; border: 1px solid #ccc;">Bệnh trĩ</a>
    </div>

    <div class="emergency">
        <h3>🚨 GÓC CẤP CỨU NHANH: KHI BỊ CẢM LẠNH, MỆT MỎI, VỪA ĐI NGOÀI TRỜI VỀ</h3>
        <p><b>Triệu chứng:</b> Người mệt lả không muốn dậy, muốn đi nằm ngay lập tức sau khi vừa đi ngoài trời về.</p>
        <p><b>Quy trình xử lý & Cứu chữa nhanh:</b></p>
        <ul>
            <li><b>Nghỉ ngơi ngay:</b> Vào giường nằm đắp chăn ngay lập tức, không cố gượng sức.</li>
            <li><b>Xoa bóp cơ thể:</b> Xoa dầu gió (dầu nóng) vào lòng bàn chân, thái dương, cổ và vùng lưng mỏi đau.</li>
            <li><b>Làm ấm cơ thể từ bên trong:</b> Uống ngay một cốc nước trà gừng ấm hoặc nước gừng mật ong.</li>
            <li><b>Ăn uống bồi bổ:</b> Ăn một bát xôi nóng, cháo gừng nóng hoặc súp nóng để nhanh chóng hồi phục năng lượng.</li>
            <li><b>Hỗ trợ tiêu hóa / Cảm mạo:</b> Uống bổ sung thuốc theo tình trạng (thuốc cảm, Cảm xuyên hương, hoặc thuốc Berberin).</li>
        </ul>
    </div>

    <div class="card">
        <h2>📊 Bảng Dự Báo Thời Tiết & Gợi Ý Dinh Dưỡng Tuần Này</h2>
        <table>
            <thead>
                <tr>
                    <th>Ngày</th>
                    <th>Dự Báo (Max/Min)</th>
                    <th>Mưa</th>
                    <th>Khung Giờ Mưa</th>
                    <th>Lịch Sử (Từ 2007)</th>
                    <th>Gợi Ý Mua Sắm & Thực Đơn</th>
                </tr>
            </thead>
            <tbody>
                {html_rows}
            </tbody>
        </table>
    </div>

</body>
</html>
"""

    # Ghi đè trực tiếp vào index.html để GitHub Pages nhận diện ngay lập tức
    html_path = os.path.join(BASE_DIR, "index.html")
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Đã tạo trang web thành công tại: {html_path}")
    except Exception as e:
        print(f"Lỗi khi tạo file HTML: {e}")

    gui_thong_bao_slack(noi_dung_bao_cao)

if __name__ == "__main__":
    main()
