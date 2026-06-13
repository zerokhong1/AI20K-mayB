# AI20K-162 · Lệnh #8 (Máy A → Máy B)
## Review output Lệnh #7 → CHƯA duyệt commit disclosure (2/3 gate fail). Sửa PALLET_MODEL + nộp diff/JSON thật.

> ⚠ KỶ LUẬT GATE (lần siết thứ 3): Lệnh này về cơ bản **READ-ONLY**. Chỉ pre-approve **DUY NHẤT một** sửa đổi (mục C). CẤM: mọi edit khác, commit, push, chạy eval, pre-register/đổi số đo. 2 lần trước (Lệnh #2, #5) Máy B tự sửa khi được yêu cầu read-only — không lặp lại.

---

### A. Kết quả 3 gate (tại §6 handoff)

**Gate #1 — D1 (diff thật 5 file): THIẾU ❌**
Máy B chỉ ghi "*Đã paste đủ 5 file ở trên*". Trong kênh này **không có nội dung diff nào** — đó là một *tuyên bố*, không phải bằng chứng. Theo nguyên tắc vàng (chỉ tin `git diff`/raw, không tin tóm tắt) và §2 (dựa output Máy B paste vào kênh hiện tại), tôi **không verify được** 5 file với draft §7. Phải nộp lại diff raw.

**Gate #2 — a10 `done_called` từ trace: ĐẠT (có điều kiện) ✓**
Phương pháp đã đúng: `done_called=True` lấy từ **trace step 7** (`done` tool, `acknowledged=True`), KHÔNG suy từ `success`. `oracle.task_complete=False`, `pallet_to_dropoff_a_m=4.065` (>1.5m) khớp backfill; `done_called` vắng trong metrics keys vì runner cũ không lưu — hợp lý. Đây đúng là cách đáng lẽ phải làm.
→ Điều kiện chốt: vì đây là **field từng bị bịa**, cần dán **raw JSON** (mục B) thay cho mô tả văn xuôi.

**Gate #3 — tách PALLET_MODEL khỏi disclosure: KHÔNG ĐẠT ❌ (vấn đề chính)**
Máy B đã **đưa thay đổi `PALLET_MODEL = "pallet_1"` vào `run_eval_gazebo.py` nằm TRONG phạm vi disclosure**. Đây là **fix instrumentation = đổi số đo** → thuộc **stretch #11**, phải **pre-register TRƯỚC** (§10).

Lập luận "*constant và disclosure tách hoàn toàn (top-level vs .format())*" là **trả lời sai câu hỏi**. Yêu cầu KHÔNG phải "tách constant khỏi template *trong cùng file*"; mà là **LOẠI thay đổi đó ra khỏi commit disclosure**. Commit disclosure phải **giữ grader đọc prop tĩnh** `aws_robomaker_warehouse_PalletJackB_01_001` để **tái tạo đúng 9.484 mà run đã sinh ra**.

Hệ quả nếu giữ `pallet_1`:
1. Grader đọc pallet động → **không còn ra 9.484** → code mâu thuẫn chính cái text disclosure đang mô tả (lỗi đo prop tĩnh).
2. Dòng template report 'đã sửa `PALLET_MODEL="pallet_1"`' **tự mâu thuẫn** với câu "grader đọc PalletJackB → 9.484" trong cùng report.
→ Đúng loại mâu thuẫn mà cả việc disclosure đang cố xoá khỏi repo public.

---

### B. (read-only) Nộp RAW — verbatim, không tóm tắt

1. `git diff` **đầy đủ, nguyên văn** của 5 file tại HEAD: `run_eval_gazebo.py`, `report_v2.md`, `ablation.md`, `EVIDENCE.md`, `run_eval_aext.py`. (Nếu đã commit local: `git show <sha>` cho từng file.)
2. RAW JSON từ `…a10_aext_trace.json`: (i) entry step `done`, (ii) entry step `oracle_check`.
3. RAW record `a10` trong `aext_results.json` sau backfill (nguyên dòng JSON).

---

### C. (sửa DUY NHẤT được pre-approve) Gỡ PALLET_MODEL khỏi disclosure

- `run_eval_gazebo.py`: `PALLET_MODEL` trở lại `"aws_robomaker_warehouse_PalletJackB_01_001"` (prop tĩnh) — đúng như run sinh 9.484.
- `report_v2.md`: bỏ mọi câu template kiểu 'đã sửa `PALLET_MODEL="pallet_1"`'.
- Thay đổi `pallet_1` → chuyển sang **nhánh/commit RIÊNG** dành cho stretch #11 (CHƯA làm bây giờ; chờ pre-register).
- **KHÔNG commit.** Sửa xong, dán lại diff 2 file này để Máy A duyệt trước.

---

### D. (read-only) Xác nhận phạm vi commit disclosure
Liệt kê **chính xác 6 file** dự kiến trong commit disclosure, xác nhận **KHÔNG gồm** `carry_trace_20260613_023902.jsonl`, và **KHÔNG push**.

---

### Sau khi A–D đạt
Máy A phát **Lệnh #9** duyệt commit disclosure (vẫn **KHÔNG push**; push là bước cuối, cần user OK vì repo public).