# LỆNH PHA 4 — SHOWCASE EVIDENCE PACK (Máy B · AI20K-162)

**Phát sẵn để chạy NGAY sau khi P2.6 kết thúc (PASS hoặc fail-có-nhãn F4) — không chờ round-trip.**
**Mốc:** SHA cuối của P2.6 · **Timebox:** 4h · **Mục tiêu:** tối đa điểm showcase cho chủ đề 162 (agent LLM planning tiếng Việt, auditable) bằng số thật + bằng chứng tự phản chứng được.
**Thứ tự ưu tiên nếu thiếu giờ: P4.1 → P4.2 → P4.4 → P4.3 → P4.5.** Mỗi mục có gate + raw như mọi khi.

## P4.1 — EVAL FINAL hai bảng (≈60')

**(a) Bảng C Gazebo final:** `LLM_PROVIDER=ollama python3 eval/run_eval_gazebo.py` với trạng thái sau P2.6, n=3 task chuẩn. Oracle độc lập + Nav² + pallet GT. Regenerate `eval/results/report_v2.md` với **bộ nhãn cố định in ngay dưới tiêu đề bảng**:
`(model: ollama qwen2.5:7b ≠ Gemini official · GT-servo dock · pallet 2kg sim-simplified · vx≤0.25 carry · map rebaked lidar-0.625 [· AMCL GT-reinit nếu F4 bật])`

**(b) Bảng A-ext Flat2D (n≥10):** mở rộng bộ task tiếng Việt trong file task RIÊNG `eval/tasks_aext.json` (đặt tên "Bảng A-ext (repo Máy B)" — KHÔNG mạo danh Bảng A official Máy A). Task đa dạng: pick-drop đơn, multi-step, lệnh có tham chiếu gián tiếp ("kệ gần cửa"), lệnh thiếu thông tin (agent phải hỏi/locate trước). 

**CHỐNG CHERRY-PICK (bắt buộc):** commit `tasks_aext.json` + seed TRƯỚC, thành commit riêng, RỒI mới chạy eval và commit kết quả ở commit sau. Hai SHA tách bạch = pre-registration. Máy A sẽ check thứ tự commit.

**GATE G4.1:** raw stdout cả 2 eval + report_v2.md + 2 SHA (pre-reg / results). Số fail cứ để fail trong bảng — bảng có cột ✗ là bảng đáng tin.

## P4.2 — ABLATION: chứng minh planning LLM có giá trị đo được (≈60')

Đây là mảnh trực tiếp trả lời "plan của agent hoạt động không". Hai arm, cùng `tasks_aext.json`, cùng seed, trên Flat2D:

- **Arm A — agent LLM đầy đủ** (ollama qwen2.5:7b): số lấy từ P4.1(b), không chạy lại.
- **Arm B — scripted-naive baseline** (viết mới `eval/ablation_baseline.py`, ~80 dòng): parser keyword tìm tên vật + tên đích trong lệnh → gọi cứng `locate → move_to → pick → move_to → drop`, không reasoning, không retry, không hỏi lại. Định nghĩa này CHỐT — không chỉnh baseline sau khi thấy số.

Metric: success rate (oracle), số bước, số task hỏng vì hiểu sai lệnh. Xuất `eval/results/ablation.md`: bảng 2 arm + chênh lệch.

**GATE G4.2:** raw cả 2 arm. Kết quả NÀO cũng có giá trị: LLM >> baseline = planning có đóng góp đo được; LLM ≈ baseline = khai thật + 1 đoạn phân tích vì sao (task quá đơn giản?) — cấm im lặng.

## P4.3 — DEMO ARTIFACT (≈45')

**(a) Demo runbook** `docs/DEMO_RUNBOOK.md` (commit): kịch bản 90 giây, từng lệnh paste-được, thời lượng từng cảnh, màn hình gì đang hiện:
1. (0–15s) `start_demo.sh` → "Full stack ready in Ns (warm)" + Foxglove kết nối.
2. (15–45s) Terminal agent: 1 lệnh tiếng Việt thật → log tool-calls hiện từng bước plan.
3. (45–75s) Foxglove: robot chạy tới goal + fork nâng pallet (các mảnh đã PASS; nếu G2.3R-final PASS → full e2e).
4. (75–90s) `oracle_check()` output + mở trace JSONL: "số này các bạn tự tính lại được".

**(b) Quay video:** nếu có DISPLAY → `ffmpeg -f x11grab` quay theo runbook; headless → runbook là deliverable, Thái quay tay theo nó. Video KHÔNG commit vào repo (public, nặng) — để local, repo chỉ chứa runbook + ghi chú đường dẫn.

**QUY TẮC CỨNG:** nếu e2e chưa PASS sạch, video là CÁC PHÂN ĐOẠN có caption "segment" — CẤM cắt ghép tạo cảm giác một lần chạy liền mạch. Một frame giả phá toàn bộ câu chuyện auditable.

**GATE G4.3:** runbook commit + (video file local có timestamp HOẶC ghi rõ "headless — chờ Thái quay").

## P4.4 — EVIDENCE INDEX `docs/EVIDENCE.md` (≈45') — trang giám khảo đọc đầu tiên

Bảng mỗi dòng một claim:

```
| Claim | Số | Nhãn điều kiện | Bằng chứng (commit/file) | Lệnh tự chạy lại |
```

Tối thiểu 12 dòng: stack 8s warm · /odom clone sạch (P0) · SDF fix + push test 0.4556 (P1) · odom-vs-GT 5.7e-7 · Nav2 goal GT 0.103m · pick z+0.16 d_robot 0.45 · carry trace · AMCL diverge 2.9m (số xấu CŨNG vào index) · map rebake · Bảng C final · Bảng A-ext · ablation · parity 72.7%.

**+ Failure Ledger** (cuối file): 5 bug lớn đã tự bắt — oracle tautology 3/3 giả · SDF≠URDF link poses · vacuous carry-pass · map-height mismatch · reverse-block do cmd_vel tranh chấp. Mỗi bug 2 dòng: triệu chứng → cách bắt → commit fix. Frame đúng chủ đề: *đây là biên lai của auditable agent — hệ thống chấm đã nhiều lần đánh trượt chính chúng tôi*.

**GATE G4.4:** file commit; Máy A sẽ chạy thử ngẫu nhiên 2 "lệnh tự chạy lại" trong bảng — lệnh nào không chạy được là FAIL gate.

## P4.5 — PITCH UPDATE (≈30')

`pitch/slide_sim_real.md`: cập nhật trạng thái cuối + mục **Q&A khó** (mỗi câu 2 dòng, có số):
- "GT-servo docking có phải cheat?" → perception là Pha 3 chưa làm, docking dùng GT có nhãn; oracle KHÔNG dùng GT-servo, đo độc lập.
- "Sao pallet 2kg?" → DART contact-island freeze ở 8kg, disclose; hình học fork-channel thật.
- "Sao không SLAM từ đầu?" → map kế thừa từ mốc TB3; bug chỉ lộ khi lidar dời 0.625 — failure ledger dòng 4.
- "Ollama khác gì bản chấm?" → model nhãn rõ trên mọi bảng; Gemini official chạy track Máy A.
- "3/3 nghĩa là gì?" → luôn kèm nhãn điều kiện, xem EVIDENCE.md.

**GATE G4.5:** diff pitch + KEY-SCAN + push.

## KHÔNG LÀM (đỡ tốn giờ + đỡ rủi ro)

- KHÔNG chạy lại Pha 3 perception (ARMBench) — ngoài phạm vi điểm còn lại, DISCLOSURE_armbench.md đã có.
- KHÔNG sửa baseline/task sau khi thấy số (pre-reg đã chốt).
- KHÔNG commit video/binary lớn. KHÔNG đụng repo BTC. KEY-SCAN mọi commit.

## BÁO CÁO VỀ

Bảng gate G4.1→G4.5 + 2 SHA pre-reg/results + SHA cuối + deviations + RAW (stdout 2 eval, bảng ablation, 2 lệnh tự-chạy-lại đã test). Máy A sẽ: tải report/ablation/EVIDENCE, tự tính lại từ traces, check thứ tự commit pre-registration.