from collections import defaultdict
import io
import os
import sqlite3
import sys
import webbrowser
import requests
from config import API_KEY

# Cấu hình Webhook Slack của bạn
SLACK_WEBHOOK_URL = (
    ""
)


def gui_thong_bao_slack(noi_dung):
  payload = {"text": noi_dung}
  try:
    response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
    if response.status_code == 200:
      print("Đã gửi tin nhắn lên Slack thành công!")
    else:
      print(f"Lỗi khi gửi Slack, mã lỗi: {response.status_code}")
  except Exception as e:
    print(f"Không thể kết nối tới Slack: {e}")


# Cấu hình đường dẫn module log trên ổ E
sys.path.append(r"E:\QUAN_LY_DU_AN")
try:
  from nhat_ky_trung_tam import tu_dong_ghi_log
except ImportError:

  def tu_dong_ghi_log(func):
    return func


# Cấu hình encoding để hiển thị tiếng Việt
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
DB_PATH = r"E:\NHACVIEC_PYTHON\THOITIET.db"


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
      print("Đã thêm thành công cột 'rain_hours' vào cơ sở dữ liệu trên ổ E!")
    except Exception as e:
      print(f"Lỗi khi thêm cột vào DB: {e}")

  conn.close()


def get_week_forecast():
  url = f"https://api.openweathermap.org/data/2.5/forecast?q=Hanoi&appid={API_KEY}&units=metric&lang=vi"
  try:
    r = requests.get(url, timeout=10).json()
    daily_map = defaultdict(
        lambda: {"min": 100, "max": -100, "rain": 0, "rain_hours": []}
    )
    for item in r["list"]:
      dt_parts = item["dt_txt"].split(" ")
      date = dt_parts[0]
      time_str = dt_parts[1][:5]  # Lấy định dạng HH:MM

      daily_map[date]["min"] = min(
          daily_map[date]["min"], item["main"]["temp_min"]
      )
      daily_map[date]["max"] = max(
          daily_map[date]["max"], item["main"]["temp_max"]
      )

      rain_3h = item.get("rain", {}).get("3h", 0)
      if rain_3h > 0:
        daily_map[date]["rain"] += rain_3h
        daily_map[date]["rain_hours"].append(f"{time_str} ({rain_3h}mm)")

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
  """Lưu thông tin dự báo kèm giờ mưa vào database trên ổ E"""
  if not os.path.exists(DB_PATH):
    return

  conn = sqlite3.connect(DB_PATH)
  cur = conn.cursor()

  for date, w in web_data.items():
    rain_hours_str = (
        ", ".join(w["rain_hours"]) if w["rain_hours"] else "Không mưa"
    )

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


@tu_dong_ghi_log
def main():
  init_database()
  web_data = get_week_forecast()
  save_forecast_to_db(web_data)

  noi_dung_bao_cao = "🤖 *BÁO CÁO THỜI TIẾT & LỜI KHUYÊN TỰ ĐỘNG* 🤖\n"
  html_rows = ""

  print(
      f"{'NGÀY':<12} | {'DỰ BÁO':<10} | {'MƯA':<6} |"
      f" {'LỊCH SỬ TỪ 2007 (TRUNG BÌNH)'}"
  )
  print("-" * 120)

  noi_dung_bao_cao += (
      "NGÀY         | DỰ BÁO     | MƯA    | LỊCH SỬ TỪ 2007 (TRUNG BÌNH)\n"
      + "-" * 80
      + "\n"
  )

  for date in sorted(web_data.keys()):
    w = web_data[date]
    md = "-".join(date.split("-")[1:])
    history = get_historical_data_for_date(md)

    if history:
      avg_max = sum(r[1] for r in history if r[1] is not None) / len(history)
      avg_min = sum(r[2] for r in history if r[2] is not None) / len(history)
      hist_str = f"TB: {avg_max:.1f}/{avg_min:.1f}°C (từ {len(history)} năm)"
    else:
      hist_str = "Chưa có dữ liệu"

    rain_str = f"{w['rain']:.1f}mm" if w["rain"] > 0 else "0mm"
    gio_mua_txt = (
        ", ".join(w["rain_hours"])
        if w["rain_hours"]
        else "Không có dự báo mưa trong ngày"
    )
    goi_y = lay_goi_y_mua_sam(w["max"], w["rain"])

    print(f"{date:<12} | {w['max']:.1f}/{w['min']:.1f}°C | {rain_str:<6} | {hist_str}")
    noi_dung_bao_cao += f"{date:<12} | {w['max']:.1f}/{w['min']:.1f}°C | {rain_str:<6} | {hist_str}\n"
    print(f"--> [WEB] Khung giờ mưa: {gio_mua_txt}")
    noi_dung_bao_cao += f"--> [WEB] Khung giờ mưa: {gio_mua_txt}\n"
    print(f"--> {goi_y}")
    noi_dung_bao_cao += f"--> Gợi ý: {goi_y}\n"
    print("-" * 120)
    noi_dung_bao_cao += "-" * 80 + "\n"

    # Gom dữ liệu để đổ vào bảng HTML
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

  # Lưu kết quả ra tệp .txt trên Desktop
  desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
  txt_path = os.path.join(desktop_path, "ket_qua_moi_nhat.txt")
  try:
    with open(txt_path, "w", encoding="utf-8") as f:
      f.write(noi_dung_bao_cao)
    print(f"Đã lưu kết quả ra tệp txt tại: {txt_path}")
  except Exception as e:
    print(f"Lỗi khi lưu tệp txt: {e}")

  # Tạo trang web thuc_don_nguoi_linh.html tích hợp menu chuẩn xác
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
    
    <!-- Thanh Menu Điều Hướng Chuẩn Xác -->
    <div style="background: #ffffff; padding: 12px 15px; margin-bottom: 20px; border: 1px solid #dcdcdc; border-radius: 8px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
        
        <!-- Nút về trang chủ -->
        <a href="file:///E:/HTML/github_data/index.html" style="background: #2c3e50; color: white; padding: 6px 12px; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 13px;">🏠 Trang Chủ</a>
        
        <!-- Các nút truy cập nhanh quan trọng -->
        <a href="file:///E:/HTML/github_data/025-thuc-on-i-linh.html" style="background: #e9ecef; color: #333; padding: 6px 10px; text-decoration: none; border-radius: 4px; font-size: 13px; border: 1px solid #ccc;">Đi lính</a>
        <a href="file:///E:/HTML/github_data/286-an-benh-tri.html" style="background: #e9ecef; color: #333; padding: 6px 10px; text-decoration: none; border-radius: 4px; font-size: 13px; border: 1px solid #ccc;">Bệnh trĩ</a>

        <span style="color: #ccc;">|</span>
        
        <!-- Menu thả xuống chứa toàn bộ các file chuyên đề khác -->
        <select onchange="if(this.value) window.location.href=this.value;" style="padding: 6px 10px; border-radius: 4px; border: 1px solid #ccc; font-size: 13px; background: #f8f9fa; cursor: pointer;">
            <option value="">📁 Kho Thực Đơn & Chuyên Đề Khác...</option>
            <option value="file:///E:/HTML/github_data/029-thuc-on-cho-oi-truong.html">Thực đơn Đại đội trưởng</option>
            <option value="file:///E:/HTML/github_data/030-thuc-on-cho-phi-cong.html">Thực đơn Phi công</option>
            <option value="file:///E:/HTML/github_data/031-thuc-on-xe-may.html">Thực đơn Xe máy</option>
            <option value="file:///E:/HTML/github_data/032-thuc-on-lai-tau-cano.html">Thực đơn Lái tàu - Cano</option>
            <option value="file:///E:/HTML/github_data/033-thuc-on-cho-lai-xe-o-to.html">Thực đơn Lái xe ô tô</option>
            <option value="file:///E:/HTML/github_data/034-thuc-on-xem-chieu.html">Thực đơn Xem chiều</option>
            <option value="file:///E:/HTML/github_data/291-chay-cho-an-uong.html">Chạy chợ ăn uống</option>
            <option value="file:///E:/HTML/github_data/293-24-tiet-khi.html">24 Tiết khí</option>
            <option value="file:///E:/HTML/github_data/297-tiet-khi-mon-an.html">Tiết khí & Món ăn</option>
            <option value="file:///E:/HTML/github_data/288-an-uong-am-lich.html">Ăn uống Âm lịch</option>
        </select>
    </div>

    <!-- Mục xử lý khẩn cấp khi bị cảm lạnh / vừa đi ngoài trời về mệt mỏi -->
    <div class="emergency">
        <h3>🚨 GÓC CẤP CỨU NHANH: KHI BỊ CẢM LẠNH, MỆT MỎI, VỪA ĐI NGOÀI TRỜI VỀ</h3>
        <p><b>Triệu chứng:</b> Người mệt lả không muốn dậy, muốn đi nằm ngay lập tức sau khi vừa đi ngoài trời về.</p>
        <p><b>Quy trình xử lý & Cứu chữa nhanh:</b></p>
        <ul>
            <li><b>Nghỉ ngơi ngay:</b> Vào giường nằm đắp chăn ngay lập tức, không cố gượng sức.</li>
            <li><b>Xoa bóp cơ thể:</b> Xoa dầu gió (dầu nóng) vào lòng bàn chân, thái dương, cổ và vùng lưng mỏi đau.</li>
            <li><b>Làm ấm cơ thể từ bên trong:</b> Uống ngay một cốc nước trà gừng ấm hoặc nước gừng mật ong.</li>
            <li><b>Ăn uống bồi bổ:</b> Ăn một bát xôi nóng, cháo gừng nóng hoặc súp nóng để nhanh chóng hồi phục năng lượng.</li>
            <li><b>Hỗ trợ tiêu hóa / Cảm mạo:</b> Uống bổ sung thuốc theo tình trạng (ví dụ: thuốc cảm, Cảm xuyên hương, hoặc thuốc Beberin nếu có vấn đề về tiêu hóa).</li>
        </ul>
    </div>

    <!-- Bảng dự báo thời tiết và gợi ý tự động -->
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

  html_path = os.path.join(desktop_path, "thuc_don_nguoi_linh.html")
  try:
    with open(html_path, "w", encoding="utf-8") as f:
      f.write(html_content)
    print(f"Đã tạo trang web thành công tại: {html_path}")
    
    # Tự động mở file HTML trực tiếp trên trình duyệt web mặc định
    webbrowser.open(f"file:///{html_path}")
  except Exception as e:
    print(f"Lỗi khi tạo hoặc mở file HTML: {e}")

  # Gửi lên Slack
  gui_thong_bao_slack(noi_dung_bao_cao)


if __name__ == "__main__":
  main()