# LỆNH PHA 0 — SELF-CONTAIN REPO (Máy B · AI20K-162)

**Từ:** Máy A (điều phối/review) · **Mốc xuất phát:** `2ae195b` (Máy A đã verify HEAD trên GitHub lúc soạn lệnh)
**Timebox:** 90 phút. Quá box → commit trạng thái + báo honest-partial. KHÔNG đụng Pha 1 (nav physics) trong phiên này.
**DoD Pha 0:** clone sạch repo (không dính ~/colcon_ws) → `colcon build` 0 fail → `start_demo.sh` báo `/odom present`. Mọi gate phải kèm RAW OUTPUT — báo cáo không kèm raw = trả lại.

## FACTS Máy A đã verify trên repo (đỡ phải dò lại)

- `warehouse_nav` **ĐÃ nằm ở** `colcon_ws/src/warehouse_nav` trong repo (commit 2d920d1). KHÔNG cần git mv nữa — việc còn lại là đồng bộ + trỏ lại start_demo.sh.
- `start_demo.sh` hiện source `$HOME/colcon_ws` (NAV_WS) + `$HOME/AI20K/colcon_ws` (AGENT_WS), và gọi `$NAV_WS/kill_ros.sh` — **kill_ros.sh không có trong repo**.
- `warehouse_sim.launch.py` hard-require qua `get_package_share_directory`: `aws_robomaker_small_warehouse_world` (world + map `maps/005/map.yaml`), `nav2_minimal_tb3_sim` (models + urdf TB3 — file đọc urdf này *vô điều kiện*, kể cả robot_type:=forklift), `nav2_bringup`, `warehouse_nav`.
- `.gitignore` đang ignore `colcon_ws/src/aws-robomaker-small-warehouse-world` với ghi chú "track as submodule separately" — **nhưng repo KHÔNG có .gitmodules** → clone sạch hiện tại CHẮC CHẮN fail. Đây là lỗ hổng chính Pha 0 phải bịt.
- `.gitignore` đã cover `colcon_ws/{build,install,log}` ✓.

---

## B0.0 — Baseline + đồng bộ (KHÔNG sửa gì ở bước này)

```bash
cd ~/AI20K && git rev-parse --short HEAD && git status --porcelain
ls ~/colcon_ws/src/
# Bản live ~/colcon_ws có drift so với bản đã copy vào repo không?
diff -ru --brief ~/colcon_ws/src/warehouse_nav ~/AI20K/colcon_ws/src/warehouse_nav
ls -la ~/colcon_ws/kill_ros.sh && cat ~/colcon_ws/kill_ros.sh
```

**GATE G0.0** (paste raw cả 4 lệnh): HEAD = 2ae195b, working tree sạch (nếu bẩn: DỪNG, báo về, không tự commit dọn). Nếu diff ≠ rỗng → đồng bộ bản MỚI HƠN vào repo (xem mtime/nội dung để xác định chiều), ghi rõ file nào sync chiều nào.

## B0.1 — Audit dependency: cái gì đang resolve từ ~/colcon_ws?

Chạy trong shell ĐANG source ~/colcon_ws như mọi khi:

```bash
for p in aws_robomaker_small_warehouse_world nav2_minimal_tb3_sim nav2_bringup ros_gz_sim ros_gz_bridge foxglove_bridge; do
  echo "== $p"; ros2 pkg prefix $p 2>&1
done
```

**GATE G0.1** (paste raw): phân loại từng package → `(a) /opt/ros/...` = system dep, chỉ cần ghi README; `(b) ~/colcon_ws/install/...` = PHẢI đưa vào repo ở B0.2. Dự đoán của Máy A: aws world chắc chắn (b); nav2_minimal_tb3_sim cần kiểm chứng.

## B0.2 — Self-contain (fix nhỏ nhất, theo kết quả B0.1)

**(a) Mỗi package loại (b):** nếu source của nó trong `~/colcon_ws/src/<pkg>` là git repo **sạch so với upstream** → add submodule pin đúng commit; nếu có sửa local → vendor thẳng (bỏ dòng ignore, commit files) + ghi chú đã sửa gì:

```bash
cd ~/AI20K
git -C ~/colcon_ws/src/aws-robomaker-small-warehouse-world status --porcelain  # sạch?
git -C ~/colcon_ws/src/aws-robomaker-small-warehouse-world remote get-url origin && git -C ~/colcon_ws/src/aws-robomaker-small-warehouse-world rev-parse HEAD
git submodule add <origin-url> colcon_ws/src/aws-robomaker-small-warehouse-world
git -C colcon_ws/src/aws-robomaker-small-warehouse-world checkout <đúng-commit-đang-dùng>
# (lặp lại tương tự cho nav2_minimal_tb3_sim nếu nó là loại (b))
```

Lưu ý: dòng ignore trong .gitignore không chặn submodule, nhưng để sạch sẽ hãy xoá dòng đó khi đã add submodule.

**(b) Vendor `kill_ros.sh`** → `scripts/kill_ros.sh` (giữ nội dung, sửa path cứng nếu có).

**(c) Rewrite `start_demo.sh`** — spec:

```bash
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WS="$REPO_ROOT/colcon_ws"           # MỘT workspace duy nhất, in-repo
# mọi `source $NAV_WS/...` + `source $AGENT_WS/...` (kể cả trong _tmux_window) → source "$WS/install/setup.bash"
# `bash $NAV_WS/kill_ros.sh` → bash "$REPO_ROOT/scripts/kill_ros.sh"
# preflight check 2 workspace → check 1 workspace
```

**(d) Quét path cứng còn sót:**

```bash
cd ~/AI20K
grep -rnE '(\$HOME|~|/home/[a-z0-9_]+)/colcon_ws' scripts/ colcon_ws/src/ eval/ tests/ *.md --include='*' | grep -v 'src/aws-robomaker' | grep -v 'src/nav2_minimal'
```

**GATE G0.2** (paste raw): grep = 0 dòng code (dòng trong .md docs cũ chấp nhận được nếu chỉ là mô tả lịch sử — liệt kê và giải thích từng dòng còn lại).

## B0.3 — Commit + push (CHỈ push lên zerokhong1/AI20K-mayB)

```bash
cd ~/AI20K && git add -A
git commit -m "P0: self-contain — submodule aws world, start_demo.sh single in-repo ws, vendor kill_ros.sh"
git diff HEAD~1 --stat
git diff HEAD~1 | grep -inE 'api[_-]?key|secret|token|AIza|sk-' || echo "KEY-SCAN: clean"
git push origin main && git rev-parse --short HEAD
```

Tiện thể: nếu `PLAN_may_B_trien_khai_full.md` đang nằm local (Máy A xác nhận nó KHÔNG có trên repo) → commit vào `plan/` luôn trong commit riêng.

**GATE G0.3** (paste raw): KEY-SCAN clean, push OK, ghi sha mới.

## B0.4 — GATE CHÍNH: clone sạch + build + /odom trong môi trường CÁCH LY

Yêu cầu cách ly (đây là "oracle độc lập" của Pha 0 — nếu shell test dính env ~/colcon_ws thì PASS là giả):

```bash
cd /tmp && rm -rf p0clone && git clone --recurse-submodules https://github.com/zerokhong1/AI20K-mayB p0clone
bash --noprofile --norc -c '
  export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  source /opt/ros/$(ls /opt/ros | head -1)/setup.bash
  echo "AMENT_PREFIX_PATH=$AMENT_PREFIX_PATH"          # PROOF 1: không được chứa /home/*/colcon_ws
  cd /tmp/p0clone/colcon_ws
  colcon build --symlink-install 2>&1 | tail -25       # PROOF 2: 0 packages failed
  source install/setup.bash
  ros2 pkg prefix aws_robomaker_small_warehouse_world  # PROOF 3: phải trỏ VÀO /tmp/p0clone
  tmux -L p0test kill-server 2>/dev/null; true
'
# start_demo từ clone, tmux socket riêng để không dính env tmux server cũ:
bash --noprofile --norc -c '
  export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  source /opt/ros/$(ls /opt/ros | head -1)/setup.bash
  cd /tmp/p0clone && bash scripts/start_demo.sh 2>&1 | tail -30   # PROOF 4: "✓ /odom present (Ns)"
'
bash --noprofile --norc -c '
  export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
  source /opt/ros/$(ls /opt/ros | head -1)/setup.bash
  source /tmp/p0clone/colcon_ws/install/setup.bash
  timeout 10 ros2 topic echo /odom --once | head -12   # PROOF 5: message thật, cũng từ shell cách ly
'
```

(Nếu start_demo.sh dùng `tmux` mặc định, cân nhắc thêm option socket riêng hoặc kill-server trước — tự quyết, báo lại cách làm.)

**GATE G0.4** (paste raw đủ 5 PROOF): AMENT không chứa ~/colcon_ws · build 0 fail · aws pkg trỏ vào clone · `/odom present` · message /odom thật. Fail ở đâu → paste 30 dòng cuối log tmux window `sim`, fix NHỎ NHẤT, chạy lại ĐÚNG bước đó. Tối đa 1 vòng fix/gate rồi báo về dù đang dở.

## WATCH-LIST (lỗi rẻ tiền hay gặp)

1. `nav2_minimal_tb3_sim` nếu là source-built mà quên đưa vào repo → launch chết ngay dòng `get_package_share_directory` (nó còn `open()` urdf TB3 vô điều kiện kể cả khi spawn forklift).
2. Map `maps/005/map.yaml` — kiểm tra tồn tại trong bản aws world đem vào repo (005 có thể là map tự bake, không có ở upstream → phải vendor map riêng).
3. tmux server cũ giữ env cũ → test giả-PASS hoặc giả-FAIL. Dùng socket riêng/kill-server.
4. Submodule: clone test PHẢI dùng `--recurse-submodules`; quên = build fail oan.
5. Build sạch lần đầu có thể thiếu apt deps (rosdep) — nếu gặp, `rosdep install --from-paths src -yi` rồi GHI VÀO README mục Prerequisites, không lẳng lặng cài.
6. Đừng commit `colcon_ws/{build,install,log}` của bản clone test (nó ở /tmp, nhưng cẩn thận vẫn hơn).
7. CẤM key trong repo public. CẤM push lên git BTC AI20K-Build-Cohort-2.

## BÁO CÁO VỀ MÁY A (format bắt buộc)

```
PHA 0 — KẾT QUẢ
Gate   | PASS/FAIL | ghi chú 1 dòng
G0.0.. | ...       | ...
SHA cuối: <sha>  ·  Files changed: <list>
Deviation so với lệnh (nếu có): <gì + vì sao>
RAW OUTPUTS: <block đầy đủ theo từng gate, không cắt số>
```

Máy A sẽ fetch repo (cache-bust) đối chiếu từng claim. Số đẹp không raw = trả lại.